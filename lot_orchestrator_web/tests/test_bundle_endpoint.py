"""POST /bundles/import — multipart upload + import."""
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


@pytest.fixture
def client():
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    return TestClient(create_app(settings=settings, mock_llm_text="x"))


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _make_bundle_zip(*, with_subdir: bool = False) -> bytes:
    """Соберает zip с manifest + db.sqlite + project.kmz.

    Если with_subdir=True — кладёт всё в один корневой подкаталог `bundle/`.
    """
    # Сделать db.sqlite в памяти не получится через sqlite3 file path;
    # пишем во временный буфер через на-диск sqlite не нужно — формируем
    # минимальную правильную SQLite-БД через sqlite3 → file → bytes.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_file = Path(tf.name)
    try:
        conn = sqlite3.connect(db_file)
        conn.executescript("""
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT,
            permitted_use TEXT, purpose TEXT, floors INTEGER
        );
        CREATE TABLE entity_registry (
            inn TEXT PRIMARY KEY, name_full TEXT NOT NULL,
            name_short TEXT, ogrn TEXT, entity_type TEXT
        );
        CREATE TABLE rights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cad_number TEXT NOT NULL, right_type TEXT NOT NULL,
            right_holder_inn TEXT
        );
        """)
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, area) "
            "VALUES ('61:44:0050706:31', 'room', 125.4)"
        )
        conn.commit()
        conn.close()
        db_bytes = db_file.read_bytes()
    finally:
        db_file.unlink(missing_ok=True)

    kmz_bytes = b"PK\x03\x04fake-kmz"
    manifest = {
        "bundle_version": "1.0.0", "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0", "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "generated_at": datetime(2026, 6, 3, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [
            {"path": "db.sqlite", "sha256": _sha256(db_bytes), "bytes": len(db_bytes)},
            {"path": "project.kmz", "sha256": _sha256(kmz_bytes), "bytes": len(kmz_bytes)},
        ],
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        prefix = "bundle/" if with_subdir else ""
        zf.writestr(f"{prefix}manifest.json", manifest_bytes)
        zf.writestr(f"{prefix}db.sqlite", db_bytes)
        zf.writestr(f"{prefix}project.kmz", kmz_bytes)
    return buf.getvalue()


def test_endpoint_happy_path(client, tmp_path):
    target = tmp_path / "ekcelo.sqlite"
    zip_bytes = _make_bundle_zip()
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("test.zip", zip_bytes, "application/zip")},
        data={"target_db": str(target)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["objects_inserted"] == 1
    assert body["is_noop"] is False


def test_endpoint_subdir_form_handled(client, tmp_path):
    """Архив, где всё лежит в одном подкаталоге, тоже должен импортироваться."""
    target = tmp_path / "ekcelo.sqlite"
    zip_bytes = _make_bundle_zip(with_subdir=True)
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("test.zip", zip_bytes, "application/zip")},
        data={"target_db": str(target)},
    )
    assert response.status_code == 200, response.text


def test_endpoint_idempotent(client, tmp_path):
    target = tmp_path / "ekcelo.sqlite"
    zip_bytes = _make_bundle_zip()
    files = {"bundle_zip": ("test.zip", zip_bytes, "application/zip")}
    data = {"target_db": str(target)}
    client.post("/bundles/import", files=files, data=data)
    files = {"bundle_zip": ("test.zip", zip_bytes, "application/zip")}
    response2 = client.post("/bundles/import", files=files, data=data)
    assert response2.status_code == 200
    assert response2.json()["is_noop"] is True


def test_endpoint_dry_run(client, tmp_path):
    target = tmp_path / "ekcelo.sqlite"
    zip_bytes = _make_bundle_zip()
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("test.zip", zip_bytes, "application/zip")},
        data={"target_db": str(target), "dry_run": "true"},
    )
    assert response.status_code == 200
    # БД создана, но данных нет.
    conn = sqlite3.connect(target)
    n = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    conn.close()
    assert n == 0


def test_endpoint_bad_zip_returns_400(client, tmp_path):
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("test.zip", b"not-a-zip", "application/zip")},
        data={"target_db": str(tmp_path / "ekcelo.sqlite")},
    )
    assert response.status_code == 400
    assert "Битый zip" in response.json()["detail"]


def test_endpoint_non_zip_filename_returns_400(client, tmp_path):
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("test.tar", b"x", "application/octet-stream")},
        data={"target_db": str(tmp_path / "ekcelo.sqlite")},
    )
    assert response.status_code == 400
    assert ".zip" in response.json()["detail"]


def test_endpoint_zip_without_manifest_returns_400(client, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("just-some-file.txt", b"hello")
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("x.zip", buf.getvalue(), "application/zip")},
        data={"target_db": str(tmp_path / "ekcelo.sqlite")},
    )
    assert response.status_code == 400
    assert "manifest.json" in response.json()["detail"]


def test_endpoint_tampered_file_returns_422(client, tmp_path):
    """sha256 mismatch → 422 (integrity), не 200/400."""
    # Соберём zip, но подменим db.sqlite чтобы sha не сошёлся.
    zip_bytes = _make_bundle_zip()
    # Распакуем и переупакуем с битой db.
    buf_in = io.BytesIO(zip_bytes)
    buf_out = io.BytesIO()
    with zipfile.ZipFile(buf_in, "r") as zf_in, \
         zipfile.ZipFile(buf_out, "w") as zf_out:
        for name in zf_in.namelist():
            data = zf_in.read(name)
            if name.endswith("db.sqlite"):
                data = b"TAMPERED" + data[8:]  # сохраним размер
            zf_out.writestr(name, data)
    response = client.post(
        "/bundles/import",
        files={"bundle_zip": ("x.zip", buf_out.getvalue(), "application/zip")},
        data={"target_db": str(tmp_path / "ekcelo.sqlite")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["files_failed"]
    assert any("sha256" in f for f in body["files_failed"])
