"""GET /bundles/{id}/download?fmt={db,json,zip} — реверс-экспорт C3.2."""
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


def _source_db_bytes() -> bytes:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        p = Path(f.name)
    try:
        conn = sqlite3.connect(p)
        try:
            conn.executescript("""
            CREATE TABLE objects (
                cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT,
                area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER
            );
            CREATE TABLE entity_registry (
                inn TEXT PRIMARY KEY, name_full TEXT NOT NULL, name_short TEXT,
                ogrn TEXT, entity_type TEXT
            );
            CREATE TABLE rights (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
                right_type TEXT NOT NULL, right_holder_inn TEXT
            );
            CREATE TABLE extracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, extract_number TEXT,
                cad_number TEXT NOT NULL, extract_date TEXT NOT NULL
            );
            """)
            conn.execute("INSERT INTO objects(cad_number, object_type, address, area) "
                         "VALUES ('61:44:0050706:31', 'room', 'Пушкина 1', 125.4)")
            conn.execute("INSERT INTO entity_registry(inn, name_full, entity_type) "
                         "VALUES ('7707083893', 'ООО Тест', 'legal')")
            conn.execute("INSERT INTO rights(cad_number, right_type, right_holder_inn) "
                         "VALUES ('61:44:0050706:31', 'собственность', '7707083893')")
            conn.execute("INSERT INTO extracts(extract_number, cad_number, extract_date) "
                         "VALUES ('EX-1', '61:44:0050706:31', '2026-05-20')")
            conn.commit()
        finally:
            conn.close()
        return p.read_bytes()
    finally:
        p.unlink(missing_ok=True)


def _bundle_zip(kmz: bytes = b"KMZ") -> bytes:
    db_bytes = _source_db_bytes()
    manifest = {
        "bundle_version": "1.0.0", "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0", "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "generated_at": datetime(2026, 6, 8, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [
            {"path": "project.kmz", "sha256": _sha256(kmz), "bytes": len(kmz)},
            {"path": "db.sqlite", "sha256": _sha256(db_bytes), "bytes": len(db_bytes)},
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("project.kmz", kmz)
        zf.writestr("db.sqlite", db_bytes)
    return buf.getvalue()


@pytest.fixture
def target_db(tmp_path: Path) -> Path:
    return tmp_path / "ekcelo.sqlite"


@pytest.fixture
def bundles_dir(tmp_path: Path) -> Path:
    return tmp_path / "bundles-store"


@pytest.fixture
def client(target_db: Path, bundles_dir: Path) -> TestClient:
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    return TestClient(create_app(
        settings=settings, mock_llm_text="x",
        ekcelo_db=target_db, bundles_dir=bundles_dir,
    ))


def _import_bundle(client: TestClient, target_db: Path, kmz: bytes = b"KMZ") -> str:
    resp = client.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", _bundle_zip(kmz), "application/zip")},
        data={"target_db": str(target_db)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["bundle_id"]


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=db
# ─────────────────────────────────────────────────────────────────────────────

def test_download_db_returns_sqlite(client: TestClient, target_db: Path, tmp_path: Path) -> None:
    bid = _import_bundle(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=db")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.sqlite3"
    # содержимое — валидный sqlite со срезом
    out = tmp_path / "got.sqlite"
    out.write_bytes(resp.content)
    conn = sqlite3.connect(out)
    try:
        cads = {r[0] for r in conn.execute("SELECT cad_number FROM objects")}
        assert cads == {"61:44:0050706:31"}
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=json
# ─────────────────────────────────────────────────────────────────────────────

def test_download_json_returns_viewmodels(client: TestClient, target_db: Path) -> None:
    bid = _import_bundle(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bundle_id"] == bid
    assert len(body["objects"]) == 1
    assert body["objects"][0]["id"] == "61:44:0050706:31"


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=zip + round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_download_zip_returns_bundle(client: TestClient, target_db: Path) -> None:
    bid = _import_bundle(client, target_db, b"KMZ-X")
    resp = client.get(f"/bundles/{bid}/download?fmt=zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "db.sqlite" in names
        assert "project.kmz" in names
        assert zf.read("project.kmz") == b"KMZ-X"


def test_download_zip_round_trips_to_noop(client: TestClient, target_db: Path, tmp_path: Path) -> None:
    """export(zip) → import → is_noop (через HTTP-import)."""
    bid = _import_bundle(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=zip")
    assert resp.status_code == 200
    # повторный импорт того же контента
    resp2 = client.post(
        "/bundles/import",
        files={"bundle_zip": ("re.zip", resp.content, "application/zip")},
        data={"target_db": str(target_db)},
    )
    assert resp2.status_code == 200
    assert resp2.json()["is_noop"] is True


# ─────────────────────────────────────────────────────────────────────────────
#  Ошибки
# ─────────────────────────────────────────────────────────────────────────────

def test_download_invalid_fmt_returns_422(client: TestClient, target_db: Path) -> None:
    bid = _import_bundle(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=bogus")
    assert resp.status_code == 422


def test_download_unknown_bundle_db_returns_404(client: TestClient, target_db: Path) -> None:
    _import_bundle(client, target_db)
    resp = client.get(f"/bundles/{'00' * 32}/download?fmt=db")
    assert resp.status_code == 404
