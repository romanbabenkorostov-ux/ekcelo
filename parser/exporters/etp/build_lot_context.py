"""build_lot_context: сборка ctx dict из БД для одного лота.

Контракт ctx — `docs/etp_export/SPEC_etp_export.md` §3
(meta / identity / location / building / layout_and_condition / legal / risks / extras).

Источники:
- `lots` + `lot_items` — состав лота и метаданные процедуры/платформ.
- `objects` — ЕГРН-поля для primary КН (identity, частично location).
- `rights` + `entity_registry` — правообладатель и тип права.
- `object_restrictions` — обременения.
- `object_etp_profile` — гэп-поля (не-ЕГРН слой, ADR-001).

Stage 1: собирается ctx для primary_cad_number лота. Multi-cad лоты
получают `extras.notes` с перечнем КН-членов; полное составное описание —
в следующем PR (text_render).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from parser.exporters.etp.address_parser import parse_address
from parser.exporters.etp.encumbrance_mapper import map_encumbrance


# ─────────────────────────────────────────────────────────────────────────────
#  Публичный API
# ─────────────────────────────────────────────────────────────────────────────

def build_lot_context(
    conn: sqlite3.Connection,
    lot_id: str,
    *,
    platform: str = "torgi.gov.ru",
    platform_mode: str = "short",
    target_cad_number: str | None = None,
) -> dict[str, Any]:
    """Собрать ctx для лота.

    Args:
        conn: открытое соединение с БД (миграция 0001 применена).
        lot_id: идентификатор лота из таблицы `lots`.
        platform: целевая ЭТП ('torgi.gov.ru' | 'roseltorg.ru' | 'sberbank-ast.ru').
        platform_mode: 'short' | 'full'.
        target_cad_number: КН для identity-секции (по умолчанию — `lots.primary_cad_number`).

    Returns:
        Dict, совместимый с SPEC §3.

    Raises:
        LookupError: если лот не найден.
        ValueError: если у лота нет items и не передан target_cad_number.
    """
    conn.row_factory = sqlite3.Row

    lot = _fetch_lot(conn, lot_id)
    items = _fetch_lot_items(conn, lot_id)
    cad = target_cad_number or lot["primary_cad_number"] or (items[0]["cad_number"] if items else None)
    if not cad:
        raise ValueError(f"Lot {lot_id!r} has no items and no target_cad_number provided")

    obj = _fetch_object(conn, cad)
    profile = _fetch_profile(conn, cad)
    rights = _fetch_rights(conn, cad)
    restrictions = _fetch_restrictions(conn, cad)

    return {
        "meta": _build_meta(lot, obj, platform, platform_mode),
        "identity": _build_identity(obj),
        "location": _build_location(obj, profile),
        "building": _build_building(obj, profile),
        "layout_and_condition": _build_layout(profile),
        "legal": _build_legal(rights, restrictions, profile),
        "risks": _build_risks(profile),
        "extras": _build_extras(profile, items, cad),
        "generated_text": {"short": None, "full": None, "version": 1},
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Загрузчики из БД
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_lot(conn: sqlite3.Connection, lot_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM lots WHERE lot_id = ?", (lot_id,)).fetchone()
    if not row:
        raise LookupError(f"Lot not found: {lot_id!r}")
    return row


def _fetch_lot_items(conn: sqlite3.Connection, lot_id: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT cad_number, role, ord FROM lot_items WHERE lot_id = ? ORDER BY ord",
        (lot_id,),
    ))


def _fetch_object(conn: sqlite3.Connection, cad: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM objects WHERE cad_number = ?", (cad,)).fetchone()


def _fetch_profile(conn: sqlite3.Connection, cad: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM object_etp_profile WHERE cad_number = ?", (cad,)).fetchone()


def _fetch_rights(conn: sqlite3.Connection, cad: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT r.*, e.name_full, e.name_short, e.entity_type "
        "FROM rights r LEFT JOIN entity_registry e ON r.right_holder_inn = e.inn "
        "WHERE r.cad_number = ? ORDER BY r.registration_date DESC",
        (cad,),
    ))


def _fetch_restrictions(conn: sqlite3.Connection, cad: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM object_restrictions WHERE cad_number = ? "
        "AND (valid_to IS NULL OR valid_to >= date('now')) "
        "ORDER BY valid_from DESC",
        (cad,),
    ))


# ─────────────────────────────────────────────────────────────────────────────
#  Сборщики секций ctx
# ─────────────────────────────────────────────────────────────────────────────

# ЕГРН object_type → SPEC object_type
_OBJECT_TYPE_MAP = {
    "land": "land",
    "building": "building",
    "construction": "building",
    "flat": "flat",
    "room": "non_residential",
}


def _build_meta(lot: sqlite3.Row, obj: sqlite3.Row | None, platform: str, mode: str) -> dict:
    return {
        "platform": platform,
        "platform_mode": mode,
        "object_type": _OBJECT_TYPE_MAP.get(obj["object_type"] if obj else "", "complex"),
        "deal_type": lot["deal_type"],
        "procedure_type": lot["procedure_type"],
        "locale": "ru-RU",
    }


def _build_identity(obj: sqlite3.Row | None) -> dict:
    if not obj:
        return {"title": None, "purpose": None, "area_total_sqm": None,
                "area_land_sqm": None, "floor": None, "floors_total": None,
                "cadastral_number": None}
    object_type = obj["object_type"]
    is_land = object_type == "land"
    title = _title_for(object_type)
    return {
        "title": title,
        "purpose": obj["purpose"],
        "area_total_sqm": None if is_land else obj["area"],
        "area_land_sqm": obj["area"] if is_land else None,
        "floor": obj["floors"] if object_type in ("flat", "room") else None,
        "floors_total": obj["floors"] if object_type in ("building", "construction") else None,
        "cadastral_number": obj["cad_number"],
    }


_TITLE_MAP = {
    "land": "Земельный участок",
    "building": "Здание",
    "construction": "Сооружение",
    "flat": "Квартира",
    "room": "Нежилое помещение",
}


def _title_for(object_type: str | None) -> str:
    return _TITLE_MAP.get(object_type or "", "Объект недвижимости")


def _build_location(obj: sqlite3.Row | None, profile: sqlite3.Row | None) -> dict:
    extra = _parse_json(profile, "location_extra") if profile else {}
    extra = extra or {}
    address_raw = obj["address"] if obj else None
    components = parse_address(address_raw)
    return {
        **components,
        "address_raw": address_raw,
        "landmark": extra.get("landmark"),
        "transport_access": extra.get("transport_access"),
        "environment_short": extra.get("environment_short"),
    }


def _build_building(obj: sqlite3.Row | None, profile: sqlite3.Row | None) -> dict:
    extra = _parse_json(profile, "building_extra") if profile else None
    if extra is None:
        # Объект без здания (например, земельный участок) или нет данных.
        return {}
    return {
        "building_type": None,
        "floors_total": obj["floors"] if obj and obj["object_type"] in ("building", "construction") else None,
        "year_built": None,
        "renovation_year": extra.get("renovation_year"),
        "wear_degree": extra.get("wear_degree"),
        "engineering": extra.get("engineering") or {},
        "amenities": extra.get("amenities") or [],
    }


def _build_layout(profile: sqlite3.Row | None) -> dict:
    layout = _parse_json(profile, "layout") if profile else None
    if not layout:
        return {}
    return {
        "layout_type": layout.get("layout_type"),
        "rooms_count": layout.get("rooms_count"),
        "ceiling_height_m": layout.get("ceiling_height_m"),
        "finish_level": layout.get("finish_level"),
        "finish_state": layout.get("finish_state"),
        "windows": layout.get("windows"),
        "entry_group": layout.get("entry_group"),
        "current_condition_comment": layout.get("current_condition_comment"),
    }


def _build_legal(
    rights: list[sqlite3.Row],
    restrictions: list[sqlite3.Row],
    profile: sqlite3.Row | None,
) -> dict:
    extra = _parse_json(profile, "legal_extra") if profile else {}
    extra = extra or {}
    primary_right = rights[0] if rights else None
    return {
        "right_type": primary_right["right_type"] if primary_right else None,
        "right_holder": (primary_right["name_full"] if primary_right and primary_right["name_full"]
                         else None),
        "basis_type": primary_right["registration_number"] if primary_right and primary_right["registration_number"] else None,
        "encumbrances": [_encumbrance_from_row(r) for r in restrictions],
        "use_type_fact": extra.get("use_type_fact"),
        "use_type_permitted": None,  # gap §10 — заполнится через NSPD enrichment (следующий PR)
        "zoning": extra.get("zoning"),
        "special_restrictions": extra.get("special_restrictions") or [],
    }


def _encumbrance_from_row(row: sqlite3.Row) -> dict:
    return {
        "type": row["restrict_type"],
        "description": row["description"],
        "influence": map_encumbrance(row["restrict_type"]),
    }


def _build_risks(profile: sqlite3.Row | None) -> dict:
    risks = _parse_json(profile, "risks") if profile else None
    if not risks:
        return {"technical_risks": [], "legal_risks": [], "location_risks": [], "other_risks": []}
    return {
        "technical_risks": risks.get("technical_risks") or [],
        "legal_risks": risks.get("legal_risks") or [],
        "location_risks": risks.get("location_risks") or [],
        "other_risks": risks.get("other_risks") or [],
    }


def _build_extras(
    profile: sqlite3.Row | None,
    items: list[sqlite3.Row],
    primary_cad: str,
) -> dict:
    extra = _parse_json(profile, "extras") if profile else {}
    extra = extra or {}
    notes_parts: list[str] = []
    if extra.get("notes"):
        notes_parts.append(extra["notes"])

    other_items = [it for it in items if it["cad_number"] != primary_cad]
    if other_items:
        membership = ", ".join(f"{it['cad_number']} ({it['role']})" for it in other_items)
        notes_parts.append(f"В состав лота также входят: {membership}.")

    return {
        "equipment": extra.get("equipment") or [],
        "furniture": extra.get("furniture"),
        "advantages": extra.get("advantages") or [],
        "notes": "\n\n".join(notes_parts) if notes_parts else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(row: sqlite3.Row | None, column: str) -> Any:
    """Безопасный json.loads из колонки sqlite3.Row. None / пустую строку → None."""
    if row is None:
        return None
    try:
        raw = row[column]
    except (IndexError, KeyError):
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
