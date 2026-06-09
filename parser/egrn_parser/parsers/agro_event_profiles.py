"""
egrn_parser/parsers/agro_event_profiles.py — профили JSON `agro_event.attrs`
и валидатор (ADR-006 §C).

Показатели события агро-поля хранятся в JSON `attrs` (не колонками), профиль —
по `event_type`. Здесь: декларативные профили (required/типы полей) + лёгкий
валидатор без внешних зависимостей. Неизвестные ключи допускаются (модель
events+JSON расширяема), валидируются только известные поля и обязательность.
"""
from __future__ import annotations

import json
from numbers import Real
from typing import Any

# Типы значений: number | text | object | substances (список действующих веществ).
PROFILES: dict[str, dict[str, Any]] = {
    "harvest": {
        "required": ["variety", "volume_kg"],
        "fields": {"variety": "text", "volume_kg": "number", "acidity_g_l": "number",
                   "sugar_brix": "number", "grade": "text", "pass_no": "number"},
    },
    "treatment": {
        "required": ["kind"],
        "fields": {"kind": "text", "preparation": "text",
                   "active_substances": "substances", "target": "text",
                   "machinery": "text"},
    },
    "observation": {
        "required": ["phase"],
        "fields": {"phase": "text", "note": "text", "measures": "object"},
    },
    "phenology": {
        "required": ["phase"],
        "fields": {"phase": "text", "note": "text", "measures": "object"},
    },
    "sowing": {
        "required": ["seeding_rate"],
        "fields": {"seeding_rate": "number", "variety": "text", "depth_cm": "number"},
    },
    # Обобщённая агро-операция (техкарта: вспашка, культивация, подвязка, удобрение…).
    "operation": {
        "required": [],
        "fields": {"work": "text", "code": "text", "phase": "text", "unit": "text",
                   "qty": "number", "unit_cost": "number", "total": "number",
                   "year": "number", "kind": "text", "name": "text",
                   "rate_per_ha": "number", "note": "text"},
    },
}


def _is_number(v: Any) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool)


def _check_value(key: str, value: Any, vtype: str) -> list[str]:
    if vtype == "number" and not _is_number(value):
        return [f"{key}: ожидалось число, получено {type(value).__name__}"]
    if vtype == "text" and not isinstance(value, str):
        return [f"{key}: ожидался текст, получено {type(value).__name__}"]
    if vtype == "object" and not isinstance(value, dict):
        return [f"{key}: ожидался объект, получено {type(value).__name__}"]
    if vtype == "substances":
        return _check_substances(key, value)
    return []


def _check_substances(key: str, value: Any) -> list[str]:
    """active_substances: список {name(текст,обяз.), rate(число,опц.), unit(текст,опц.)}."""
    if not isinstance(value, list):
        return [f"{key}: ожидался список действующих веществ"]
    errs = []
    for i, sub in enumerate(value):
        if not isinstance(sub, dict):
            errs.append(f"{key}[{i}]: ожидался объект")
            continue
        if not isinstance(sub.get("name"), str) or not sub.get("name"):
            errs.append(f"{key}[{i}].name: обязателен непустой текст")
        if "rate" in sub and not _is_number(sub["rate"]):
            errs.append(f"{key}[{i}].rate: ожидалось число")
        if "unit" in sub and not isinstance(sub["unit"], str):
            errs.append(f"{key}[{i}].unit: ожидался текст")
    return errs


def validate_event_attrs(event_type: str, attrs: Any) -> list[str]:
    """Валидировать attrs события. Возвращает список ошибок ([] = валидно).

    `attrs` может быть dict или JSON-строкой. Неизвестный event_type → ошибка.
    Неизвестные ключи в attrs допускаются (не ошибка)."""
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except (ValueError, TypeError):
            return ["attrs: невалидный JSON"]
    if not isinstance(attrs, dict):
        return ["attrs: ожидался объект (dict)"]
    profile = PROFILES.get(event_type)
    if profile is None:
        return [f"event_type: неизвестный тип '{event_type}' "
                f"(ожидается один из {sorted(PROFILES)})"]
    errs: list[str] = []
    for req in profile["required"]:
        if attrs.get(req) is None:
            errs.append(f"{req}: обязательное поле отсутствует")
    for key, vtype in profile["fields"].items():
        if key in attrs and attrs[key] is not None:
            errs.extend(_check_value(key, attrs[key], vtype))
    return errs


def is_valid_event(event_type: str, attrs: Any) -> bool:
    return not validate_event_attrs(event_type, attrs)
