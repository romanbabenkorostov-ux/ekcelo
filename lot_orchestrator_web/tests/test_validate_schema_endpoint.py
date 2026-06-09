"""P0.1.2 — POST /bundles/import?validate_schema=true → 422 на не-схемном db.sqlite."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _db_bytes(full: bool) -> bytes:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        p = Path(f.name)
    try:
        conn = sqlite3.connect(p)
        try:
            if full:
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
            else:
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
        return p.read_bytes()
    finally:
        p.unlink(missing_ok=True)


def _bundle_zip(full: bool) -> bytes:
    db = _db_bytes(full)
    manifest = {
        "bundle_version": "1.0.0", "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0", "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "generated_at": datetime(2026, 6, 8, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [{"path": "db.sqlite", "sha256": _sha256(db), "bytes": len(db)}],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("db.sqlite", db)
    return buf.getvalue()


@pytest.fixture
def target_db(tmp_path: Path) -> Path:
    return tmp_path / "ekcelo.sqlite"


@pytest.fixture
def client(target_db: Path) -> TestClient:
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    return TestClient(create_app(settings=settings, mock_llm_text="x", ekcelo_db=target_db))


def _post(client, target_db, zip_bytes, **form):
    return client.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", zip_bytes, "application/zip")},
        data={"target_db": str(target_db), **form},
    )


def test_import_without_validate_accepts_minimal_db(client, target_db) -> None:
    resp = _post(client, target_db, _bundle_zip(full=False))
    assert resp.status_code == 200
    assert resp.json()["schema_violations"] == []


def test_import_validate_schema_accepts_full_db(client, target_db) -> None:
    resp = _post(client, target_db, _bundle_zip(full=True), validate_schema="true")
    assert resp.status_code == 200
    assert resp.json()["schema_violations"] == []


def test_import_validate_schema_rejects_minimal_db_422(client, target_db) -> None:
    resp = _post(client, target_db, _bundle_zip(full=False), validate_schema="true")
    assert resp.status_code == 422
    body = resp.json()
    assert body["schema_violations"]
    assert any("address" in v for v in body["schema_violations"])
    # импорт прерван — ничего не вставлено
    assert body["objects_inserted"] == 0
