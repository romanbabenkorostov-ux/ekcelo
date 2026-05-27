"""
tests/test_etp_profile_schema.py — DDL миграции 0001_etp_profile.

Покрывает:
- Применение `schema/migrations/0001_etp_profile.sql` к свежей БД.
- Вставку всех записей из фикстуры `tests/fixtures/etp/object_etp_profile_sample.json`.
- CHECK-constraint'ы (source, confidence, deal_type, role, lot_id charset/длина).
- FOREIGN KEY каскадные.

См. ADR-001, SPEC §5, CORRESPONDENCE/025+026.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_SQL = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
FIXTURE_JSON = Path(__file__).resolve().parent / "fixtures" / "etp" / "object_etp_profile_sample.json"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """In-memory БД с минимальной таблицей objects + применённая миграция 0001."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    # Минимальный objects(cad_number) — нужен для FK из новых таблиц.
    conn.execute("CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT)")
    conn.executescript(MIGRATION_SQL.read_text(encoding="utf-8"))
    return conn


def _insert_object(conn: sqlite3.Connection, cad: str, obj_type: str = "room") -> None:
    conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, ?)", (cad, obj_type))


def _json(value) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


# ─────────────────────────────────────────────────────────────────────────────
#  Базовый DDL
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_creates_three_tables():
    conn = _make_db()
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"object_etp_profile", "lots", "lot_items"}.issubset(tables)


def test_migration_creates_indexes():
    conn = _make_db()
    indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        )
    }
    assert {"idx_etp_profile_source", "idx_lots_primary", "idx_lot_items_cad"}.issubset(indexes)


# ─────────────────────────────────────────────────────────────────────────────
#  Фикстура целиком грузится без ошибок
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture_loads_into_db():
    fixture = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    conn = _make_db()

    # Подгружаем КН в objects — иначе FK не пройдут.
    cads = {p["cad_number"] for p in fixture["object_etp_profile"]}
    cads |= {it["cad_number"] for it in fixture["lot_items"]}
    for cad in cads:
        _insert_object(conn, cad)

    for prof in fixture["object_etp_profile"]:
        conn.execute(
            "INSERT INTO object_etp_profile("
            "  cad_number, location_extra, building_extra, layout, legal_extra, risks, extras,"
            "  source, confidence, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                prof["cad_number"],
                _json(prof.get("location_extra")),
                _json(prof.get("building_extra")),
                _json(prof.get("layout")),
                _json(prof.get("legal_extra")),
                _json(prof.get("risks")),
                _json(prof.get("extras")),
                prof["source"],
                prof["confidence"],
                prof["updated_at"],
            ),
        )

    for lot in fixture["lots"]:
        conn.execute(
            "INSERT INTO lots("
            "  lot_id, name, platform_targets, procedure_type, deal_type,"
            "  primary_cad_number, notes_md, created_at"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                lot["lot_id"],
                lot["name"],
                _json(lot.get("platform_targets")),
                lot.get("procedure_type"),
                lot.get("deal_type"),
                lot.get("primary_cad_number"),
                lot.get("notes_md"),
                lot["created_at"],
            ),
        )

    for it in fixture["lot_items"]:
        conn.execute(
            "INSERT INTO lot_items(lot_id, cad_number, role, ord) VALUES (?,?,?,?)",
            (it["lot_id"], it["cad_number"], it["role"], it["ord"]),
        )

    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0] == len(fixture["object_etp_profile"])
    assert conn.execute("SELECT COUNT(*) FROM lots").fetchone()[0] == len(fixture["lots"])
    assert conn.execute("SELECT COUNT(*) FROM lot_items").fetchone()[0] == len(fixture["lot_items"])


# ─────────────────────────────────────────────────────────────────────────────
#  CHECK-constraint'ы
# ─────────────────────────────────────────────────────────────────────────────

