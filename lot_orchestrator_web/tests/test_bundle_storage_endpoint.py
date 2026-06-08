"""POST /bundles/import (с bundle_id + KMZ storage) + GET /bundles/{id}/download.

Покрывает C3.1: расширение import-эндпоинта и новый download-эндпоинт.
"""
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


def _make_source_db_bytes() -> bytes:
    """Минимальная sqlite-БД источника."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        p = Path(f.name)
    try:
        conn = sqlite3.connect(p)
        try:
            conn.executescript("""
            CREATE TABLE objects (
                cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
                address TEXT, area REAL, category TEXT, permitted_use TEXT,
                purpose TEXT, floors INTEGER
            );
            CREATE TABLE entity_registry (
                inn TEXT PRIMARY KEY, name_full TEXT NOT NULL,
                name_short TEXT, ogrn TEXT, entity_type TEXT
            );
            CREATE TABLE rights (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
                right_type TEXT NOT NULL, right_holder_inn TEXT
            );
            """)
            conn.execute(
                "INSERT INTO objects(cad_number, object_type, address) "
                "VALUES ('61:44:0050706:31', 'room', 'г. Ростов')"
            )
            conn.commit()
        finally:
            conn.close()
        return p.read_bytes()
    finally:
        p.unlink(missing_ok=True)


def _make_bundle_zip(kmz_bytes: bytes = b"KMZ-CONTENT") -> bytes:
    """Собирает zip с manifest + db.sqlite + project.kmz."""
    db_bytes = _make_source_db_bytes()
    manifest = {
        "bundle_version": "1.0.0",
        "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0",
        "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "extract_date": "2026-05-20",
        "etp_layer_present": False,
        "generated_at": datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [
            {"path": "project.kmz", "sha256": _sha256(kmz_bytes),
             "bytes": len(kmz_bytes)},
            {"path": "db.sqlite", "sha256": _sha256(db_bytes),
             "bytes": len(db_bytes)},
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("project.kmz", kmz_bytes)
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


@pytest.fixture
def client_no_bundles_dir(target_db: Path) -> TestClient:
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    return TestClient(create_app(
        settings=settings, mock_llm_text="x", ekcelo_db=target_db,
    ))


# ─────────────────────────────────────────────────────────────────────────────
#  POST /bundles/import — расширение C3.1
# ─────────────────────────────────────────────────────────────────────────────

def test_import_returns_bundle_id_in_payload(
    client: TestClient, target_db: Path,
) -> None:
    resp = client.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", _make_bundle_zip(), "application/zip")},
        data={"target_db": str(target_db)},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "bundle_id" in payload
    assert isinstance(payload["bundle_id"], str)
    assert len(payload["bundle_id"]) == 64


def test_import_persists_kmz_in_bundles_dir(
    client: TestClient, target_db: Path, bundles_dir: Path,
) -> None:
    resp = client.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", _make_bundle_zip(b"REAL-KMZ"), "application/zip")},
        data={"target_db": str(target_db)},
    )
    assert resp.status_code == 200
    bid = resp.json()["bundle_id"]
    stored = bundles_dir / f"{bid}.kmz"
    assert stored.is_file()
    assert stored.read_bytes() == b"REAL-KMZ"


def test_import_dry_run_does_not_store_bundle(
    client: TestClient, target_db: Path, bundles_dir: Path,
) -> None:
    resp = client.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", _make_bundle_zip(), "application/zip")},
        data={"target_db": str(target_db), "dry_run": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["bundle_id"] is None
    assert not bundles_dir.exists() or list(bundles_dir.glob("*.kmz")) == []


def test_import_without_bundles_dir_returns_null_bundle_id(
    client_no_bundles_dir: TestClient, target_db: Path,
) -> None:
    resp = client_no_bundles_dir.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", _make_bundle_zip(), "application/zip")},
        data={"target_db": str(target_db)},
    )
    assert resp.status_code == 200
    assert resp.json()["bundle_id"] is None  # storage disabled


# ─────────────────────────────────────────────────────────────────────────────
#  GET /bundles/{bundle_id}/download
# ─────────────────────────────────────────────────────────────────────────────

def _import_and_get_id(client: TestClient, target_db: Path, kmz: bytes = b"KMZ") -> str:
    resp = client.post(
        "/bundles/import",
        files={"bundle_zip": ("b.zip", _make_bundle_zip(kmz), "application/zip")},
        data={"target_db": str(target_db)},
    )
    assert resp.status_code == 200
    return resp.json()["bundle_id"]


def test_download_kmz_returns_file(client: TestClient, target_db: Path) -> None:
    bid = _import_and_get_id(client, target_db, b"KMZ-DOWNLOAD-1")
    resp = client.get(f"/bundles/{bid}/download?fmt=kmz")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.google-earth.kmz"
    assert resp.content == b"KMZ-DOWNLOAD-1"


def test_download_default_fmt_is_kmz(client: TestClient, target_db: Path) -> None:
    bid = _import_and_get_id(client, target_db, b"DEFAULT-KMZ")
    resp = client.get(f"/bundles/{bid}/download")
    assert resp.status_code == 200
    assert resp.content == b"DEFAULT-KMZ"


def test_download_manifest_returns_json(client: TestClient, target_db: Path) -> None:
    bid = _import_and_get_id(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=manifest")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["bundle_version"] == "1.0.0"
    assert body["primary_cad_number"] == "61:44:0050706:31"


def test_download_unknown_bundle_returns_404(
    client: TestClient, target_db: Path,
) -> None:
    # Сначала любой import чтобы создать БД (иначе ekcelo_db не существует → 503)
    _import_and_get_id(client, target_db)
    resp = client.get(f"/bundles/{'00' * 32}/download?fmt=kmz")
    assert resp.status_code == 404


def test_download_invalid_fmt_returns_422(
    client: TestClient, target_db: Path,
) -> None:
    bid = _import_and_get_id(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=bogus")
    assert resp.status_code == 422


def test_download_db_fmt_returns_200_after_c3_2(
    client: TestClient, target_db: Path,
) -> None:
    # C3.2 реализовал реверс-экспорт fmt=db (раньше было 501).
    bid = _import_and_get_id(client, target_db)
    resp = client.get(f"/bundles/{bid}/download?fmt=db")
    assert resp.status_code == 200


def test_download_503_when_bundles_dir_not_configured(
    client_no_bundles_dir: TestClient, target_db: Path,
) -> None:
    # Сначала impor для существования target_db (без bundles_dir → bundle_id=None)
    _import_and_get_id(client_no_bundles_dir, target_db)
    resp = client_no_bundles_dir.get(f"/bundles/{'aa' * 32}/download?fmt=kmz")
    assert resp.status_code == 503
