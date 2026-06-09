"""
egrn_parser/parsers/egrul_egrip_pdf.py — адаптер PDF-выписок ФНС
ЕГРЮЛ/ЕГРИП → та же нормализованная запись, что и XML-парсер.

Зачем: у экономиста на руках чаще всего PDF (а не машиночитаемый XML).
PDF ФНС — табличный («№ п/п | Наименование показателя | Значение показателя»),
секции вводятся текстовыми заголовками. Надёжнее всего читается ШАПКА
(тип реестра + полное наименование/ФИО + ОГРН/ОГРНИП + ИНН) — её достаточно,
чтобы получить ИНН/ОГРН и затем дотянуть данные из checko/dadata по ИНН.
Связи (руководитель/учредители/правопреемник) парсятся best-effort по секциям.

Извлечение текста отделено от разбора: `parse_text(text)` — чистая функция
(тестируется на текстовых фикстурах без PDF-библиотек); `extract_text(pdf)`
пробует доступную библиотеку (pdfplumber → PyMuPDF → pypdfium2).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from egrn_parser.parsers._common import parse_number
from egrn_parser.parsers.egrul_egrip_normalized import empty_record

log = logging.getLogger(__name__)

# Интро-строки, по которым опознаём реестр.
_RE_EGRUL_INTRO = re.compile(r"реестра\s+юридических\s+лиц", re.IGNORECASE)
_RE_EGRIP_INTRO = re.compile(r"реестра\s+индивидуальных\s+предпринимателей", re.IGNORECASE)

# ОГРН/ОГРНИП/ИНН в шапке печатаются по одной цифре через пробел.
_RE_OGRN = re.compile(r"ОГРН\s+([\d\s]{13,40}?)(?:\n|$)")
_RE_OGRNIP = re.compile(r"ОГРНИП\s+([\d\s]{15,40}?)(?:\n|$)")
_RE_INN = re.compile(r"(?<!ОГРН)ИНН\s+([\d\s]{10,40}?)(?:\n|$)")


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


# ── Извлечение текста (зависит от доступной PDF-библиотеки) ──────────────────
def extract_text(pdf_path: Path | str) -> str:
    """Текст всех страниц PDF. Пробует pdfplumber → PyMuPDF → pypdfium2."""
    pdf_path = str(pdf_path)
    # 1) pdfplumber — уже используется в репо (pdf_parser.py)
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as exc:  # noqa: BLE001
        log.debug("pdfplumber недоступен/упал (%s), пробую PyMuPDF", exc)
    # 2) PyMuPDF (fitz)
    try:
        import fitz  # type: ignore

        with fitz.open(pdf_path) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as exc:  # noqa: BLE001
        log.debug("PyMuPDF недоступен/упал (%s), пробую pypdfium2", exc)
    # 3) pypdfium2
    import pypdfium2 as pdfium  # type: ignore

    doc = pdfium.PdfDocument(pdf_path)
    return "\n".join(
        doc[i].get_textpage().get_text_range() for i in range(len(doc))
    )


# ── Хелперы разбора текста ──────────────────────────────────────────────────
def detect_registry(text: str) -> Optional[str]:
    """Опознать реестр по интро PDF: 'ЕГРЮЛ' | 'ЕГРИП' | None."""
    head = text[:1500]
    if _RE_EGRIP_INTRO.search(head):
        return "ЕГРИП"
    if _RE_EGRUL_INTRO.search(head):
        return "ЕГРЮЛ"
    return None


def is_fns_reestr_pdf_text(text: str) -> bool:
    return detect_registry(text) is not None


def _is_counter(s: str) -> bool:
    """Строка-счётчик «№ п/п» (одни цифры, ≤3 знака). Значения ОГРН/ИНН/КПП длиннее."""
    return s.isdigit() and len(s) <= 3


# Ведущий счётчик «№ п/п» перед меткой (pdfplumber кладёт «NN Метка Значение»
# в одну строку; PyMuPDF — счётчик отдельной строкой).
_COUNTER_RE = re.compile(r"^\d{1,3}\s+")

# Короткие числовые метки: значение-остаток должно начинаться с цифры
# (чтобы «ИНН» не схватил «ИНН юридического лица …»).
_NUMERIC_LABELS = {"ИНН", "ОГРН", "ОГРНИП", "КПП"}


def _norm(lines: list[str]) -> list[str]:
    """Снять ведущий счётчик «№ п/п » с каждой строки (унификация pdfplumber/fitz)."""
    return [_COUNTER_RE.sub("", ln).rstrip() for ln in lines]


def _is_boundary(s: str) -> bool:
    """Граница значения: счётчик, заголовок секции или метка ГРН-даты."""
    return (not s or _is_counter(s) or s.startswith("ГРН и дата")
            or any(h in s for h in _SECTION_HEADERS))


def _label_rest(s: str, label: str) -> Optional[str]:
    """Если строка — это метка `label`, вернуть остаток-значение (или '' для fitz).

    None — если строка не начинается с метки. Для числовых меток остаток обязан
    начинаться с цифры (иначе это более длинная метка, напр. «ИНН юридического лица»).
    """
    if s == label:
        return ""
    if s.startswith(label + " "):
        rest = s[len(label):].strip()
        if label in _NUMERIC_LABELS and rest and not rest[0].isdigit():
            return None
        return rest
    return None


def _value_after(lines: list[str], label: str) -> Optional[str]:
    """Скалярное значение метки: остаток той же строки (pdfplumber) либо
    первая значимая строка ниже (PyMuPDF). Строки уже без счётчика (`_norm`)."""
    for i, ln in enumerate(lines):
        rest = _label_rest(ln.strip(), label)
        if rest is None:
            continue
        if rest:
            return rest
        for nx in lines[i + 1:]:
            if nx.strip():
                return nx.strip()
        return None
    return None


def _text_after(lines: list[str], label: str, *, limit: int = 4) -> Optional[str]:
    """Многострочное текстовое значение: остаток строки + перенос(ы) до границы.

    Покрывает обе раскладки: pdfplumber (значение на строке метки, хвост ниже)
    и PyMuPDF (значение полностью ниже метки)."""
    for i, ln in enumerate(lines):
        rest = _label_rest(ln.strip(), label)
        if rest is None:
            continue
        out: list[str] = []
        if rest:
            out.append(rest)
        for nx in lines[i + 1: i + 1 + limit + 2]:
            s = nx.strip()
            if _is_boundary(s):
                if out:
                    break
                continue
            out.append(s)
            if len(out) >= limit:
                break
        return " ".join(out) if out else None
    return None


# Строки колонтитулов/футеров, замусоривающие табличные значения.
_RE_FOOTER = re.compile(
    r"^(Страница\b|Выписка из ЕГР|\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$|ОГРН \d{13,15}$|ОГРНИП \d{15}$)")


def _strip_noise(lines: list[str]) -> list[str]:
    """Убрать колонтитулы ФНС-PDF: 'Страница N из', 'Выписка из ЕГРЮЛ',
    инлайн-футер 'ОГРН <субъекта>', метку времени и номер страницы за ними
    (иначе номер страницы попадает как значение ОГРН учредителя)."""
    out: list[str] = []
    prev_footer = False
    for ln in lines:
        s = ln.strip()
        if _RE_FOOTER.match(s):
            prev_footer = True
            continue
        # бара-число сразу после футер-ОГРН — это номер страницы, не значение
        if prev_footer and s.isdigit() and len(s) <= 4:
            prev_footer = False
            continue
        prev_footer = False
        out.append(ln)
    return out


def _section_slice(lines: list[str], start_markers: list[str], stop_markers: list[str]) -> list[str]:
    """Срез строк от первого start-маркера до ближайшего stop-маркера."""
    start = None
    for i, ln in enumerate(lines):
        if any(m in ln for m in start_markers):
            start = i
            break
    if start is None:
        return []
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if any(m in lines[j] for m in stop_markers):
            end = j
            break
    return lines[start:end]


# Заголовки секций (для границ).
_SECTION_HEADERS = [
    "Сведения о лице, имеющем право без доверенности",
    "Сведения об уставном капитале",
    "Сведения об участниках",
    "Сведения об учредителях",
    "Сведения об учете в налоговом органе",
    "Сведения о видах экономической",
    "Сведения об основном виде",
    "Сведения о дополнительных видах",
    "Сведения о правопреемник",
    "Сведения о правопредшественник",
    "Сведения о прекращении",
    "Сведения о записях",
    "Сведения о регистрации",
    "Сведения о состоянии",
]


def _fio_triple(lines: list[str]) -> Optional[dict]:
    """ФИО из трёх подряд меток Фамилия/Имя/Отчество (обе раскладки).

    pdfplumber: значение на строке метки («Фамилия ОБОРИН»). PyMuPDF: метки,
    затем три значения. Строки уже без счётчика (`_norm`)."""
    for i in range(len(lines) - 2):
        rf = _label_rest(lines[i].strip(), "Фамилия")
        ri = _label_rest(lines[i + 1].strip(), "Имя")
        ro = _label_rest(lines[i + 2].strip(), "Отчество")
        if rf is None or ri is None or ro is None:
            continue
        if rf and ri:  # inline (pdfplumber); отчество может отсутствовать
            return {"last": rf, "first": ri, "middle": ro or None}
        vals = [l.strip() for l in lines[i + 3: i + 6]]  # fitz: 3 значения ниже
        if len(vals) == 3 and all(vals):
            return {"last": vals[0], "first": vals[1], "middle": vals[2]}
    return None


def _ogrn_inn_name(block: list[str]) -> dict:
    """ОГРН/ИНН/Полное наименование из блока секции (для орг-связей)."""
    return {
        "ogrn": _digits(_value_after(block, "ОГРН") or "") or None,
        "inn": _digits(_value_after(block, "ИНН") or "") or None,
        "name": _text_after(block, "Полное наименование"),
    }


def _header_inn(text: str) -> Optional[str]:
    """ИНН из ШАПКИ выписки (первые строки), чтобы не схватить ИНН директора."""
    m = _RE_INN.search(text[:600])
    return _digits(m.group(1)) if m else None


# ── Разбор по реестрам ──────────────────────────────────────────────────────
def _parse_egrul_text(lines: list[str], rec: dict) -> None:
    text = "\n".join(lines)

    # Идентификация: имя — из чистой строки шапки; ОГРН — из шапки; ИНН —
    # из шапки (а если её нет, как у личного фонда) — из «ИНН юридического лица».
    name = _header_name(lines, "о юридическом лице") \
        or _text_after(lines, "Полное наименование на русском языке")
    m_ogrn = _RE_OGRN.search(text)
    inn = _header_inn(text) \
        or _digits(_value_after(lines, "ИНН юридического лица") or "") or None
    short = _text_after(lines, "Сокращенное наименование", limit=5)
    if short:  # убрать перенесённые фрагменты метки «на русском языке»
        short = re.sub(r"\b(на\s+русском|языке)\b", " ", short)
        short = re.sub(r"\s+", " ", short).strip() or None
    rec["subject"] = {
        "kind": "org",
        "ogrn": _digits(m_ogrn.group(1)) if m_ogrn else None,
        "inn": inn,
        "kpp": _digits(_value_after(lines, "КПП юридического лица") or "") or None,
        "name_full": name,
        "name_short": short,
    }
    # ОКВЭД основной
    okved_sec = _section_slice(
        lines, ["Сведения об основном виде"],
        ["Сведения о дополнительных видах", "Сведения о правопреемник", "Сведения о записях"],
    )
    okved_val = _text_after(okved_sec, "Код и наименование вида деятельности")
    if okved_val:
        rec["subject"]["okved_main"] = _split_okved(okved_val)
    # Статус (прекращение)
    if "Сведения о прекращении" in text:
        rec["subject"]["status"] = {
            "terminated": True,
            "method": _text_after(
                _section_slice(lines, ["Сведения о прекращении"], _SECTION_HEADERS),
                "Способ прекращения"),
        }

    # Руководитель (ЕИО) — физлицо или управляющая организация
    dir_sec = _section_slice(
        lines, ["Сведения о лице, имеющем право без доверенности"],
        ["Сведения об уставном", "Сведения об участниках", "Сведения об учредителях",
         "Сведения о единственном акционере", "Сведения об акционер", "Сведения об учете"],
    )
    if dir_sec:
        fio = _fio_triple(dir_sec)
        if fio:
            rec["directors"].append({
                "fio": fio,
                "inn": _digits(_value_after(dir_sec, "ИНН") or "") or None,
                "post": _value_after(dir_sec, "Должность"),
            })
        else:
            org = _ogrn_inn_name(dir_sec)
            if org.get("ogrn") or org.get("name"):
                rec["managing_orgs"].append(org)

    # Учредители / участники / акционеры (в т.ч. единственный акционер АО,
    # иностранный учредитель: «Страна происхождения» + иностр. рег. номер).
    found_sec = _section_slice(
        lines,
        ["Сведения об участниках", "Сведения об учредителях",
         "Сведения о единственном акционере", "Сведения об акционере",
         "Сведения об акционерах"],
        ["Сведения об учете в налоговом", "Сведения о регистрации",
         "Сведения о видах", "Сведения о держателе реестра"],
    )
    if found_sec:
        fio = _fio_triple(found_sec)
        share = _value_after(found_sec, "Размер доли (в процентах)")
        nominal = _value_after(found_sec, "Номинальная стоимость доли")
        country = _value_after(found_sec, "Страна происхождения")
        item: dict[str, Any] = {}
        if fio:
            item = {"kind": "person", "fio": fio,
                    "inn": _digits(_value_after(found_sec, "ИНН") or "") or None}
        else:
            name = _text_after(found_sec, "Полное наименование") \
                or _text_after(found_sec, "Наименование")
            inn = _digits(_value_after(found_sec, "ИНН") or "") or None
            ogrn = _digits(_value_after(found_sec, "ОГРН") or "") or None
            if inn or ogrn or name:
                item = {"kind": "legal_foreign" if country else "legal",
                        "ogrn": ogrn, "inn": inn, "name": name}
                if country:
                    item["country"] = country
                    item["foreign_reg"] = _value_after(found_sec, "Регистрационный номер")
        if item:
            if share:
                item["share_percent"] = parse_number(share)
            if nominal:
                item["share_nominal"] = parse_number(nominal)
            rec["founders"].append(item)

    # Правопреемник / правопредшественник
    for marker, key in (("Сведения о правопреемник", "successors"),
                        ("Сведения о правопредшественник", "predecessors")):
        sec = _section_slice(lines, [marker], _SECTION_HEADERS)
        if sec:
            org = _ogrn_inn_name(sec)
            if org.get("ogrn") or org.get("name"):
                rec[key].append(org)


def _parse_egrip_text(lines: list[str], rec: dict) -> None:
    text = "\n".join(lines)
    m_ogrnip = _RE_OGRNIP.search(text)
    m_inn = _RE_INN.search(text)
    rec["subject"] = {
        "kind": "person",
        "ogrnip": _digits(m_ogrnip.group(1)) if m_ogrnip else None,
        "inn": _digits(m_inn.group(1)) if m_inn else None,
        "fio": _fio_triple(lines) or _header_fio(lines),
        "gender": _value_after(lines, "Пол"),
        "citizenship": _value_after(lines, "Гражданство"),
    }
    okved_sec = _section_slice(
        lines, ["Сведения об основном виде"],
        ["Сведения о дополнительных видах", "Сведения о записях"],
    )
    okved_val = _text_after(okved_sec, "Код и наименование вида деятельности")
    if okved_val:
        rec["subject"]["okved_main"] = _split_okved(okved_val)
    if "прекрати" in text.lower() or "Сведения о прекращении" in text:
        rec["subject"]["status"] = {"terminated": True}


def _header_name(lines: list[str], after: str) -> Optional[str]:
    """Имя/наименование сразу после интро-строки ('о юридическом лице')."""
    for i, ln in enumerate(lines):
        if after in ln:
            for ln2 in lines[i + 1: i + 3]:
                s = ln2.strip()
                if s and "наименование" not in s.lower():
                    return s
    return None


def _header_fio(lines: list[str]) -> Optional[dict]:
    """ФИО ИП из шапки (строка после 'об индивидуальном предпринимателе')."""
    name = _header_name(lines, "индивидуальном предпринимателе")
    if not name:
        return None
    parts = name.split()
    if len(parts) >= 3:
        return {"last": parts[0], "first": parts[1], "middle": " ".join(parts[2:])}
    return {"last": name, "first": None, "middle": None}


def _split_okved(value: str) -> dict:
    """'68.1 Покупка и продажа…' → {code, name}. Имя может быть на след. строках."""
    m = re.match(r"\s*([\d.]+)\s+(.*)", value)
    code = m.group(1) if m else None
    name = (m.group(2) if m else value).strip()
    return {"code": code, "name": name or None}


# ── Точка входа ──────────────────────────────────────────────────────────────
def parse_text(text: str, *, file: Optional[str] = None) -> dict[str, Any]:
    """Распарсить ТЕКСТ PDF-выписки → нормализованная запись.

    Бросает ValueError, если текст не опознан как выписка ЕГРЮЛ/ЕГРИП.
    """
    registry = detect_registry(text)
    if registry is None:
        raise ValueError("Текст не опознан как PDF-выписка ЕГРЮЛ/ЕГРИП")
    lines = _norm(_strip_noise([l.rstrip() for l in text.splitlines()]))
    rec = empty_record(registry)
    rec["source"] = {
        "system": f"ФНС-{registry}-PDF",
        "confidence": 0.8,  # текст из PDF — ниже доверие, чем к XML
        "file": file,
    }
    (_parse_egrul_text if registry == "ЕГРЮЛ" else _parse_egrip_text)(lines, rec)
    return {"format": {"registry": registry, "source": "pdf"}, "records": [rec]}


def parse_pdf(pdf_path: Path | str) -> dict[str, Any]:
    """Извлечь текст PDF и распарсить → нормализованная запись."""
    pdf_path = Path(pdf_path)
    return parse_text(extract_text(pdf_path), file=pdf_path.name)
