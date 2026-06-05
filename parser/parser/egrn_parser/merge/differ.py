"""
egrn_parser/merge/differ.py — сравнение полей объектов для diff-режима.

Возвращает словарь изменённых полей: {"field": [old_value, new_value]}.
"""

from __future__ import annotations

import json
from typing import Any

# Поля-JSON-массивы: сравниваются канонически (порядок элементов НЕ важен),
# чтобы повторный парсинг одного отчёта (PDF↔XML, разный порядок) не давал ложный diff.
JSON_LIST_FIELDS = frozenset({
    "object_restrictions", "permitted_uses", "land_cad_numbers",
    "old_numbers", "nested_objects",
})


# Значимые поля для diff (ТЗ раздел 7.6)
SIGNIFICANT_LAND_FIELDS = [
    "area", "cadastral_value", "land_category", "permitted_uses",
    "lifecycle_status", "address", "object_restrictions",
]

SIGNIFICANT_BUILDING_FIELDS = [
    "area", "cadastral_value", "purpose", "name",
    "floors_total", "floors_above_ground", "underground_floors",
    "lifecycle_status", "address", "object_restrictions",
    "land_cad_numbers", "parent_cad_number",
]


def diff_objects(old: dict, new: dict, object_class: str = "building") -> dict[str, list]:
    """
    Сравнить два словаря объектов (старый и новый).
    Возвращает dict {field: [old_value, new_value]} только для изменённых полей.
    """
    fields = (
        SIGNIFICANT_LAND_FIELDS if object_class == "land"
        else SIGNIFICANT_BUILDING_FIELDS
    )
    changed: dict[str, list] = {}
    for field in fields:
        old_val = old.get(field)
        new_val = new.get(field)
        if field in JSON_LIST_FIELDS:
            if _json_list_differ(old_val, new_val):
                changed[field] = [old_val, new_val]
        elif _values_differ(old_val, new_val):
            changed[field] = [old_val, new_val]
    return changed


def _values_differ(a: Any, b: Any) -> bool:
    """Проверить, отличаются ли два значения."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    # Числа: сравниваем с допуском 0.01%
    if isinstance(a, float) and isinstance(b, float):
        if a == 0 and b == 0:
            return False
        return abs(a - b) / max(abs(a), abs(b), 1e-9) > 0.0001
    return str(a).strip() != str(b).strip()


def _canonical_json_list(v: Any):
    """Привести JSON-массив (строка или list) к каноничному виду: отсортированный
    список элементов, сериализованных с sort_keys. Порядок и пробелы не важны."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            v = json.loads(s)
        except (ValueError, TypeError):
            return s  # не JSON — сравниваем как строку
    if isinstance(v, list):
        if not v:
            return None  # пустой массив ≡ отсутствие ограничений
        return sorted(json.dumps(el, ensure_ascii=False, sort_keys=True, default=str) for el in v)
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)


def _json_list_differ(a: Any, b: Any) -> bool:
    """Сравнение JSON-массивов без учёта порядка элементов (детерминированно)."""
    ca, cb = _canonical_json_list(a), _canonical_json_list(b)
    if ca is None and cb is None:
        return False
    return ca != cb


def format_diff_report(cad_number: str, name: str, changed: dict[str, list]) -> str:
    """Форматировать отчёт об изменениях для вывода в консоль (ТЗ 13.3)."""
    lines = [f"\n[DIFF] Объект {cad_number} (\"{name}\")"]
    lines.append(f"  {'Поле':<30} | {'В БД':<30} | {'В новой выписке':<30}")
    lines.append("  " + "-" * 95)
    for field, (old_val, new_val) in changed.items():
        ov = str(old_val)[:28] if old_val is not None else "—"
        nv = str(new_val)[:28] if new_val is not None else "—"
        lines.append(f"  {field:<30} | {ov:<30} | {nv:<30}")
    return "\n".join(lines)
