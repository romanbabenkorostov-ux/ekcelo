"""Bundle reverse-export (C3.2) — fmt=db/json/zip + round-trip."""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from backend.app.services.bundle_export import (
    BundleExportError,
    export_bundle_db,
    export_bundle_json,
    export_bundle_zip,
)
from backend.app.services.bundle_storage import BundleRecord


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_target_db(path: Path) -> None:
    """Полная БД §1..§6 с данными для двух объектов."""
    conn = sqlite3.connect(path)
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
            right_type TEXT NOT NULL, right_holder_inn TEXT,
            share_numerator INTEGER, share_denominator INTEGER,
            registration_number TEXT, registration_date TEXT
        );
        CREATE TABLE extracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, extract_number TEXT,
            cad_number TEXT NOT NULL, extract_date TEXT NOT NULL
        );
        CREATE TABLE object_restrictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
            restrict_type TEXT, description TEXT, registry_number TEXT,
            valid_from TEXT, valid_to TEXT, basis_doc TEXT
        );
        CREATE TABLE object_etp_profile (
            cad_number TEXT PRIMARY KEY, location_extra TEXT, building_extra TEXT,
            layout TEXT, legal_extra TEXT, risks TEXT, extras TEXT,
            source TEXT NOT NULL, confidence REAL NOT NULL, updated_at TEXT
        );
        """)
        conn.execute("INSERT INTO objects(cad_number, object_type, address, area, floors) "
                     "VALUES ('61:44:0050706:31', 'room', 'Пушкина 1', 125.4, 5)")
        conn.execute("INSERT INTO objects(cad_number, object_type, address) "
                     "VALUES ('61:44:0050706:99', 'land', 'Лермонтова 2')")
        # объект НЕ из bundle — не должен попасть в срез
        conn.execute("INSERT INTO objects(cad_number, object_type, address) "
                     "VALUES ('77:01:0000000:1', 'building', 'Москва, чужой')")
        conn.execute("INSERT INTO entity_registry(inn, name_full, entity_type) "
                     "VALUES ('7707083893', 'ООО Тест', 'legal')")
        conn.execute("INSERT INTO entity_registry(inn, name_full, entity_type) "
                     "VALUES ('999999999999', 'Чужой Холдинг', 'legal')")
        conn.execute("INSERT INTO rights(cad_number, right_type, right_holder_inn, "
                     "share_numerator, share_denominator) "
                     "VALUES ('61:44:0050706:31', 'собственность', '7707083893', 1, 1)")
        conn.execute("INSERT INTO rights(cad_number, right_type, right_holder_inn) "
                     "VALUES ('77:01:0000000:1', 'собственность', '999999999999')")
        conn.execute("INSERT INTO extracts(extract_number, cad_number, extract_date) "
                     "VALUES ('EX-1', '61:44:0050706:31', '2026-05-20')")
        conn.execute("INSERT INTO object_restrictions(cad_number, restrict_type, description) "
                     "VALUES ('61:44:0050706:31', 'okn', 'памятник')")
        conn.execute("INSERT INTO object_etp_profile(cad_number, layout, source, confidence) "
                     "VALUES ('61:44:0050706:31', '{\"finish\":\"good\"}', 'osv', 0.8)")
        conn.commit()
    finally:
        conn.close()


def _record(kmz_path: Path | None = None) -> BundleRecord:
    return BundleRecord(
        bundle_id="a" * 64,
        bundle_version="1.0.0",
        contracts_version="1.0.0",
        kmz_contract_version="2.12.0",
        kind="object",
        primary_cad_number="61:44:0050706:31",
        manifest_json={
            "bundle_version": "1.0.0",
            "contracts_version": "1.0.0",
            "kmz_contract_version": "2.12.0",
            "kind": "object",
            "primary_cad_number": "61:44:0050706:31",
            "generated_at": "2026-06-08T10:00:00+00:00",
            "objects": ["61:44:0050706:31", "61:44:0050706:99"],
            "files": [{"path": "db.sqlite", "sha256": "0" * 64, "bytes": 1}],
        },
        kmz_path=kmz_path,
        kmz_sha256=None,
        kmz_bytes=None,
        imported_at="2026-06-08 10:00:00",
    )


@pytest.fixture
def target_db(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_target_db(p)
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=db
# ─────────────────────────────────────────────────────────────────────────────

def test_export_db_returns_valid_sqlite(target_db: Path, tmp_path: Path) -> None:
    data = export_bundle_db(target_db, _record())
    out = tmp_path / "slice.sqlite"
    out.write_bytes(data)
    conn = sqlite3.connect(out)
    try:
        cads = {r[0] for r in conn.execute("SELECT cad_number FROM objects")}
        assert cads == {"61:44:0050706:31", "61:44:0050706:99"}
    finally:
        conn.close()


def test_export_db_excludes_objects_not_in_manifest(target_db: Path, tmp_path: Path) -> None:
    data = export_bundle_db(target_db, _record())
    out = tmp_path / "slice.sqlite"
    out.write_bytes(data)
    conn = sqlite3.connect(out)
    try:
        cads = {r[0] for r in conn.execute("SELECT cad_number FROM objects")}
        assert "77:01:0000000:1" not in cads  # чужой объект исключён
        # чужой ИНН тоже не попал (он только у чужого объекта)
        inns = {r[0] for r in conn.execute("SELECT inn FROM entity_registry")}
        assert inns == {"7707083893"}
    finally:
        conn.close()


def test_export_db_includes_related_rows(target_db: Path, tmp_path: Path) -> None:
    data = export_bundle_db(target_db, _record())
    out = tmp_path / "slice.sqlite"
    out.write_bytes(data)
    conn = sqlite3.connect(out)
    try:
        assert conn.execute("SELECT COUNT(*) FROM rights").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM extracts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM object_restrictions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0] == 1
    finally:
        conn.close()


def test_export_db_raises_if_manifest_object_missing(target_db: Path) -> None:
    rec = _record()
    rec.manifest_json["objects"] = ["61:44:0050706:31", "00:00:0000000:00"]
    with pytest.raises(BundleExportError):
        export_bundle_db(target_db, rec)


def test_export_db_raises_if_no_objects_in_manifest(target_db: Path) -> None:
    rec = _record()
    rec.manifest_json["objects"] = []
    with pytest.raises(BundleExportError):
        export_bundle_db(target_db, rec)


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=json
# ─────────────────────────────────────────────────────────────────────────────

def test_export_json_returns_viewmodels(target_db: Path) -> None:
    out = export_bundle_json(target_db, _record())
    assert out["bundle_id"] == "a" * 64
    assert out["kind"] == "object"
    assert len(out["objects"]) == 2
    ids = {o["id"] for o in out["objects"]}
    assert ids == {"61:44:0050706:31", "61:44:0050706:99"}


def test_export_json_object_has_characteristics(target_db: Path) -> None:
    out = export_bundle_json(target_db, _record())
    obj = next(o for o in out["objects"] if o["id"] == "61:44:0050706:31")
    assert obj["physical"]["area_m2"] == 125.4
    assert obj["temporal"]["extract_date"] == "2026-05-20"


def test_export_json_raises_if_object_missing(target_db: Path) -> None:
    rec = _record()
    rec.manifest_json["objects"] = ["00:00:0000000:00"]
    with pytest.raises(BundleExportError):
        export_bundle_json(target_db, rec)


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=zip
# ─────────────────────────────────────────────────────────────────────────────

def test_export_zip_contains_manifest_and_db(target_db: Path) -> None:
    data = export_bundle_zip(target_db, _record())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "db.sqlite" in names


def test_export_zip_includes_kmz_when_present(target_db: Path, tmp_path: Path) -> None:
    kmz = tmp_path / "stored.kmz"
    kmz.write_bytes(b"KMZ-DATA")
    data = export_bundle_zip(target_db, _record(kmz_path=kmz))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "project.kmz" in zf.namelist()
        assert zf.read("project.kmz") == b"KMZ-DATA"


def test_export_zip_manifest_has_fresh_hashes(target_db: Path) -> None:
    data = export_bundle_zip(target_db, _record())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        db_bytes = zf.read("db.sqlite")
        import hashlib
        db_entry = next(f for f in manifest["files"] if f["path"] == "db.sqlite")
        assert db_entry["sha256"] == hashlib.sha256(db_bytes).hexdigest()
        assert db_entry["bytes"] == len(db_bytes)


def test_export_zip_round_trip_import_is_noop(target_db: Path, tmp_path: Path) -> None:
    """Round-trip контракт: export(zip) → import → is_noop == True."""
    from backend.app.services.bundle import import_bundle

    data = export_bundle_zip(target_db, _record())
    # распаковать экспортированный bundle
    bundle_dir = tmp_path / "exported"
    bundle_dir.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(bundle_dir)

    # импортировать в ТУ ЖЕ БД → ничего не должно измениться
    report = import_bundle(bundle_dir, target_db, verify_hashes=True)
    assert report.is_noop, (
        f"round-trip не no-op: inserted={report.objects_inserted}, "
        f"updated={report.objects_updated}, rights={report.rights_inserted}, "
        f"errors={report.errors}"
    )
    assert report.files_failed == []