def test_source_check_rejects_unknown():
    conn = _make_db()
    _insert_object(conn, "61:00:0000000:1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO object_etp_profile(cad_number, source, confidence) VALUES (?,?,?)",
            ("61:00:0000000:1", "wikipedia", 0.5),
        )


def test_confidence_check_rejects_out_of_range():
    conn = _make_db()
    _insert_object(conn, "61:00:0000000:2")
    for bad in (-0.1, 1.5):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO object_etp_profile(cad_number, source, confidence) VALUES (?,?,?)",
                ("61:00:0000000:2", "osv", bad),
            )


def test_lot_id_charset_accepts_recommended_pattern():
    conn = _make_db()
    for valid in ("lot:pirushin:001", "lot_pirushin_001", "abc-XYZ/123", "a"):
        conn.execute(
            "INSERT INTO lots(lot_id, name) VALUES (?, ?)",
            (valid, f"Test {valid}"),
        )
    assert conn.execute("SELECT COUNT(*) FROM lots").fetchone()[0] == 4


def test_lot_id_charset_rejects_invalid():
    conn = _make_db()
    invalid_ids = [
        "",                            # пусто
        "лот:001",                     # кириллица
        "lot 001",                     # пробел
        "lot;001",                     # запрещённый ;
        "lot.001",                     # точка
        "lot#001",                     # #
        "a" * 257,                     # длина >256
    ]
    for bad in invalid_ids:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO lots(lot_id, name) VALUES (?, ?)",
                (bad, "x"),
            )


def test_deal_type_check():
    conn = _make_db()
    conn.execute("INSERT INTO lots(lot_id, name, deal_type) VALUES ('lot:t:001', 'x', 'sale')")
    conn.execute("INSERT INTO lots(lot_id, name, deal_type) VALUES ('lot:t:002', 'x', NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO lots(lot_id, name, deal_type) VALUES ('lot:t:003', 'x', 'mortgage')"
        )


def test_lot_item_role_check():
    conn = _make_db()
    _insert_object(conn, "61:00:0000000:3")
    conn.execute("INSERT INTO lots(lot_id, name) VALUES ('lot:t:001', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO lot_items(lot_id, cad_number, role) VALUES (?, ?, ?)",
            ("lot:t:001", "61:00:0000000:3", "garage"),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  FOREIGN KEY каскады
# ─────────────────────────────────────────────────────────────────────────────

def test_object_etp_profile_cascade_on_object_delete():
    conn = _make_db()
    _insert_object(conn, "61:00:0000000:4")
    conn.execute(
        "INSERT INTO object_etp_profile(cad_number, source, confidence) VALUES (?,?,?)",
        ("61:00:0000000:4", "osv", 1.0),
    )
    conn.execute("DELETE FROM objects WHERE cad_number = ?", ("61:00:0000000:4",))
    rows = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 0


def test_lot_items_cascade_on_lot_delete():
    conn = _make_db()
    _insert_object(conn, "61:00:0000000:5")
    conn.execute("INSERT INTO lots(lot_id, name) VALUES ('lot:t:001', 'x')")
    conn.execute(
        "INSERT INTO lot_items(lot_id, cad_number, role) VALUES (?,?,?)",
        ("lot:t:001", "61:00:0000000:5", "room"),
    )
    conn.execute("DELETE FROM lots WHERE lot_id = 'lot:t:001'")
    assert conn.execute("SELECT COUNT(*) FROM lot_items").fetchone()[0] == 0


def test_lots_primary_cad_set_null_on_object_delete():
    conn = _make_db()
    _insert_object(conn, "61:00:0000000:6")
    conn.execute(
        "INSERT INTO lots(lot_id, name, primary_cad_number) VALUES (?,?,?)",
        ("lot:t:001", "x", "61:00:0000000:6"),
    )
    conn.execute("DELETE FROM objects WHERE cad_number = ?", ("61:00:0000000:6",))
    primary = conn.execute("SELECT primary_cad_number FROM lots WHERE lot_id = 'lot:t:001'").fetchone()[0]
    assert primary is None
