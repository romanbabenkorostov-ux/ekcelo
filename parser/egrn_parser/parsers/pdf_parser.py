"""
egrn_parser/parsers/pdf_parser.py — парсер PDF-выписок ЕГРН.

Поддерживаемые типы объектов: Земельный участок, Здание, Помещение,
Сооружение, Машино-место, ОНС.

Оба шаблона: 'full' (…об объекте недвижимости)
             'brief' (…об основных характеристиках…)

Раздел 1 → АКТИВ (характеристики объекта + object_restrictions)
Раздел 2 → ПАССИВ (права / обременения / ограничения прав)

ВАЖНО: поле «Сведения о возможности предоставления третьим лицам персональных
       данных физического лица» НИКОГДА не сохраняется (Приложение A ТЗ).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import warnings
from pathlib import Path
from typing import Any, Optional

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pdfplumber

from egrn_parser.parsers._common import (
    CAD_NUMBER_RE,
    INN_RE,
    parse_date_ru,
    parse_datetime_ru,
    parse_date_any,
    parse_number,
    parse_share,
    parse_term,
    normalize_cad_number,
    extract_all_cad_numbers,
    cad_quarter,
    extract_inn,
    extract_ogrn,
    classify_holder_type,
    normalize_whitespace,
    is_absent,
    clean_value,
)
from egrn_parser.utils.personal_data_filter import (
    filter_personal_data,
    clean_personal_data_from_text,
)
from egrn_parser.dictionaries import (
    OBJECT_TYPE_RU_TO_CODE,
    RIGHT_TYPE_RU_TO_CODE,
    ENCUMBRANCE_RU_TO_CODE,
    RESTRICTION_PHRASE_TO_CODE,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Константы
# ─────────────────────────────────────────────────────────────────────────────

EGRN_MARKERS = (
    "выписка из единого государственного реестра недвижимости",
    "роскадастр",
    "росреестр",
    "сведения о характеристиках объекта недвижимости",
    "сведения об основных характеристиках",
)

FULL_MARKER  = "об объекте недвижимости"
BRIEF_MARKER = "об основных характеристиках"

# Regex для номера и даты выписки
EXTRACT_NUM_RE  = re.compile(r"№\s*(КУВИ-\d+/\d{4}-\d+)")
EXTRACT_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*г?\.?\s*№\s*КУВИ")

# Regex кадастрового номера из шапки
CAD_NUM_LABEL_RE = re.compile(r"Кадастровый номер\s*:\s*(\d{2}:\d{2}:\d{6,7}:\d+)")

# Тип объекта
OBJ_TYPE_RE = re.compile(
    r"(Земельный участок|Помещение|Здание|Сооружение|Машино-место|"
    r"Объект незаверш[её]нного строительства)"
    r"[\s\r\n]+вид объекта",
    re.IGNORECASE,
)

# Разделы
SECTION_RE = re.compile(r"(?:Раздел|раздел)\s+(\d+(?:\.\d+)?)")
SECTION_SHEET_RE = re.compile(r"Лист\s*№\s*(\d+)\s*раздела\s*(\d+(?:\.\d+)?)")

# Поле «Получатель выписки» — для исключения из хранения
RECIPIENT_RE = re.compile(r"Получатель выписки\s*:\s*(.+)", re.IGNORECASE)

# Personal data pattern (для очистки текста)
PERSONAL_CONSENT_RE = re.compile(
    r"Сведения о возможности предоставления третьим лицам персональных данных.*?"
    r"(?=\n\d+\s|\nИНН:|\nОГРН:|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Идентификация файла
# ─────────────────────────────────────────────────────────────────────────────

def is_egrn_pdf(pdf_path: Path | str) -> bool:
    """Проверить, является ли PDF выпиской ЕГРН."""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if not pdf.pages:
                return False
            text = (pdf.pages[0].extract_text() or "").lower()
            return any(m in text for m in EGRN_MARKERS)
    except Exception as e:
        log.warning("Не удалось открыть %s: %s", Path(pdf_path).name, e)
        return False


def detect_template(full_text: str) -> str:
    """Определить шаблон выписки: 'full' или 'brief'."""
    t = full_text.lower()
    if BRIEF_MARKER in t:
        return "brief"
    return "full"


# ─────────────────────────────────────────────────────────────────────────────
#  Парсинг страниц по разделам
# ─────────────────────────────────────────────────────────────────────────────

def _split_pages_by_section(pdf) -> dict[str, list]:
    """
    Разделить страницы PDF по номерам разделов.
    Возвращает dict: {'1': [page,...], '2': [page,...], ...}
    """
    sections: dict[str, list] = {}
    for page in pdf.pages:
        text = page.extract_text() or ""
        m = SECTION_SHEET_RE.search(text)
        if m:
            sec = m.group(2)
        else:
            # Fallback: ищем «Раздел N»
            m2 = SECTION_RE.search(text)
            sec = m2.group(1) if m2 else "1"
        sections.setdefault(sec, []).append(page)
    return sections



def _clean_status_text(raw: str) -> Optional[str]:
    """Убрать «Сведения об объекте недвижимости имеют статус» из lifecycle_status_text."""
    if not raw:
        return None
    cleaned = raw.strip()
    # Удаляем стандартный префикс (с кавычками и без)
    import re as _re
    cleaned = _re.sub(
        r'^Сведения об объекте недвижимости имеют статус\s*["“]?\s*',
        '', cleaned, flags=_re.IGNORECASE
    ).strip('"» ')
    return cleaned or None


# ─────────────────────────────────────────────────────────────────────────────
#  Извлечение метаданных (шапка)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_header(full_text: str) -> dict:
    """Извлечь метаданные выписки из полного текста PDF."""
    result: dict[str, Any] = {
        "extract_number":   None,
        "extract_date":     None,
        "organ":            None,
        "extract_template": detect_template(full_text),
        "total_sheets":     None,
        "total_sections":   None,
    }

    # Номер выписки
    m = EXTRACT_NUM_RE.search(full_text)
    if m:
        result["extract_number"] = m.group(1)

    # Дата выписки
    m = EXTRACT_DATE_RE.search(full_text)
    if m:
        result["extract_date"] = parse_date_ru(m.group(1))

    # Орган регистрации
    m = re.search(r"Филиал публично-правовой компании[^\n]+", full_text)
    if m:
        result["organ"] = normalize_whitespace(m.group(0))

    # Общее число листов
    m = re.search(r"Всего листов выписки:\s*(\d+)", full_text)
    if m:
        result["total_sheets"] = int(m.group(1))

    # Число разделов
    m = re.search(r"Всего разделов:\s*(\d+)", full_text)
    if m:
        result["total_sections"] = int(m.group(1))

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Парсинг раздела 1 — характеристики объекта (АКТИВ)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_field(text: str, label: str, multiline: bool = False) -> Optional[str]:
    """Извлечь значение поля по метке из текста."""
    pattern = re.compile(
        rf"{re.escape(label)}\s*:?\s*(.+?)"
        + (r"(?=\n[А-ЯA-Z]|\Z)" if multiline else r"(?:\n|$)"),
        re.IGNORECASE | (re.DOTALL if multiline else 0),
    )
    m = pattern.search(text)
    if not m:
        return None
    val = normalize_whitespace(m.group(1))
    return None if is_absent(val) else val



def _extract_name_safe(text: str, cad_number: str) -> Optional[str]:
    """
    Извлечь наименование объекта ТОЛЬКО из текста после первого упоминания
    кадастрового номера. Предотвращает ложное срабатывание на
    «полное наименование органа регистрации прав».
    """
    # Найти позицию первого вхождения кад. номера
    pos = text.find(cad_number)
    if pos < 0:
        return None
    after_cad = text[pos:]
    # Ищем «Наименование:» как отдельное поле (не «полное наименование»)
    m = re.search(
        r"(?m)^Наименование\s*:\s*(.+?)$",
        after_cad,
        re.IGNORECASE,
    )
    if m:
        val = normalize_whitespace(m.group(1))
        if val and not is_absent(val) and len(val) < 200:
            return val
    return None


def _parse_section1_land(text: str) -> dict:
    """Парсинг раздела 1 для земельного участка."""
    result: dict[str, Any] = {}

    result["area"]        = parse_number(_extract_field(text, "Площадь") or "")
    result["area_error"]  = None

    # Площадь с погрешностью: «248 +/- 6»
    m = re.search(r"Площадь\s*:\s*([\d.]+)\s*\+/-\s*([\d.]+)", text)
    if m:
        result["area"]       = parse_number(m.group(1))
        result["area_error"] = parse_number(m.group(2))

    result["land_category"]  = clean_value(_extract_field(text, "Категория земель") or "")
    result["permitted_uses"] = clean_value(_extract_field(text, "Виды разрешенного использования") or "")

    # Кадастровая стоимость (Fix 40e: несколько паттернов)
    kv = (_extract_field(text, "Кадастровая стоимость, руб.")
          or _extract_field(text, "Кадастровая стоимость, руб")
          or _extract_field(text, "Кадастровая стоимость"))
    # Убрать артефакты ". " в начале (когда label заканчивается перед точкой)
    import re as _re
    if kv and _re.match(r'^[.:\s]+', kv):
        kv = _re.sub(r'^[.:\s]+', '', kv)
    result["cadastral_value"] = parse_number(kv or "")

    # Статус записи
    status_raw = _extract_field(text, "Статус записи об объекте недвижимости") or ""
    result["lifecycle_status"]      = "deregistered" if "снят" in status_raw.lower() else "active"
    result["lifecycle_status_text"] = _clean_status_text(status_raw)

    # Вложенные объекты (кад. номера в пределах участка)
    nested_raw = _extract_field(text, "Кадастровые номера расположенных в пределах земельного участка объектов") or ""
    nested = extract_all_cad_numbers(nested_raw)
    result["nested_objects"] = json.dumps(nested, ensure_ascii=False) if nested else None

    # Предшественники / преемники
    pred_raw = _extract_field(text, "Кадастровые номера объектов недвижимости, из которых образован") or ""
    succ_raw = _extract_field(text, "Кадастровые номера образованных объектов недвижимости") or ""
    preds = extract_all_cad_numbers(pred_raw)
    succs = extract_all_cad_numbers(succ_raw)
    result["predecessor_cad_numbers"] = json.dumps(preds, ensure_ascii=False) if preds else None
    result["successor_cad_numbers"]   = json.dumps(succs, ensure_ascii=False) if succs else None

    return result


def _parse_section1_building(text: str) -> dict:
    """Парсинг раздела 1 для здания."""
    result: dict[str, Any] = {}

    result["area"]    = parse_number(
        _extract_field(text, "Площадь, м2") or _extract_field(text, "Площадь") or ""
    )
    # name: искать только после кад. номера чтобы не поймать «полное наименование органа»
    result["name"]    = None   # заполняется в parse_egrn_pdf после определения cad_number
    result["purpose"] = clean_value(_extract_field(text, "Назначение") or "")

    # Этажность
    floors_raw = _extract_field(text, "Количество этажей, в том числе подземных этажей") or ""
    if floors_raw:
        m_total = re.match(r"(\d+)", floors_raw)
        if m_total:
            ft = int(m_total.group(1))
            result["floors_total"] = ft if ft < 200 else None  # >200 = скорее год
        m_ug = re.search(r"(\d+)\s*$", floors_raw)
        if m_ug:
            fug = int(m_ug.group(1))
            result["underground_floors"] = fug if fug < 200 else None
    else:
        # В некоторых форматах этажность разбита по строкам
        m_floors = re.search(r"Количество этажей.*?(\d+)", text, re.DOTALL)
        if m_floors:
            result["floors_total"] = int(m_floors.group(1))

    # Вычислить floors_above_ground
    ft  = result.get("floors_total")
    fug = result.get("underground_floors", 0) or 0
    if ft is not None:
        result["floors_above_ground"] = ft - fug

    result["year_built"]  = _parse_year(_extract_field(text, "Год завершения строительства") or "")
    result["year_used"]   = _parse_year(_extract_field(text, "Год ввода в эксплуатацию по завершении строительства") or "")

    # Кадастровая стоимость
    # Fix 40e: несколько паттернов для кадастровой стоимости
    kv = (_extract_field(text, "Кадастровая стоимость, руб.")
          or _extract_field(text, "Кадастровая стоимость, руб")
          or _extract_field(text, "Кадастровая стоимость"))
    if kv:
        import re as _re; kv = _re.sub(r'^[.:\s]+', '', kv)
    result["cadastral_value"] = parse_number(kv or "")

    # ЗУ-носители: pdfplumber склеивает ячейки горизонтально (Fix 21/22)
    land_cads_b = []
    for _line in text.splitlines():
        if "пределах" in _line.lower():
            land_cads_b.extend(extract_all_cad_numbers(_line))
    if not land_cads_b:
        land_raw = _extract_field(text, "Кадастровые номера иных объектов недвижимости, в пределах которых") or ""
        land_cads_b = extract_all_cad_numbers(land_raw)
    result["land_cad_numbers"] = "; ".join(land_cads_b) if land_cads_b else None

    # Статус
    status_raw = _extract_field(text, "Статус записи об объекте недвижимости") or ""
    result["lifecycle_status"]      = "deregistered" if "снят" in status_raw.lower() else "active"
    result["lifecycle_status_text"] = _clean_status_text(status_raw)

    return result


def _parse_section1_room(text: str) -> dict:
    """Парсинг раздела 1 для помещения / машино-места."""
    result: dict[str, Any] = {}

    result["area"]    = parse_number(
        _extract_field(text, "Площадь, м2") or _extract_field(text, "Площадь") or ""
    )
    # name: искать только после кад. номера чтобы не поймать «полное наименование органа»
    result["name"]    = None   # заполняется в parse_egrn_pdf после определения cad_number
    result["purpose"] = clean_value(_extract_field(text, "Назначение") or "")

    # Вид жилого помещения
    vp = _extract_field(text, "Вид жилого помещения")
    if vp and not result["name"]:
        result["name"] = clean_value(vp)

    # Этаж
    floor_raw = _extract_field(text, "Номер, тип этажа, на котором расположено помещение") or ""
    if not floor_raw:
        m = re.search(r"Этаж\s*№\s*([-\d,]+)", text)
        floor_raw = m.group(1) if m else ""
    result["floor"] = _parse_year(floor_raw)  # floor может быть числом

    # Родительский объект (здание/сооружение)
    parent_raw = _extract_field(text, "Кадастровые номера иных объектов недвижимости, в пределах которых") or ""
    parents = extract_all_cad_numbers(parent_raw)
    result["parent_cad_number"] = parents[0] if parents else None

    # Кадастровая стоимость
    # Fix 40e: несколько паттернов для кадастровой стоимости
    kv = (_extract_field(text, "Кадастровая стоимость, руб.")
          or _extract_field(text, "Кадастровая стоимость, руб")
          or _extract_field(text, "Кадастровая стоимость"))
    if kv:
        import re as _re; kv = _re.sub(r'^[.:\s]+', '', kv)
    result["cadastral_value"] = parse_number(kv or "")

    # Статус
    status_raw = _extract_field(text, "Статус записи об объекте недвижимости") or ""
    result["lifecycle_status"]      = "deregistered" if "снят" in status_raw.lower() else "active"
    result["lifecycle_status_text"] = _clean_status_text(status_raw)

    return result


def _parse_section1_structure(text: str) -> dict:
    """Парсинг раздела 1 для сооружения."""
    result: dict[str, Any] = {}

    result["name"]    = None  # заполняется в parse_egrn_pdf после cad_number
    result["purpose"] = clean_value(_extract_field(text, "Назначение") or "")

    # Основная характеристика сооружения / ОНС
    # Формат А (XML/полная): «тип значение единица измерения»
    m = re.search(
        r"Основная характеристика[^\n]*\n?"
        r"(?:[^\n]*\n)?"  # возможно строка «тип | значение | единица измерения»
        r"([\wа-яА-Я\s]+?)\s+(\d[\d.,\s]*)\s+(в\s+[\wа-яА-Я\s]+(?:метрах|метров)|погонных метрах|[\wа-яА-Я\s]+метр[а-я]*)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if m:
        result["main_char_type"] = normalize_whitespace(m.group(1))
        result["main_value"]     = parse_number(m.group(2))
        result["main_unit"]      = normalize_whitespace(m.group(3))
    else:
        # Формат Б (brief/pdfplumber горизонтальное склеивание):
        # «площадь застройки 335.7 в квадратных метрах»
        m2 = re.search(
            r"(?:площадь[\s\w]*|протяжённость[\s\w]*|высота[\s\w]*)\s+"
            r"([\d.,]+)\s+(в\s+[\wа-яА-Я]+(?:метрах|метров)|[\wа-яА-Я]+\s*метр[а-я]*)",
            text, re.IGNORECASE,
        )
        if m2:
            # Извлечь тип из контекста вокруг «Основная характеристика»
            mc_ctx = re.search(r"Основная характеристика[^\n]*\n([^\n]+)", text, re.IGNORECASE)
            result["main_char_type"] = normalize_whitespace(mc_ctx.group(1)) if mc_ctx else None
            result["main_value"]     = parse_number(m2.group(1))
            result["main_unit"]      = normalize_whitespace(m2.group(2))

    # Площадь (если указана напрямую; у ОНС поле «Площадь, м2»)
    area_raw = (
        _extract_field(text, "Площадь, м2")
        or _extract_field(text, "Площадь")
    )
    if area_raw:
        result["area"] = parse_number(area_raw)

    # Степень готовности ОНС
    sg = _extract_field(text, "Степень готовности объекта незавершенного строительства, %")
    if sg:
        result["construction_stage"] = parse_number(sg)

    # Проектируемое назначение ОНС
    pn = _extract_field(text, "Проектируемое назначение")
    if pn and not is_absent(pn):
        result["purpose"] = clean_value(pn)

    result["year_built"] = _parse_year(_extract_field(text, "Год завершения строительства") or "")
    result["year_used"]  = _parse_year(_extract_field(text, "Год ввода в эксплуатацию по завершении строительства") or "")

    # Fix 40e: несколько паттернов для кадастровой стоимости
    kv = (_extract_field(text, "Кадастровая стоимость, руб.")
          or _extract_field(text, "Кадастровая стоимость, руб")
          or _extract_field(text, "Кадастровая стоимость"))
    if kv:
        import re as _re; kv = _re.sub(r'^[.:\s]+', '', kv)
    result["cadastral_value"] = parse_number(kv or "")

    # ЗУ-носители: pdfplumber склеивает ячейки горизонтально (метка + значение в одной строке)
    land_cads = []
    for _line in text.splitlines():
        if "пределах" in _line.lower() or "расположен объект" in _line.lower():
            land_cads.extend(extract_all_cad_numbers(_line))
    if not land_cads:  # fallback через extract_field
        land_raw = _extract_field(text, "Кадастровые номера иных объектов недвижимости, в пределах которых") or ""
        land_cads = extract_all_cad_numbers(land_raw)
    result["land_cad_numbers"] = "; ".join(land_cads) if land_cads else None

    status_raw = _extract_field(text, "Статус записи об объекте недвижимости") or ""
    result["lifecycle_status"]      = "deregistered" if "снят" in status_raw.lower() else "active"
    result["lifecycle_status_text"] = _clean_status_text(status_raw)

    return result


def _parse_year(text: str) -> Optional[int]:
    """Извлечь 4-значный год из строки."""
    if not text:
        return None
    m = re.search(r"\b(\d{4})\b", text)
    return int(m.group(1)) if m else None


# ─────────────────────────────────────────────────────────────────────────────
#  Парсинг ограничений объекта (object_restrictions)
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_beneficiary(text: str) -> str | None:
    """Очистить имя бенефициара от артефактов pdfplumber (Fix 30, 31)."""
    if not text or is_absent(text):
        return None
    # Если это чисто ИНН (10 или 12 цифр) — сохранить как есть
    if re.match(r'^\d{10,12}$', text.strip()):
        return text.strip()
    # Сократить организационно-правовую форму (Fix 31)
    from egrn_parser.exporters.xlsx_exporter import _shorten_org_form
    try:
        text = _shorten_org_form(text)
    except Exception:
        pass
    return text.strip() or None


def _parse_object_restrictions(text: str, extract_number) -> list:
    """
    Извлечь ограничения объекта (ЗОУИТ, ОКН, охранные зоны) из всего текста.
    Обрабатывает многостраничные выписки с несколькими блоками.
    """
    import re as _re

    restrictions = []
    seen_reg_nums: set = set()

    # Regex вне r-строк во избежание проблем с \n
    BLOCK_RE  = _re.compile("(?:полностью расположен)[^\\n]*реестровым номером\\s+([\\d:.\\-/]+)", _re.IGNORECASE)
    VID_RE    = _re.compile("вид/наименование:\\s*([^\\n;,|]{3,200})", _re.IGNORECASE)
    TIP_RE    = _re.compile("тип:\\s*([^\\n,;]{3,100})", _re.IGNORECASE)
    DATE_RE   = _re.compile("дата решения:\\s*(\\d{2}\\.\\d{2}\\.\\d{4})", _re.IGNORECASE)
    NUM_RE    = _re.compile("номер решения:\\s*([^\\n,;]{1,100})", _re.IGNORECASE)

    for m_block in BLOCK_RE.finditer(text):
        reg_num = m_block.group(1).strip()
        if reg_num in seen_reg_nums:
            continue
        seen_reg_nums.add(reg_num)

        start = m_block.start()
        nxt   = BLOCK_RE.search(text, m_block.end())
        end   = nxt.start() if nxt else min(start + 3000, len(text))
        block = text[start:end]

        vid_m  = VID_RE.search(block)
        tip_m  = TIP_RE.search(block)
        date_m = DATE_RE.search(block)
        num_m  = NUM_RE.search(block)

        restr_type = "czuit_zone"
        if tip_m and "культурного наследия" in tip_m.group(1).lower():
            restr_type = "okn_territory"
        elif vid_m and "культурного наследия" in vid_m.group(1).lower():
            restr_type = "okn_territory"

        desc = None
        if vid_m:
            desc = normalize_whitespace(vid_m.group(1))[:200]
        elif tip_m:
            desc = normalize_whitespace(tip_m.group(1))[:200]

        restrictions.append({
            "type":            restr_type,
            "description":     desc,
            "registry_number": reg_num,
            "basis_doc": {
                "type":   "decision",
                "number": normalize_whitespace(num_m.group(1)) if num_m else None,
                "date":   parse_date_ru(date_m.group(1)) if date_m else None,
            },
            "source_extract": extract_number,
        })

    # Fallback: «Особые отметки» (ст. 56 ЗК) если нет реестровых номеров
    if not restrictions:
        om_m = _re.search("Особые отметки\\s*:(.*?)(?=Получатель выписки|\\Z)", text, _re.DOTALL | _re.IGNORECASE)
        if om_m:
            for chunk in _re.split("вид ограничения \\(обременения\\)\\s*:", om_m.group(1)):
                if not chunk.strip():
                    continue
                date_m = DATE_RE.search(chunk)
                num_m  = NUM_RE.search(chunk)
                rtype  = "okn_territory" if "культурного наследия" in chunk.lower() else "czuit_zone"
                desc_raw = normalize_whitespace(chunk[:200])
                # Пропустить ложноположительные («данные отсутствуют», «Сведения, необходимые»)
                _FALSE_POSITIVE_PATTERNS = (
                    "данные отсутствуют", "сведения, необходимые",
                    "план расположения", "отсутствуют.",
                )
                if any(fp in desc_raw.lower() for fp in _FALSE_POSITIVE_PATTERNS):
                    continue
                restrictions.append({
                    "type":            rtype,
                    "description":     desc_raw,
                    "registry_number": None,
                    "basis_doc": {"type": "decision",
                                  "number": normalize_whitespace(num_m.group(1)) if num_m else None,
                                  "date":   parse_date_ru(date_m.group(1)) if date_m else None},
                    "source_extract": extract_number,
                })
    return restrictions



def _parse_section2(
    text: str,
    cad_number: str,
    object_class: str,
    extract_number: Optional[str],
) -> dict:
    """
    Разобрать раздел 2 PDF-выписки.
    Возвращает dict с ключами:
      - 'rights':    список dict (права, обременения, ограничения прав)
      - 'personal_participation_req': bool
      - 'claim_records': str | None
    """
    # Очистить персональные данные перед парсингом
    text = clean_personal_data_from_text(text)

    rights: list[dict] = []
    personal_participation_req = False
    claim_records: Optional[str] = None

    # ── Разбивка на блоки правообладателей (ключ «1.N») ──────────────────────
    # Ищем начало каждого блока «1» → «1.1», «1.2», …
    # Стратегия: поиск строк вида «1\t1.1\t<holder>» в таблицах pdfplumber
    # Для текстового режима — ищем паттерн «1.1» с последующим текстом
    right_block_re = re.compile(
        r"(?m)^1\s+(?:Правообладатель.*?)?$",
    )

    # Упрощённый подход: ищем блоки по ключам 1.N, 2.N, 4/5 в тексте
    rights.extend(_parse_rights_from_text(text, cad_number, object_class, extract_number))

    # ── Ключ «10» → personal_participation_req ───────────────────────────────
    m10 = re.search(
        r"(?:10|Сведения о невозможности[^\n]+)\s*(.+?)(?=11|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if m10:
        val = normalize_whitespace(m10.group(1))
        personal_participation_req = not is_absent(val)

    # ── Ключ «11» → claim_records ────────────────────────────────────────────
    m11 = re.search(
        r"(?:11|Правопритязания)[^\n]*\n+(.+?)(?=\Z|Раздел\s+\d)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if m11:
        val = normalize_whitespace(m11.group(1))
        claim_records = None if is_absent(val) else val[:1000]

    return {
        "rights":                    rights,
        "personal_participation_req":personal_participation_req,
        "claim_records":             claim_records,
    }


def _parse_rights_from_text(
    text: str,
    cad_number: str,
    object_class: str,
    extract_number: Optional[str],
) -> list[dict]:
    """
    Основной алгоритм извлечения прав из текстового представления раздела 2.
    Разделяет три категории: right / encumbrance / restriction.
    """
    rights: list[dict] = []

    # ── Права (ключ 2.N — вид, номер, дата регистрации) ─────────────────────
    # Паттерн: многострочная запись «Вид, номер, дата и время государственной регистрации права»
    right_blocks = _extract_right_blocks(text)
    for block in right_blocks:
        right = _parse_one_right_block(block, cad_number, object_class, extract_number)
        if right:
            rights.append(right)

    # ── Обременения/ограничения (ключи 4, 5) ─────────────────────────────────
    enc_blocks = _extract_encumbrance_blocks(text)
    for block in enc_blocks:
        enc = _parse_one_encumbrance_block(block, cad_number, object_class, extract_number)
        if enc:
            rights.append(enc)

    return rights


# Regex для поиска блоков «Вид, номер, дата» в тексте
RIGHT_BLOCK_RE = re.compile(
    r"(?:Вид,\s*номер,\s*дата и время[^\n]*\n)"
    r"(.*?)(?=(?:Вид,\s*номер,\s*дата|Ограничение прав|Договоры участия|"
    r"Заявленные в судебном|Сведения о возможности|Правопритязания|\Z))",
    re.DOTALL | re.IGNORECASE,
)

# Regex для поиска данных правообладателя
HOLDER_NAME_RE = re.compile(
    r"(?:Правообладатель|1\.\d)\s*[:\s]+([^\n]+?(?:ИНН|ОГРН|$))",
    re.IGNORECASE,
)


def _extract_right_blocks(text: str) -> list[str]:
    """Извлечь текстовые блоки прав из раздела 2."""
    blocks = []
    # Ищем все вхождения «2.N Вид, номер, дата...»
    pattern = re.compile(
        r"(2\.?\d*\s*(?:Вид,\s*номер,\s*дата и время государственной регистрации права)?[^\n]*"
        r"(?:\n(?!\d+\s+).*)*)",
        re.MULTILINE,
    )
    # Fallback: ищем паттерны «Собственность\n<номер>\n<дата>»
    # Ищем блоки: тип_права + номер регистрации + дата
    alt_pattern = re.compile(
        r"((?:Собственность|Общая долевая собственность|Аренда|"
        r"Постоянное \(бессрочное\) пользование|Оперативное управление|"
        r"Хозяйственное ведение|Безвозмездное пользование|"
        r"Пожизненное наследуемое владение|Доверительное управление)[^\n]*\n"
        r"[\d\-/:а-яА-Я]+[^\n]*(?:\n[\d.:\s]+[^\n]*)?)",
        re.IGNORECASE,
    )
    for m in alt_pattern.finditer(text):
        blocks.append(m.group(0))
    return blocks


def _parse_one_right_block(
    block: str,
    cad_number: str,
    object_class: str,
    extract_number: Optional[str],
) -> Optional[dict]:
    """Разобрать один блок записи о праве."""
    lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
    if not lines:
        return None

    # Строка 0: «Тип права, доля/1000»
    line0 = lines[0]
    right_type_raw = line0.split(",")[0].strip()
    right_type_code = RIGHT_TYPE_RU_TO_CODE.get(right_type_raw.lower(), "unknown")

    share_num, share_den = parse_share(line0)

    # Строка 1: номер регистрации (убрать артефакт "права: " от pdfplumber)
    right_number = lines[1] if len(lines) > 1 else None
    if right_number:
        right_number = re.sub(r'^(?:права|ограничения|обременения):\s*', '', right_number, flags=re.IGNORECASE).strip()
        # Если lines[1] содержит «дата» — значит это не номер, берём lines[2]
        if right_number and re.search(r'дата|^\d{2}\.\d{2}\.\d{4}', right_number, re.IGNORECASE):
            right_number = lines[2] if len(lines) > 2 else None
        if not right_number:
            right_number = lines[2] if len(lines) > 2 else None
    # Ещё раз очистить если всё равно попала дата
    if right_number and re.search(r'дата государственной', right_number, re.IGNORECASE):
        right_number = None

    # Строка 2: дата регистрации
    right_date: Optional[str] = None
    if len(lines) > 2:
        right_date = parse_datetime_ru(lines[2]) or parse_date_ru(lines[2])

    if not right_number:
        return None

    return filter_personal_data({
        "object_class":     object_class,
        "object_key_type":  "cad_number",
        "object_key_value": cad_number,
        "right_category":   "right",
        "right_type":       right_type_raw,
        "right_type_code":  right_type_code,
        "right_number":     right_number,
        "right_date":       right_date,
        "share_numerator":  share_num,
        "share_denominator":share_den,
        "is_active":        1,
        "source_extract_number": extract_number,
        "source_format":    "pdf",
    })


def _extract_encumbrance_blocks(text: str) -> list[str]:
    """Извлечь блоки обременений/ограничений (ключи 4, 5) из текста."""
    blocks = []

    # Паттерн для «вид: Запрещение регистрации» / «вид: Ипотека» и т.д.
    enc_start_re = re.compile(
        r"(?:(?:4|5)\.?\d*\s+)?вид\s*:\s*(Запрещение регистрации|Ипотека|Аренда|"
        r"Арест|Сервитут|Публичный сервитут|Концессия|[^\n]+)",
        re.IGNORECASE,
    )
    # Ищем каждое вхождение «вид:»
    positions = [(m.start(), m.end()) for m in enc_start_re.finditer(text)]
    seen_types: set = set()
    for i, (start, end) in enumerate(positions):
        finish = positions[i+1][0] if i+1 < len(positions) else len(text)
        stop_re = re.compile(r"(?:Договоры участия|Заявленные в судебном|Правопритязания|Сведения о невозможности)")
        stop_m = stop_re.search(text, end)
        if stop_m and stop_m.start() < finish:
            finish = stop_m.start()
        block_text = text[start:finish]
        # Дедупликация по комбинации вид+номер
        num_m = re.search(r"номер государственной регистрации\s*:\s*([^\n]+)", block_text, re.IGNORECASE)
        key = num_m.group(1).strip() if num_m else block_text[:60]
        if key in seen_types:
            continue
        seen_types.add(key)
        blocks.append(block_text)

    return blocks


def _normalize_org_name(name: str) -> str:
    """Нормализовать ООО/ПАО/АО в наименовании (Fix 31)."""
    import re as _r
    if not name:
        return name
    pairs = [
        ("Общество с ограниченной ответственностью", "ООО"),
        ("Публичное акционерное общество", "ПАО"),
        ("Акционерное общество", "АО"),
        ("Закрытое акционерное общество", "ЗАО"),
        ("Открытое акционерное общество", "ОАО"),
        ("Публично-правовая компания", "ППК"),
        ("Государственное унитарное предприятие", "ГУП"),
        ("Муниципальное унитарное предприятие", "МУП"),
    ]
    r = name
    for long, short in pairs:
        r = _r.sub(long, short, r, flags=_r.IGNORECASE)
    return r.strip()


def _parse_one_encumbrance_block(
    block: str,
    cad_number: str,
    object_class: str,
    extract_number: Optional[str],
) -> Optional[dict]:
    """Разобрать один блок обременения/ограничения прав."""
    block = clean_personal_data_from_text(block)
    if not block.strip():
        return None

    rec: dict[str, Any] = {
        "object_class":      object_class,
        "object_key_type":   "cad_number",
        "object_key_value":  cad_number,
        "is_active":         1,
        "source_extract_number": extract_number,
        "source_format":     "pdf",
    }

    # Вид обременения
    m_vid = re.search(r"вид\s*:\s*([^\n]+)", block, re.IGNORECASE)
    if m_vid:
        right_type_raw = normalize_whitespace(m_vid.group(1))
        rec["right_type"] = right_type_raw
        code = ENCUMBRANCE_RU_TO_CODE.get(right_type_raw.lower(), "other")
        rec["right_type_code"] = code
        # Признак публичного сервитута
        if "публичный" in right_type_raw.lower():
            rec["servitude_is_public"] = 1

    # Дата регистрации
    m_date = re.search(r"дата государственной регистрации\s*:\s*([^\n]+)", block, re.IGNORECASE)
    if m_date:
        rec["right_date"] = parse_datetime_ru(m_date.group(1)) or parse_date_ru(m_date.group(1))

    # Номер регистрации
    m_num = re.search(r"номер государственной регистрации\s*:\s*([^\n]+)", block, re.IGNORECASE)
    if m_num:
        rec["right_number"] = normalize_whitespace(m_num.group(1))

    # Срок
    m_srok = re.search(
        r"срок[^\n]*(?:ограничени[яе]|действия)?[^\n]*:\s*([^\n]+)",
        block, re.IGNORECASE,
    )
    if m_srok:
        term = parse_term(m_srok.group(1))
        rec.update(term)

    # Лицо, в пользу которого → encumbrance; если нет → restriction
    # ── Извлечение бенефициара ──────────────────────────────────────────────
    # Используем DOTALL для перекрёстных строк (Fix 30, 31)
    m_ben = re.search(
        r"лицо,\s*в пользу которого[^:]*:\s*(.{1,400}?)(?=\n(?:основани|сведения о возможности|данные отсутствуют)|\Z)",
        block, re.DOTALL | re.IGNORECASE,
    )
    if m_ben:
        ben_raw = normalize_whitespace(m_ben.group(1))
        # Убрать артефакты pdfplumber — системный префикс второй строки
        ben_raw = re.sub(
            r"^(?:прав и обременение объекта недвижимости|ограничение прав"
            r"|объекта недвижимости|прав и обременение)\s*:\s*",
            "", ben_raw, flags=re.IGNORECASE,
        ).strip()
        if ben_raw and not is_absent(ben_raw) and ben_raw.lower() not in ("не определено", "данные отсутствуют"):
            ben_inn = extract_inn(ben_raw)
            # Очистить имя: убрать «, ИНН: xxxxxxxx» в конце
            ben_name = re.sub(r",?\s*ИНН[:\s]+\d{10,12}", "", ben_raw, flags=re.IGNORECASE).strip()
            # Если осталось только ИНН — имени нет
            if re.match(r"^\d{10,12}$", ben_name.strip()):
                ben_name = None
            # Нормализация: ООО, ПАО и т.д. (Fix 31)
            if ben_name:
                ben_name = _normalize_org_name(ben_name)
            # Если INN извлечён не из текста — пробовать извлечь ОГРН-подобный паттерн
            if not ben_inn:
                inn_only = re.search(r"\b(\d{10,12})\b", ben_raw)
                if inn_only:
                    ben_inn = inn_only.group(1)
            rec["beneficiary_name"] = ben_name
            rec["beneficiary_inn"]  = ben_inn
            rec["right_category"]   = "encumbrance"
        else:
            rec["right_category"] = "restriction"
    else:
        rec["right_category"] = "restriction"

    # Документ-основание
    m_basis = re.search(r"основани[ея][^\n]*:\s*([^\n]+(?:\n[^\n]+)?)", block, re.IGNORECASE)
    if m_basis:
        rec["basis"] = normalize_whitespace(m_basis.group(1))[:500]

    # Если нет ни вида, ни номера — пропустить
    if not rec.get("right_type") and not rec.get("right_number"):
        return None

    return filter_personal_data(rec)


# ─────────────────────────────────────────────────────────────────────────────
#  Главная функция парсинга
# ─────────────────────────────────────────────────────────────────────────────

def parse_egrn_pdf(pdf_path: Path | str) -> Optional[dict]:
    """
    Разобрать PDF-выписку ЕГРН.

    Возвращает dict с ключами:
      header:       метаданные выписки
      object:       характеристики объекта (актив)
      rights:       список записей о правах (пассив)
      object_restrictions: список ограничений объекта (JSON-массив)
      raw_text:     полный текст для отладки
      cad_number:   кадастровый номер
      object_type:  тип объекта ('land', 'building', ...)

    Или None если файл не является валидной ЕГРН-выпиской.
    """
    pdf_path = Path(pdf_path)
    log.debug("Парсинг PDF: %s", pdf_path.name)

    if not is_egrn_pdf(pdf_path):
        log.warning("Файл не является выпиской ЕГРН: %s", pdf_path.name)
        return None

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]
    except Exception as e:
        log.error("Ошибка чтения %s: %s", pdf_path.name, e)
        return None

    full_text = "\n".join(pages_text)

    # ── Метаданные ───────────────────────────────────────────────────────────
    header = _parse_header(full_text)

    # ── Кадастровый номер ────────────────────────────────────────────────────
    m_cad = CAD_NUM_LABEL_RE.search(full_text)
    if not m_cad:
        log.warning("Кадастровый номер не найден в %s", pdf_path.name)
        return None
    cad_number = m_cad.group(1)

    # ── Тип объекта ──────────────────────────────────────────────────────────
    m_type = OBJ_TYPE_RE.search(full_text)
    obj_type_ru = m_type.group(1).capitalize() if m_type else ""
    object_type = OBJECT_TYPE_RU_TO_CODE.get(obj_type_ru.lower(), "unknown")

    # ── Разделение текста по разделам ────────────────────────────────────────
    # Буферизуем страницы раздела 1 и 2 по маркерам
    sec1_text = ""
    sec2_text = ""
    current_section = "1"

    for page_text in pages_text:
        # Определяем раздел по маркеру на странице
        m_sec = SECTION_SHEET_RE.search(page_text)
        if m_sec:
            current_section = m_sec.group(2)
        if current_section in ("1",):
            sec1_text += "\n" + page_text
        elif current_section in ("2",):
            sec2_text += "\n" + page_text
        # Разделы 3–8 (планы, схемы) — пропускаем

    # Fallback: если не нашли разделы — берём весь текст
    if not sec1_text:
        sec1_text = full_text
    if not sec2_text:
        # Ищем раздел 2 по маркеру «Сведения о зарегистрированных правах»
        m_r2 = re.search(r"Сведения о зарегистрированных правах", full_text)
        if m_r2:
            sec2_text = full_text[m_r2.start():]

    # ── Парсинг раздела 1 ────────────────────────────────────────────────────
    obj_data: dict[str, Any] = {
        "cad_number":          cad_number,
        "quarter_cad_number":  cad_quarter(cad_number),
        "object_type":         object_type,
        "data_source":         pdf_path.name,
        "source_file":         pdf_path.name,
        "is_primary":          1,
    }

    # Адрес / местоположение
    addr = (_extract_field(sec1_text, "Местоположение") or
            _extract_field(sec1_text, "Адрес") or
            _extract_field(sec1_text, "Местоположение установлено"))
    obj_data["address"] = clean_value(addr or "")

    # Дата присвоения кадастрового номера
    reg_date_raw = _extract_field(sec1_text, "Дата присвоения кадастрового номера")
    obj_data["registration_date"] = parse_date_ru(reg_date_raw or "")

    # Ранее присвоенные номера — хранить как plain text
    # Multiline: ранее присвоенный номер может продолжаться на следующей строке
    old_raw = _extract_field(sec1_text, "Ранее присвоенный государственный учетный номер",
                              multiline=True)
    if not old_raw or is_absent(old_raw):
        old_raw = _extract_field(sec1_text, "Ранее присвоенный государственный учетный номер")
    if old_raw and not is_absent(old_raw):
        # Склеить строки которые pdfplumber разорвал (продолжение начинается с маленькой буквы или цифры)
        import re as _re2
        import re as _re2
        old_clean = ' '.join(old_raw.split())
        # Убрать пробелы вокруг дефисов в числах (артефакт pdfplumber)
        old_clean = _re2.sub(r'(\d+)- (\d)', r'\1-\2', old_clean)
        old_clean = _re2.sub(r'(\d)- ([\d/])', r'\1-\2', old_clean)
        obj_data["old_numbers"] = old_clean.strip()

    # Тип-специфичные поля
    if object_type == "land":
        obj_data.update(_parse_section1_land(sec1_text))
        # Auto-generate name для ЗУ
        area = obj_data.get("area")
        area_str = f", {area} кв.м" if area else ""
        obj_data["name"] = f"Земельный участок {cad_number}{area_str}"
    elif object_type in ("building", "complex"):
        obj_data.update(_parse_section1_building(sec1_text))
        # Безопасное извлечение наименования (после кад. номера в тексте)
        obj_data["name"] = _extract_name_safe(sec1_text, cad_number)
    elif object_type in ("room", "parking"):
        obj_data.update(_parse_section1_room(sec1_text))
        obj_data["name"] = _extract_name_safe(sec1_text, cad_number)
    elif object_type in ("structure", "ons"):
        obj_data.update(_parse_section1_structure(sec1_text))
        name = _extract_name_safe(sec1_text, cad_number)
        # ОНС: если нет «Наименование» — взять «Проектируемое назначение» как наименование
        if not name and object_type == "ons":
            name = obj_data.get("purpose")
        obj_data["name"] = name

    # ── Ограничения объекта (из раздела 1 и 2) ────────────────────────────────
    object_restrictions = _parse_object_restrictions(
        sec1_text + "\n" + sec2_text,
        header.get("extract_number"),
    )
    obj_data["object_restrictions"] = (
        json.dumps(object_restrictions, ensure_ascii=False) if object_restrictions else None
    )

    # ── Парсинг раздела 2 ────────────────────────────────────────────────────
    rights_data: dict = {"rights": [], "personal_participation_req": False, "claim_records": None}
    if sec2_text:
        rights_data = _parse_section2(
            sec2_text, cad_number, object_type or "land", header.get("extract_number")
        )

    # ── Content hash ─────────────────────────────────────────────────────────
    content_hash = _compute_content_hash({
        "cad_number":          cad_number,
        "area":                obj_data.get("area"),
        "cadastral_value":     obj_data.get("cadastral_value"),
        "address":             obj_data.get("address"),
        "permitted_uses":      obj_data.get("permitted_uses"),
        "object_restrictions": object_restrictions,
        "rights_summary":      [
            (r.get("right_number"), r.get("right_type"), r.get("valid_until"), r.get("beneficiary_inn"))
            for r in rights_data.get("rights", [])
        ],
    })
    obj_data["content_hash"] = content_hash

    # ── Получатель (не сохраняем, только для логов) ──────────────────────────
    # recipient = RECIPIENT_RE.search(full_text)  # намеренно не сохраняется

    result = filter_personal_data({
        "header":               header,
        "object":               obj_data,
        "rights":               rights_data.get("rights", []),
        "personal_participation_req": rights_data.get("personal_participation_req"),
        "claim_records":        rights_data.get("claim_records"),
        "object_restrictions":  object_restrictions,
        "cad_number":           cad_number,
        "object_type":          object_type,
        "source_filename":      pdf_path.name,
    })

    log.info(
        "✓ Разобрана выписка %s: %s (%s), прав: %d, ограничений объекта: %d",
        header.get("extract_number", "?"),
        cad_number,
        object_type,
        len(result["rights"]),
        len(object_restrictions),
    )
    return result


def _compute_content_hash(extract_summary: dict) -> str:
    """SHA-256 от нормализованного содержимого выписки (ТЗ раздел 7.6)."""
    payload = json.dumps(extract_summary, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
