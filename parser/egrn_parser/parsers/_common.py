"""
egrn_parser/parsers/_common.py — общие утилиты для всех парсеров.

Нормализация дат, кадастровых номеров, ИНН/ОГРН, числовых значений.
"""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  Регулярные выражения
# ─────────────────────────────────────────────────────────────────────────────

# Полный кадастровый номер: NN:NN:NNNNNN:N (6–7 цифр в третьем сегменте)
CAD_NUMBER_RE = re.compile(r"\b(\d{2}:\d{2}:\d{6,7}:\d+)\b")

# Частичный кадастровый номер (только последний сегмент)
CAD_FRAGMENT_RE = re.compile(r":(\d{3,5})\b")

# ИНН (10 или 12 цифр)
INN_RE = re.compile(r"\bИНН[:\s]+(\d{10,12})\b")

# ОГРН (13 или 15 цифр)
OGRN_RE = re.compile(r"\bОГРН[:\s]+(\d{13,15})\b")

# Дата в формате DD.MM.YYYY
DATE_RU_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")

# Дата и время DD.MM.YYYY HH:MM:SS
DATETIME_RU_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})")

# ISO дата YYYY-MM-DD
DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Доля в виде числитель/знаменатель
SHARE_RE = re.compile(r"(\d+)\s*/\s*(\d+)")

# Число с точкой или запятой как десятичным разделителем
NUMBER_RE = re.compile(r"[\d\s]+[.,]?\d*")

# Срок: с DD.MM.YYYY по DD.MM.YYYY
SROK_RE_1 = re.compile(r"с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})")
# Срок: с DD.MM.YYYY сроком на N лет
SROK_RE_2 = re.compile(r"с\s+(\d{2}\.\d{2}\.\d{4})\s+сроком\s+на\s+(\d+)\s+лет")
# Срок: с DD.MM.YYYY N лет
SROK_RE_3 = re.compile(r"с\s+(\d{2}\.\d{2}\.\d{4})\s+(\d+)\s*лет")
# Срок с DD.MM.YYYY (без конца)
SROK_RE_4 = re.compile(r"с\s+(\d{2}\.\d{2}\.\d{4})")


# ─────────────────────────────────────────────────────────────────────────────
#  Нормализация дат
# ─────────────────────────────────────────────────────────────────────────────

def parse_date_ru(text: str) -> Optional[str]:
    """
    Распознать дату формата DD.MM.YYYY → ISO YYYY-MM-DD.
    Возвращает None если не найдена.
    Обрабатывает вариант «01.01.2026г.» (без пробела перед «г»).
    """
    # Заменяем «г.» / «г» суффикс чтобы \b работал корректно
    cleaned = re.sub(r"(\d{4})г\.?", r"\1 ", text)
    m = DATE_RU_RE.search(cleaned)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        try:
            datetime(int(y), int(mo), int(d))
            return f"{y}-{mo}-{d}"
        except ValueError:
            return None
    return None


