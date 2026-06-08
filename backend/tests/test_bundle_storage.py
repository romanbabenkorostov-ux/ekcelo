"""Bundle storage (C3.1) — bundle_id + sidecar таблица + KMZ-копия."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.services.bundle import Manifest, load_manifest
from backend.app.services.bundle_storage import (
    compute_bundle_id,
    ensure_bundles_schema,
    get_bundle,
    store_bundle,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers — синтетический Bundle
# ─────────────────────────────────────────────────────────────────────────────

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _make_bundle(root: Path, *, kmz_bytes: bytes = b"KMZ-MOCK") -> Manifest:
    """Создаёт каталог bundle с manifest.json + project.kmz + пустым db.sqlite."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.kmz").write_bytes(kmz_bytes)
    (root / "db.sqlite").write_bytes(b"")
    manifest_dict = {
        "bundle_version": "1.0.0",
        "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0",
        "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "extract_date": "2026-05-20",
        "etp_layer_present": False,
        "generated_at": datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [{
            "path": "project.kmz",
            "sha256": _sha256(kmz_bytes),
            "bytes": len(kmz_bytes),
        }],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest_dict, ensure_ascii=False), encoding="utf-8"
    )
    return load_manifest(root)


def _empty_target_db(path: Path) -> Path:
    sqlite3.connect(path).close()
    return path


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    return tmp_path / "bundle"


@pytest.fixture
def bundles_dir(tmp_path: Path) -> Path:
    return tmp_path / "bundles-store"


@pytest.fixture
def target_db(tmp_path: Path) -> Path:
    return _empty_target_db(tmp_path / "ekcelo.sqlite")


# ─────────────────────────────────────────────────────────────────────────────
#  compute_bundle_id
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_bundle_id_deterministic(bundle_dir: Path) -> None:
    m1 = _make_bundle(bundle_dir)
    # перечитаем тот же манифест второй раз
    m2 = load_manifest(bundle_dir)
    assert compute_bundle_id(m1) == compute_bundle_id(m2)
    # формат: 64 hex
    bid = compute_bundle_id(m1)
    assert len(bid) == 64
    assert all(c in "0123456789abcdef" for c in bid)


def test_compute_bundle_id_differs_for_different_manifests(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    m_a = _make_bundle(a, kmz_bytes=b"AAA")
    m_b = _make_bundle(b, kmz_bytes=b"BBB")
    assert compute_bundle_id(m_a) != compute_bundle_id(m_b)


# ─────────────────────────────────────────────────────────────────────────────
#  ensure_bundles_schema
# ─────────────────────────────────────────────────────────────────────────────

def test_ensure_bundles_schema_creates_table(target_db: Path) -> None:
    conn = sqlite3.connect(target_db)
    try:
        ensure_bundles_schema(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bundles'"
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_ensure_bundles_schema_idempotent(target_db: Path) -> None:
    conn = sqlite3.connect(target_db)
    try:
        ensure_bundles_schema(conn)
        ensure_bundles_schema(conn)  # second call must not error
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  store_bundle
# ─────────────────────────────────────────────────────────────────────────────

def test_store_bundle_returns_id_and_persists_row(
    bundle_dir: Path, bundles_dir: Path, target_db: Path,
) -> None:
    manifest = _make_bundle(bundle_dir)
    bid = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    assert len(bid) == 64
    conn = sqlite3.connect(target_db)
    try:
        rows = conn.execute("SELECT * FROM bundles WHERE bundle_id = ?", (bid,)).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_store_bundle_copies_kmz_to_bundles_dir(
    bundle_dir: Path, bundles_dir: Path, target_db: Path,
) -> None:
    manifest = _make_bundle(bundle_dir, kmz_bytes=b"PROJECT-KMZ-CONTENT")
    bid = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    dst = bundles_dir / f"{bid}.kmz"
    assert dst.is_file()
    assert dst.read_bytes() == b"PROJECT-KMZ-CONTENT"


def test_store_bundle_idempotent_no_duplicate_row(
    bundle_dir: Path, bundles_dir: Path, target_db: Path,
) -> None:
    manifest = _make_bundle(bundle_dir)
    bid1 = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    bid2 = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    assert bid1 == bid2
    conn = sqlite3.connect(target_db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM bundles WHERE bundle_id = ?", (bid1,)).fetchone()[0]
        assert n == 1
    finally:
        conn.close()


def test_store_bundle_creates_bundles_dir_if_missing(
    bundle_dir: Path, tmp_path: Path, target_db: Path,
) -> None:
    nested = tmp_path / "nested" / "deep" / "bundles"
    assert not nested.exists()
    manifest = _make_bundle(bundle_dir)
    store_bundle(target_db, nested, bundle_dir, manifest)
    assert nested.is_dir()


def test_store_bundle_without_kmz_records_metadata_only(
    bundle_dir: Path, bundles_dir: Path, target_db: Path,
) -> None:
    manifest = _make_bundle(bundle_dir)
    (bundle_dir / "project.kmz").unlink()  # удалить KMZ
    bid = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    conn = sqlite3.connect(target_db)
    try:
        row = conn.execute(
            "SELECT kmz_path, kmz_sha256, kmz_bytes FROM bundles WHERE bundle_id = ?",
            (bid,),
        ).fetchone()
        assert row == (None, None, None)
    finally:
        conn.close()
    assert not (bundles_dir / f"{bid}.kmz").exists()


# ─────────────────────────────────────────────────────────────────────────────
#  get_bundle
# ─────────────────────────────────────────────────────────────────────────────

def test_get_bundle_returns_record_after_store(
    bundle_dir: Path, bundles_dir: Path, target_db: Path,
) -> None:
    manifest = _make_bundle(bundle_dir)
    bid = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    rec = get_bundle(target_db, bundles_dir, bid)
    assert rec is not None
    assert rec.bundle_id == bid
    assert rec.kind == "object"
    assert rec.primary_cad_number == "61:44:0050706:31"
    assert rec.kmz_path is not None
    assert rec.kmz_path.is_file()
    assert rec.manifest_json["bundle_version"] == "1.0.0"


def test_get_bundle_returns_none_for_unknown(
    bundles_dir: Path, target_db: Path,
) -> None:
    assert get_bundle(target_db, bundles_dir, "deadbeef" * 8) is None


def test_get_bundle_returns_none_when_no_bundles_table(
    bundles_dir: Path, target_db: Path,
) -> None:
    # БД существует, но миграция 0002 не применена
    assert get_bundle(target_db, bundles_dir, "any_id") is None


def test_get_bundle_returns_none_when_db_missing(tmp_path: Path) -> None:
    assert get_bundle(tmp_path / "no.sqlite", tmp_path / "bundles", "x") is None


def test_get_bundle_kmz_path_is_none_if_file_missing(
    bundle_dir: Path, bundles_dir: Path, target_db: Path,
) -> None:
    manifest = _make_bundle(bundle_dir)
    bid = store_bundle(target_db, bundles_dir, bundle_dir, manifest)
    # Удалить KMZ файл с диска (запись в БД остаётся)
    (bundles_dir / f"{bid}.kmz").unlink()
    rec = get_bundle(target_db, bundles_dir, bid)
    assert rec is not None
    assert rec.kmz_path is None
