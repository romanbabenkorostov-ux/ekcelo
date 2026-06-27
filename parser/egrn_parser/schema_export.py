"""
egrn_parser/schema_export.py — экспорт внутренней БД парсера в C2-формат
(`schema/egrn_current_schema.sql`). ADR-007.

C2 — канонический контракт обмена с бэкендом (решение заказчика 2026-06-09).
Внутренняя схема парсера (`egrn_parser/db/schema.sql`) богаче/иная; здесь — слой
перевода §1–§5 + копия §6 (ЭТП-слой уже C2-нативный).

Маппинг (полное пояснение — `obsidian/Decisions/ADR-007-pkg-schema-to-c2-export.md`):
  objects            ← building_objects ∪ land_objects
  entity_registry    ← entity_registry (подмножество; PK inn)
  rights             ← rights[right_category='right'] (+ right_holders.inn)
  object_restrictions← rights[right_category∈encumbrance/restriction]
  extracts           ← extracts
  §6 (object_etp_profile/lots/lot_items) — копируются как есть (C2-нативные)

Устойчив к отсутствию исходных таблиц/колонок (graceful skip).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

_C2_SCHEMA = "egrn_current_schema.sql"


def _find_c2_schema() -> Path:
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1], here.parents[1].parent):
        p = base / "schema" / _C2_SCHEMA
        if p.exists():
            return p
    raise FileNotFoundError(f"не найден {_C2_SCHEMA}")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _g(row: dict, *keys: str) -> Any:
    """Первое непустое значение по списку ключей."""
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def export_to_c2(src: str | sqlite3.Connection, out_path: str | Path) -> dict[str, int]:
    """Экспортировать БД парсера `src` в C2-`out_path`. Возвращает счётчики строк."""
    own = isinstance(src, (str, Path))
    sconn = sqlite3.connect(str(src)) if own else src
    sconn.row_factory = sqlite3.Row

    out = Path(out_path)
    if out.exists():
        out.unlink()
    dst = sqlite3.connect(str(out))
    dst.executescript(_find_c2_schema().read_text(encoding="utf-8"))
    dst.execute("PRAGMA foreign_keys=OFF")           # порядок вставки не критичен

    counts: dict[str, int] = {}
    try:
        counts["objects"] = _export_objects(sconn, dst)
        counts["entity_registry"] = _export_entities(sconn, dst)
        counts["rights"] = _export_rights(sconn, dst)
        counts["object_restrictions"] = _export_restrictions(sconn, dst)
        counts["extracts"] = _export_extracts(sconn, dst)
        for t in ("object_etp_profile", "lots", "lot_items"):   # §6 — как есть
            counts[t] = _copy_table(sconn, dst, t)
        dst.commit()
    finally:
        dst.close()
        if own:
            sconn.close()
    return counts


# ── §1 objects ← building_objects ∪ land_objects ─────────────────────────────
def _export_objects(s: sqlite3.Connection, d: sqlite3.Connection) -> int:
    n = 0
    if _has_table(s, "building_objects"):
        for r in s.execute("SELECT * FROM building_objects"):
            r = dict(r)
            d.execute("INSERT OR IGNORE INTO objects(cad_number, object_type, address, "
                      "area, category, permitted_use, purpose, floors) VALUES(?,?,?,?,?,?,?,?)",
                      (r["cad_number"], _g(r, "object_type") or "building", _g(r, "address"),
                       _g(r, "area"), None, _g(r, "permitted_uses"),
                       _g(r, "purpose"), _g(r, "floors_above_ground", "floors_total")))
            n += 1
    if _has_table(s, "land_objects"):
        for r in s.execute("SELECT * FROM land_objects"):
            r = dict(r)
            d.execute("INSERT OR IGNORE INTO objects(cad_number, object_type, address, "
                      "area, category, permitted_use, purpose, floors) VALUES(?,?,?,?,?,?,?,?)",
                      (r["cad_number"], "land", _g(r, "address"), _g(r, "area"),
                       _g(r, "land_category"), _g(r, "permitted_uses"), None, None))
            n += 1
    return n


# ── §2 entity_registry (PK inn) ──────────────────────────────────────────────
def _export_entities(s: sqlite3.Connection, d: sqlite3.Connection) -> int:
    if not _has_table(s, "entity_registry"):
        return 0
    n = 0
    for r in s.execute("SELECT * FROM entity_registry"):
        r = dict(r)
        inn = _g(r, "inn")
        if not inn:                                  # C2 PK = inn; без ИНН не мапим
            continue
        name = _g(r, "name_full", "name_short") or "н/д"
        d.execute("INSERT OR IGNORE INTO entity_registry(inn, name_full, name_short, "
                  "ogrn, entity_type) VALUES(?,?,?,?,?)",
                  (inn, name, _g(r, "name_short"), _g(r, "ogrn"), _g(r, "entity_type")))
        n += 1
    return n


def _holder_inn(s: sqlite3.Connection, right_id: Any) -> Optional[str]:
    if not _has_table(s, "right_holders"):
        return None
    row = s.execute("SELECT inn FROM right_holders WHERE right_id=? AND inn IS NOT NULL "
                    "ORDER BY holder_id LIMIT 1", (right_id,)).fetchone()
    return row[0] if row else None


# ── §3 rights[right_category='right'] ────────────────────────────────────────
def _export_rights(s: sqlite3.Connection, d: sqlite3.Connection) -> int:
    if not _has_table(s, "rights"):
        return 0
    cols = _cols(s, "rights")
    n = 0
    for r in s.execute("SELECT * FROM rights"):
        r = dict(r)
        if _g(r, "right_category") not in (None, "right"):   # обременения → restrictions
            continue
        cad = _g(r, "object_key_value", "cad_number")
        if not cad:
            continue
        inn = _holder_inn(s, r.get("right_id")) if "right_id" in cols else None
        d.execute("INSERT INTO rights(cad_number, right_type, right_holder_inn, "
                  "share_numerator, share_denominator, registration_number, "
                  "registration_date) VALUES(?,?,?,?,?,?,?)",
                  (cad, _g(r, "right_type", "right_category") or "ownership", inn,
                   _g(r, "share_numerator"), _g(r, "share_denominator"),
                   _g(r, "right_number"), _g(r, "right_date")))
        n += 1
    return n


# ── §5 object_restrictions ← rights[encumbrance|restriction] ─────────────────
def _export_restrictions(s: sqlite3.Connection, d: sqlite3.Connection) -> int:
    if not _has_table(s, "rights"):
        return 0
    n = 0
    for r in s.execute("SELECT * FROM rights WHERE right_category IN ('encumbrance','restriction')"):
        r = dict(r)
        cad = _g(r, "object_key_value", "cad_number")
        if not cad:
            continue
        d.execute("INSERT INTO object_restrictions(cad_number, restrict_type, description, "
                  "registry_number, valid_from, valid_to, basis_doc) VALUES(?,?,?,?,?,?,?)",
                  (cad, _g(r, "right_type", "right_category"),
                   _g(r, "right_type", "right_type_code"), _g(r, "right_number"),
                   _g(r, "valid_from", "right_date"),
                   _g(r, "valid_until", "right_end_date"), _g(r, "basis")))
        n += 1
    return n


# ── §4 extracts ──────────────────────────────────────────────────────────────
def _export_extracts(s: sqlite3.Connection, d: sqlite3.Connection) -> int:
    if not _has_table(s, "extracts"):
        return 0
    n = 0
    for r in s.execute("SELECT * FROM extracts"):
        r = dict(r)
        cad = _g(r, "cad_number")
        if not cad:
            continue
        d.execute("INSERT INTO extracts(extract_number, cad_number, extract_date, "
                  "document_type, raw_json, parser_version) VALUES(?,?,?,?,?,?)",
                  (_g(r, "extract_number"), cad, _g(r, "extract_date") or "",
                   _g(r, "extract_template", "object_class"), None, _g(r, "schema_id")))
        n += 1
    return n


# ── §6 — копия как есть (C2-нативные таблицы) ────────────────────────────────
def _copy_table(s: sqlite3.Connection, d: sqlite3.Connection, table: str) -> int:
    if not _has_table(s, table):
        return 0
    common = sorted(_cols(s, table) & _cols(d, table))
    if not common:
        return 0
    collist = ", ".join(common)
    ph = ", ".join("?" for _ in common)
    n = 0
    for r in s.execute(f"SELECT {collist} FROM {table}"):
        d.execute(f"INSERT OR REPLACE INTO {table}({collist}) VALUES({ph})", tuple(r))
        n += 1
    return n
