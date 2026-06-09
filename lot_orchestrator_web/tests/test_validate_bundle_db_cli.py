"""P0.1.2 — CLI ekcelo-validate-bundle-db."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from lot_orchestrator_web.validate_bundle_db_cli import main


def _full_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
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
        """)
        conn.commit()
    finally:
        conn.close()


def _minimal_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL);
        CREATE TABLE entity_registry (inn TEXT PRIMARY KEY, name_full TEXT NOT NULL);
        CREATE TABLE rights (id INTEGER PRIMARY KEY, cad_number TEXT NOT NULL, right_type TEXT NOT NULL);
        """)
        conn.commit()
    finally:
        conn.close()


def test_cli_valid_db_returns_0(tmp_path: Path, capsys) -> None:
    db = tmp_path / "db.sqlite"
    _full_db(db)
    rc = main([str(db)])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_invalid_db_returns_3(tmp_path: Path, capsys) -> None:
    db = tmp_path / "db.sqlite"
    _minimal_db(db)
    rc = main([str(db)])
    assert rc == 3
    out = capsys.readouterr().out
    assert "НАРУШЕНИЯ" in out
    assert "address" in out


def test_cli_resolves_db_in_bundle_dir(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _full_db(bundle / "db.sqlite")
    rc = main([str(bundle)])
    assert rc == 0


def test_cli_missing_path_returns_2(tmp_path: Path, capsys) -> None:
    rc = main([str(tmp_path / "nope")])
    assert rc == 2


def test_cli_bundle_dir_without_db_returns_2(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = main([str(empty)])
    assert rc == 2


def test_cli_json_output(tmp_path: Path, capsys) -> None:
    db = tmp_path / "db.sqlite"
    _minimal_db(db)
    rc = main([str(db), "--json"])
    assert rc == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["db_path"].endswith("db.sqlite")
    assert any("address" in v for v in payload["violations"])


def test_cli_require_section6_flag(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _full_db(db)  # §1..§5 only, no §6
    assert main([str(db)]) == 0                       # §6 опционален
    assert main([str(db), "--require-section6"]) == 3  # требуем §6 → нарушение