def parse_datetime_ru(text: str) -> Optional[str]:
    """
    Распознать дату+время DD.MM.YYYY HH:MM:SS → ISO YYYY-MM-DDTHH:MM:SS.
    Возвращает None если не найдено.
    """
    m = DATETIME_RU_RE.search(text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        h, mi, s = m.group(4), m.group(5), m.group(6)
        try:
            datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
            return f"{y}-{mo}-{d} {h}:{mi}:{s}"  # пробел вместо T — Excel-совместимость
        except ValueError:
            return None
    return None


def parse_date_any(text: str) -> Optional[str]:
    """Попытаться распознать дату в любом формате (ISO или DD.MM.YYYY).
    
    Поддерживает:
    - "2002-12-30T00:00:00+03:00" (XML с timezone offset) → "2002-12-30"
    - "2002-12-30T00:00:00"       (ISO datetime без TZ)  → "2002-12-30"
    - "2002-12-30"                (ISO date)              → "2002-12-30"
    - "30.12.2002"                (DD.MM.YYYY)            → "2002-12-30"
    - "30.12.2002 12:26:19"       (DD.MM.YYYY HH:MM:SS)  → "2002-12-30T12:26:19"
    """
    if not text:
        return None
    t = text.strip()
    
    # ISO datetime с timezone: 2002-12-30T00:00:00+03:00 → 2002-12-30
    # ISO datetime без TZ: 2002-12-30T00:00:00 → 2002-12-30
    iso_dt = re.match(
        r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2}:\d{2})(?:[+\-]\d{2}:\d{2}|Z)?",
        t
    )
    if iso_dt:
        y, mo, d, time_part = iso_dt.group(1), iso_dt.group(2), iso_dt.group(3), iso_dt.group(4)
        try:
            datetime(int(y), int(mo), int(d))
            # Если время не 00:00:00 — возвращаем полный datetime
            if time_part != "00:00:00":
                return f"{y}-{mo}-{d} {time_part}"  # пробел вместо T — Excel-совместимость
            return f"{y}-{mo}-{d}"
        except ValueError:
            pass

    # Простая ISO дата: 2002-12-30
    iso = DATE_ISO_RE.search(t)
    if iso:
        y, mo, d = iso.group(1), iso.group(2), iso.group(3)
        try:
            datetime(int(y), int(mo), int(d))
            return f"{y}-{mo}-{d}"
        except ValueError:
            pass

    # DD.MM.YYYY [HH:MM:SS]
    ru = re.match(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}:\d{2}:\d{2}))?", t)
    if ru:
        d, mo, y = ru.group(1), ru.group(2), ru.group(3)
        time_part = ru.group(4)
        try:
            datetime(int(y), int(mo), int(d))
            if time_part:
                return f"{y}-{mo}-{d} {time_part}"  # пробел для Excel
            return f"{y}-{mo}-{d}"
        except ValueError:
            pass

    return parse_date_ru(text)


