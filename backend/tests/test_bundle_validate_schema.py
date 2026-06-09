"""P0.1.2 — import_bundle(validate_schema=True) + ImportReport.schema_violations."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.services.bundle import import_bundle


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _full_source_db(path: Path) -> None:
    """db.sqlite, полностью соответствующая C2-контракту (§1..§5)."""
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
        conn.execute("INSERT INTO objects(cad_number, object_type, address) "
                     "VALUES ('61:44:0050706:31', 'room', 'Ростов')")
        conn.commit()
    finally:
        conn.close()


def _minimal_source_db(path: Path) -> None:
    """db.sqlite с недостающими колонками — нарушает C2-контракт."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL);
        CREATE TABLE entity_registry (inn TEXT PRIMARY KEY, name_full TEXT NOT NULL);
        CREATE TABLE rights (id INTEGER PRIMARY KEY, cad_number TEXT NOT NULL, right_type TEXT NOT NULL);
        """)
        conn.execute("INSERT INTO objects(cad_number, object_type) "
                     "VALUES ('61:44:0050706:31', 'room')")
        conn.commit()
    finally:
        conn.close()


def _make_bundle(root: Path, db_builder) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "db.sqlite"
    db_builder(db_path)
    db_bytes = db_path.read_bytes()
    manifest = {
        "bundle_version": "1.0.0", "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0", "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "generated_at": datetime(2026, 6, 8, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [{"path": "db.sqlite", "sha256": _sha256(db_bytes), "bytes": len(db_bytes)}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                        encoding="utf-8")
    return root


def test_validate_schema_off_imports_minimal_db(tmp_path: Path) -> None:
    # backward-compat: без validate_schema минимальная БД импортируется
    bundle = _make_bundle(tmp_path / "b", _minimal_source_db)
    report = import_bundle(bundle, tmp_path / "t.sqlite")
    assert report.errors == []
    assert report.schema_violations == []
    assert report.objects_inserted == 1


def test_validate_schema_on_passes_full_db(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path / "b", _full_source_db)
    report = import_bundle(bundle, tmp_path / "t.sqlite", validate_schema=True)
    assert report.schema_violations == []
    assert report.errors == []
    assert report.objects_inserted == 1


def test_validate_schema_on_blocks_minimal_db(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path / "b", _minimal_source_db)
    target = tmp_path / "t.sqlite"
    report = import_bundle(bundle, target, validate_schema=True)
    assert report.schema_violations, "ожидались нарушения C2-схемы"
    assert any("address" in v for v in report.schema_violations)
    assert report.errors  # schema contract error добавлен
    # импорт прерван ДО мутации — ничего не вставлено
    assert report.objects_inserted == 0


def test_validate_schema_on_does_not_touch_target_on_violation(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path / "b", _minimal_source_db)
    target = tmp_path / "t.sqlite"
    import_bundle(bundle, target, validate_schema=True)
    # target не должен содержать импортированных строк (объект не вставлен)
    if target.exists():
        conn = sqlite3.connect(target)
        try:
            has_objects_tbl = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='objects'"
            ).fetchone()
            if has_objects_tbl:
                n = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
                assert n == 0
        finally:
            conn.close()
