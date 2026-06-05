"""Единый классификатор типа ограничения объекта — общий для PDF и XML парсеров.

Раньше pdf_parser и xml_parser определяли czuit_zone/okn_territory независимо и
расходились на одном и том же отчёте. Теперь оба зовут classify_restriction_type().
"""
from __future__ import annotations

# Маркеры территории объекта культурного наследия (ОКН).
OKN_MARKERS = (
    "культурного наследия",
    "объект культурного наследия",
    "памятник",
    "достопримечательное место",
)

# Явные маркеры ЗОУИТ (зона с особыми условиями использования территории).
ZOUIT_MARKERS = (
    "зона с особыми условиями",
    "охранная зона",
    "санитарно-защитн",
    "приаэродром",
    "водоохранн",
)


def classify_restriction_type(*texts: str | None) -> str:
    """Вернуть 'okn_territory' | 'czuit_zone' по совокупности текстовых фрагментов
    (вид/наименование, тип, описание). ОКН имеет приоритет; иначе — ЗОУИТ по умолчанию."""
    blob = " ".join(t for t in texts if t).lower()
    if any(m in blob for m in OKN_MARKERS):
        return "okn_territory"
    return "czuit_zone"
