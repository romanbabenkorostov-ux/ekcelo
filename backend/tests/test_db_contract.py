"""DB-контракт C2 — load + validate_db + sync-guard (P0.1.1)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.app.services.db_contract import (
    check_contract_matches_ddl,
    contract_tables,
    load_contract,
    validate_db,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Фикстуры — БД по контракту
# ─────────────────────────────────────────────────────────────────────────────

_FULL_SCHEMA = """
CREATE TABLE objects (
    cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT,
    area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER,
    updated_at TEXT
);
CREATE TABLE entity_registry (
    inn TEXT PRIMARY KEY, name_full TEXT NOT NULL, name_short TEXT,
    ogrn TEXT, entity_type TEXT, updated_at TEXT
);
CREATE TABLE rights (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
    right_type TEXT NOT NULL, right_holder_inn TEXT, share_numerator INTEGER,
    share_denominator INTEGER, registration_number TEXT, registration_date TEXT,
    source_extract_id INTEGER, updated_at TEXT
);
CREATE TABLE extracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, extract_number TEXT,
    cad_number TEXT NOT NULL, extract_date TEXT NOT NULL, document_type TEXT,
    raw_json TEXT, parsed_at TEXT, parser_version TEXT
);
CREATE TABLE object_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
    restrict_type TEXT, description TEXT, registry_number TEXT,
    valid_from TEXT, valid_to TEXT, basis_doc TEXT, updated_at TEXT
);
CREATE TABLE object_etp_profile (
    cad_number TEXT PRIMARY KEY, location_extra TEXT, building_extra TEXT,
    layout TEXT, legal_extra TEXT, risks TEXT, extras TEXT,
    source TEXT NOT NULL, confidence REAL NOT NULL, updated_at TEXT
);
CREATE TABLE lots (
    lot_id TEXT PRIMARY KEY, name TEXT NOT NULL, platform_targets TEXT,
    procedure_type TEXT, deal_type TEXT, primary_cad_number TEXT,
    notes_md TEXT, created_at TEXT
);
CREATE TABLE lot_items (
    lot_id TEXT NOT NULL, cad_number TEXT NOT NULL, role TEXT NOT NULL,
    ord INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (lot_id, cad_number)
);
"""

_EGRN_ONLY_SCHEMA = """
CREATE TABLE objects (
    cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT,
    area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER,
    updated_at TEXT
);
CREATE TABLE entity_registry (
    inn TEXT PRIMARY KEY, name_full TEXT NOT NULL, name_short TEXT,
    ogrn TEXT, entity_type TEXT, updated_at TEXT
);
CREATE TABLE rights (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
    right_type TEXT NOT NULL, right_holder_inn TEXT, share_numerator INTEGER,
    share_denominator INTEGER, registration_number TEXT, registration_date TEXT,
    source_extract_id INTEGER, updated_at TEXT
);
CREATE TABLE extracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, extract_number TEXT,
    cad_number TEXT NOT NULL, extract_date TEXT NOT NULL, document_type TEXT,
    raw_json TEXT, parsed_at TEXT, parser_version TEXT
);
CREATE TABLE object_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
    restrict_type TEXT, description TEXT, registry_number TEXT,
    valid_from TEXT, valid_to TEXT, basis_doc TEXT, updated_at TEXT
);
"""


def _make_db(path: Path, ddl: str) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def full_db(tmp_path: Path) -> Path:
    return _make_db(tmp_path / "full.sqlite", _FULL_SCHEMA)


@pytest.fixture
def egrn_db(tmp_path: Path) -> Path:
    return _make_db(tmp_path / "egrn.sqlite", _EGRN_ONLY_SCHEMA)


# ─────────────────────────────────────────────────────────────────────────────
#  load_contract
# ─────────────────────────────────────────────────────────────────────────────

def test_load_contract_has_8_tables() -> None:
    tables = contract_tables()
    assert set(tables) == {
        "objects", "entity_registry", "rights", "extracts",
        "object_restrictions", "object_etp_profile", "lots", "lot_items",
    }


def test_contract_marks_section6_not_restorable() -> None:
    tables = contract_tables()
    for t in ("object_etp_profile", "lots", "lot_items"):
        assert tables[t]["restorable"] is False
        assert str(tables[t]["section"]) == "6"
    for t in ("objects", "entity_registry", "rights", "extracts", "object_restrictions"):
        assert tables[t]["restorable"] is True


def test_contract_has_version_and_ddl_source() -> None:
    c = load_contract()
    assert c["contract_version"]
    assert c["ddl_source"] == "schema/egrn_current_schema.sql"


# ─────────────────────────────────────────────────────────────────────────────
#  validate_db
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_full_db_passes(full_db: Path) -> None:
    assert validate_db(full_db) == []


def test_validate_egrn_only_passes_without_section6(egrn_db: Path) -> None:
    # §6 отсутствует — это допустимо для чистого ЕГРН-слепка
    assert validate_db(egrn_db) == []


def test_validate_egrn_only_fails_when_section6_required(egrn_db: Path) -> None:
    violations = validate_db(egrn_db, require_section6=True)
    assert any("object_etp_profile" in v for v in violations)
    assert any("lots" in v for v in violations)


def test_validate_detects_missing_table(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "partial.sqlite", """
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT,
            area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER
        );
    """)
    violations = validate_db(db)
    assert any("отсутствует таблица: entity_registry" in v for v in violations)
    assert any("отсутствует таблица: rights" in v for v in violations)


def test_validate_detects_missing_column(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "badcol.sqlite", """
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL);
        CREATE TABLE entity_registry (inn TEXT PRIMARY KEY, name_full TEXT NOT NULL);
        CREATE TABLE rights (id INTEGER PRIMARY KEY, cad_number TEXT NOT NULL, right_type TEXT NOT NULL);
        CREATE TABLE extracts (id INTEGER PRIMARY KEY, cad_number TEXT NOT NULL, extract_date TEXT NOT NULL);
        CREATE TABLE object_restrictions (id INTEGER PRIMARY KEY, cad_number TEXT NOT NULL);
    """)
    violations = validate_db(db)
    # objects недостаёт address/area/... — должно отлавливаться
    assert any("objects: отсутствует колонка address" in v for v in violations)


def test_validate_extra_columns_allowed(tmp_path: Path) -> None:
    # лишняя колонка в БД — не нарушение (схема расширяема вперёд)
    db = _make_db(tmp_path / "extra.sqlite", _EGRN_ONLY_SCHEMA + """
        ALTER TABLE objects ADD COLUMN future_field TEXT;
    """)
    assert validate_db(db) == []


# ─────────────────────────────────────────────────────────────────────────────
#  Sync-guard: контракт ↔ реальный DDL schema/egrn_current_schema.sql
# ─────────────────────────────────────────────────────────────────────────────

def test_contract_in_sync_with_real_ddl() -> None:
    """КРИТИЧНО: contracts/db/schema.json не должен отставать от schema.sql."""
    issues = check_contract_matches_ddl()
    assert issues == [], "контракт разошёлся с schema/egrn_current_schema.sql:\n" + "\n".join(issues)


def test_sync_guard_detects_extra_contract_table() -> None:
    contract = load_contract()
    contract["tables"]["ghost_table"] = {"section": "1", "columns": {"x": {"type": "TEXT"}}}
    issues = check_contract_matches_ddl(contract=contract)
    assert any("ghost_table" in i and "НЕ в DDL" in i for i in issues)


def test_sync_guard_detects_missing_contract_column() -> None:
    ddl = "CREATE TABLE objects (cad_number TEXT PRIMARY KEY, brand_new_col TEXT);"
    contract = {"tables": {"objects": {"columns": {"cad_number": {"type": "TEXT"}}}}}
    issues = check_contract_matches_ddl(contract=contract, ddl_text=ddl)
    assert any("brand_new_col" in i and "НЕ в контракте" in i for i in issues)


def test_sync_guard_ignores_table_level_constraints() -> None:
    # PRIMARY KEY (...) на уровне таблицы не должен попадать в колонки
    ddl = """CREATE TABLE lot_items (
        lot_id TEXT NOT NULL, cad_number TEXT NOT NULL, role TEXT NOT NULL,
        ord INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (lot_id, cad_number)
    );"""
    contract = {"tables": {"lot_items": {"columns": {
        "lot_id": {"type": "TEXT"}, "cad_number": {"type": "TEXT"},
        "role": {"type": "TEXT"}, "ord": {"type": "INTEGER"},
    }}}}
    issues = check_contract_matches_ddl(contract=contract, ddl_text=ddl)
    assert issues == []