def add_years_to_date(date_str: str, years: int) -> Optional[str]:
    """Прибавить N лет к дате формата YYYY-MM-DD."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        new_dt = dt.replace(year=dt.year + years)
        return new_dt.strftime("%Y-%m-%d")
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Парсинг срока (valid_from / valid_until / valid_duration_years)
# ─────────────────────────────────────────────────────────────────────────────

def parse_term(text: str) -> dict:
    """
    Разобрать срок ограничения/обременения. Четыре формата из ТЗ раздел 5.4.4.
    Возвращает dict с ключами: valid_from, valid_until, valid_duration_years,
    lease_term_description.
    """
    result = {
        "valid_from":          None,
        "valid_until":         None,
        "valid_duration_years":None,
        "lease_term_description": None,
    }
    if not text:
        return result

    text_stripped = text.strip()

    # Бессрочно
    if re.search(r"бессрочно|на неопределённый срок|не установлен", text_stripped, re.IGNORECASE):
        result["lease_term_description"] = "бессрочно"
        return result

    # Формат 1: с DD.MM.YYYY по DD.MM.YYYY
    m = SROK_RE_1.search(text_stripped)
    if m:
        result["valid_from"]  = parse_date_ru(m.group(1))
        result["valid_until"] = parse_date_ru(m.group(2))
        return result

    # Формат 2: с DD.MM.YYYY сроком на N лет
    m = SROK_RE_2.search(text_stripped)
    if m:
        vf = parse_date_ru(m.group(1))
        n  = int(m.group(2))
        result["valid_from"]           = vf
        result["valid_until"]          = add_years_to_date(vf, n) if vf else None
        result["valid_duration_years"] = n
        return result

    # Формат 3: с DD.MM.YYYY N лет
    m = SROK_RE_3.search(text_stripped)
    if m:
        vf = parse_date_ru(m.group(1))
        n  = int(m.group(2))
        result["valid_from"]           = vf
        result["valid_until"]          = add_years_to_date(vf, n) if vf else None
        result["valid_duration_years"] = n
        return result

    # Формат 4: с DD.MM.YYYY (открытый срок)
    m = SROK_RE_4.search(text_stripped)
    if m:
        result["valid_from"] = parse_date_ru(m.group(1))
        return result

    # Ничего не нашли — сохраняем как текст
    result["lease_term_description"] = text_stripped
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Кадастровые номера
# ─────────────────────────────────────────────────────────────────────────────

def normalize_cad_number(text: str) -> Optional[str]:
    """Извлечь и нормализовать кадастровый номер из строки."""
    if not text:
        return None
    m = CAD_NUMBER_RE.search(text.replace(" ", ""))
    return m.group(1) if m else None


def extract_all_cad_numbers(text: str) -> list[str]:
    """Извлечь все кадастровые номера из текста."""
    return list(dict.fromkeys(CAD_NUMBER_RE.findall(text)))


def cad_quarter(cad_number: str) -> Optional[str]:
    """Вернуть кадастровый квартал (без последнего сегмента)."""
    parts = cad_number.rsplit(":", 1)
    return parts[0] if len(parts) == 2 else None


# ─────────────────────────────────────────────────────────────────────────────
#  ИНН / ОГРН
# ─────────────────────────────────────────────────────────────────────────────

def extract_inn(text: str) -> Optional[str]:
    """Извлечь ИНН из строки."""
    m = INN_RE.search(text)
    return m.group(1) if m else None


def extract_ogrn(text: str) -> Optional[str]:
    """Извлечь ОГРН из строки."""
    m = OGRN_RE.search(text)
    return m.group(1) if m else None


def classify_holder_type(name: str, inn: Optional[str]) -> str:
    """
    Определить тип правообладателя по имени и ИНН.
    Возвращает код из HOLDER_TYPES.
    """
    # ИНН из 12 цифр → физлицо (проверяем ДО имени)
    if inn and len(inn) == 12:
        return "individual"
    # ИНН из 10 цифр → юрлицо
    if inn and len(inn) == 10:
        return "legal_entity"

    if not name:
        return "unknown"
    name_lower = name.lower()
    # Публичные субъекты
    if any(kw in name_lower for kw in ("российская федерация", "субъект рф", "субъект российской")):
        return "public"
    # Муниципальные
    if any(kw in name_lower for kw in ("муниципальное образование", "городской округ", "поселение")):
        return "municipal"
    # ЮЛ
    if any(kw in name_lower for kw in ("ооо", "оао", "зао", " ао ", "пао", "гуп", "муп", "фгуп",
                                        "унитарное", "акционерное", "общество с ограниченной",
                                        "некоммерческая", "учреждение", "предприятие")):
        return "legal_entity"
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
#  Числовые значения
# ─────────────────────────────────────────────────────────────────────────────

def parse_number(text: str) -> Optional[float]:
    """Разобрать число из строки (точка или запятая как разделитель)."""
    if not text:
        return None
    cleaned = re.sub(r"[\s\u00a0]", "", str(text)).replace(",", ".")
    # Убрать всё кроме цифр, точки и минуса
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_share(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Разобрать долю вида 'N/M' или '47/100'.
    Возвращает (числитель, знаменатель) или (None, None).
    """
    m = SHARE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные
# ─────────────────────────────────────────────────────────────────────────────

def normalize_whitespace(text: str) -> str:
    """Удалить лишние пробелы и переносы строк."""
    return re.sub(r"\s+", " ", text).strip()


def is_absent(text: str) -> bool:
    """Проверить, является ли значение «данные отсутствуют» или пустым."""
    if not text:
        return True
    normalized = normalize_whitespace(text).lower()
    return normalized in (
        "данные отсутствуют",
        "не зарегистрировано",
        "отсутствуют",
        "нет данных",
        "-",
        "",
    )


def clean_value(text: str) -> Optional[str]:
    """Вернуть None если значение «отсутствующее», иначе нормализовать пробелы."""
    if is_absent(text):
        return None
    return normalize_whitespace(text)
