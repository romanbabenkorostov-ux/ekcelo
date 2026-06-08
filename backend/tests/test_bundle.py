"""Bundle (C3) — манифест-валидация + идемпотентный импорт."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.services.bundle import (
    ImportReport,
    Manifest,
    import_bundle,
    load_manifest,
    verify_files,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers — синтетический Bundle
# ─────────────────────────────────────────────────────────────────────────────

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _make_source_db(path: Path, *, with_etp: bool = False) -> None:
    """Минимальная SQLite-БД источника с objects/rights/entity_registry (+ опц. ЭТП)."""
    conn = sqlite3.connect(path)
    try:
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
            "INSERT INTO objects(cad_number, object_type, address, area) "
            "VALUES ('61:44:0050706:31', 'room', 'г. Ростов', 125.4)"
        )
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, entity_type) "
            "VALUES ('7707083893', 'ООО Тест', 'legal')"
        )
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn) "
            "VALUES ('61:44:0050706:31', 'собственность', '7707083893')"
        )
        if with_etp:
            conn.executescript("""
            CREATE TABLE object_etp_profile (
                cad_number TEXT PRIMARY KEY,
                building_extra TEXT, legal_extra TEXT,
                source TEXT, confidence REAL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            """)
            conn.execute(
                "INSERT INTO object_etp_profile(cad_number, building_extra, source, confidence) "
                "VALUES ('61:44:0050706:31', '{\"year_built\": 1990}', 'osv', 1.0)"
            )
        conn.commit()
    finally:
        conn.close()


def _make_bundle(tmp_path: Path, *, with_etp: bool = False,
                 kmz_bytes: bytes = b"PK\x03\x04fake-kmz") -> Path:
    """Собирает валидный Bundle: manifest.json + db.sqlite + project.kmz."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    db_path = bundle / "db.sqlite"
    _make_source_db(db_path, with_etp=with_etp)
    kmz_path = bundle / "project.kmz"
    kmz_path.write_bytes(kmz_bytes)

    manifest = {
        "bundle_version": "1.0.0",
        "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0",
        "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "extract_date": "2026-05-01",
        "etp_layer_present": with_etp,
        "generated_by": "test-fixture",
        "generated_at": datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [
            {"path": "db.sqlite", "sha256": _sha256(db_path.read_bytes()),
             "bytes": db_path.stat().st_size},
            {"path": "project.kmz", "sha256": _sha256(kmz_path.read_bytes()),
             "bytes": kmz_path.stat().st_size},
        ],
    }
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return bundle


# ─────────────────────────────────────────────────────────────────────────────
#  Manifest schema validation
# ─────────────────────────────────────────────────────────────────────────────

def test_manifest_minimal_valid(tmp_path):
    bundle = _make_bundle(tmp_path)
    m = load_manifest(bundle)
    assert m.kind == "object"
    assert m.objects == ["61:44:0050706:31"]
    assert len(m.files) == 2


def test_manifest_missing_required_fields_rejected():
    with pytest.raises(ValidationError):
        Manifest.model_validate({"bundle_version": "1.0.0"})  # too few fields


def test_manifest_objects_must_be_unique():
    with pytest.raises(ValidationError, match="дубликаты"):
        Manifest.model_validate({
            "bundle_version": "1.0.0", "contracts_version": "1.0.0",
            "kmz_contract_version": "2.12.0", "kind": "object",
            "generated_at": "2026-06-03T00:00:00Z",
            "objects": ["a", "a"],
            "files": [{"path": "x", "sha256": "0" * 64, "bytes": 1}],
        })


def test_manifest_sha256_format_enforced():
    with pytest.raises(ValidationError):
        Manifest.model_validate({
            "bundle_version": "1.0.0", "contracts_version": "1.0.0",
            "kmz_contract_version": "2.12.0", "kind": "object",
            "generated_at": "2026-06-03T00:00:00Z",
            "objects": ["a"],
            "files": [{"path": "x", "sha256": "not-hex", "bytes": 1}],
        })


def test_manifest_kind_lot_allows_lot_block():
    m = Manifest.model_validate({
        "bundle_version": "1.0.0", "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0", "kind": "lot",
        "generated_at": "2026-06-03T00:00:00Z",
        "objects": ["a", "b"],
        "lot": {"lot_id": "lot:test:001", "members": ["a", "b"]},
        "files": [{"path": "x", "sha256": "0" * 64, "bytes": 1}],
    })
    assert m.lot is not None
    assert m.lot.lot_id == "lot:test:001"


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        load_manifest(tmp_path / "no-such-bundle")


# ─────────────────────────────────────────────────────────────────────────────
#  verify_files — sha256/size integrity
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_files_clean_bundle(tmp_path):
    bundle = _make_bundle(tmp_path)
    m = load_manifest(bundle)
    assert verify_files(bundle, m) == []


def test_verify_files_detects_tamper(tmp_path):
    bundle = _make_bundle(tmp_path)
    m = load_manifest(bundle)
    # Подменим KMZ — sha256 не сойдётся.
    (bundle / "project.kmz").write_bytes(b"TAMPERED")
    failures = verify_files(bundle, m)
    assert len(failures) >= 1
    assert any("sha256 mismatch" in f or "size mismatch" in f for f in failures)


def test_verify_files_detects_missing(tmp_path):
    bundle = _make_bundle(tmp_path)
    m = load_manifest(bundle)
    (bundle / "project.kmz").unlink()
    failures = verify_files(bundle, m)
    assert any("missing" in f and "project.kmz" in f for f in failures)


# ─────────────────────────────────────────────────────────────────────────────
#  import_bundle — идемпотентность + изоляция от красивых ошибок
# ─────────────────────────────────────────────────────────────────────────────

def test_import_bundle_happy_path(tmp_path):
    bundle = _make_bundle(tmp_path)
    target_db = tmp_path / "ekcelo.sqlite"
    report = import_bundle(bundle, target_db)
    assert report.errors == []
    assert report.objects_inserted == 1
    assert report.entities_inserted == 1
    assert report.rights_inserted == 1
    assert report.files_verified == 2
    # БД действительно создана и содержит запись.
    conn = sqlite3.connect(target_db)
    try:
        row = conn.execute(
            "SELECT object_type FROM objects WHERE cad_number=?",
            ("61:44:0050706:31",)
        ).fetchone()
        assert row == ("room",)
    finally:
        conn.close()


def test_import_bundle_idempotent_second_run_is_noop(tmp_path):
    bundle = _make_bundle(tmp_path)
    target_db = tmp_path / "ekcelo.sqlite"
    import_bundle(bundle, target_db)
    report2 = import_bundle(bundle, target_db)
    assert report2.errors == []
    assert report2.is_noop, (
        f"повторный импорт должен быть no-op, got: "
        f"obj_ins={report2.objects_inserted} obj_upd={report2.objects_updated} "
        f"rights_ins={report2.rights_inserted} ent_ins={report2.entities_inserted}"
    )
    assert report2.objects_skipped_identical == 1


def test_import_bundle_updates_changed_object(tmp_path):
    bundle = _make_bundle(tmp_path)
    target_db = tmp_path / "ekcelo.sqlite"
    import_bundle(bundle, target_db)

    # Меняем поле в исходной БД и пересчитываем manifest.
    src_db = bundle / "db.sqlite"
    conn = sqlite3.connect(src_db)
    conn.execute("UPDATE objects SET area = 200.0 WHERE cad_number = '61:44:0050706:31'")
    conn.commit()
    conn.close()
    # manifest пересчитываем чтобы verify_files прошёл.
    manifest_data = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest_data["files"] = [
        {"path": "db.sqlite", "sha256": _sha256(src_db.read_bytes()),
         "bytes": src_db.stat().st_size},
        manifest_data["files"][1],
    ]
    (bundle / "manifest.json").write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = import_bundle(bundle, target_db)
    assert report.objects_updated == 1
    assert report.objects_inserted == 0
    assert report.objects_skipped_identical == 0
    # Проверяем что значение действительно обновилось.
    conn = sqlite3.connect(target_db)
    area = conn.execute(
        "SELECT area FROM objects WHERE cad_number='61:44:0050706:31'"
    ).fetchone()[0]
    conn.close()
    assert area == 200.0


def test_import_bundle_dry_run_rolls_back(tmp_path):
    bundle = _make_bundle(tmp_path)
    target_db = tmp_path / "ekcelo.sqlite"
    report = import_bundle(bundle, target_db, dry_run=True)
    assert report.objects_inserted == 1
    assert any("dry-run" in w for w in report.warnings)
    # БД создана (схема), но данных нет.
    conn = sqlite3.connect(target_db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_import_bundle_detects_hash_mismatch(tmp_path):
    bundle = _make_bundle(tmp_path)
    (bundle / "project.kmz").write_bytes(b"TAMPERED")
    target_db = tmp_path / "ekcelo.sqlite"
    report = import_bundle(bundle, target_db)
    assert report.errors  # есть ошибки целостности
    assert report.objects_inserted == 0  # импорт не запустился


def test_import_bundle_missing_db_sqlite(tmp_path):
    bundle = _make_bundle(tmp_path)
    (bundle / "db.sqlite").unlink()
    # Manifest с этого момента не сходится; пропустим verify.
    target_db = tmp_path / "ekcelo.sqlite"
    report = import_bundle(bundle, target_db, verify_hashes=False)
    assert any("db.sqlite" in e for e in report.errors)


def test_import_bundle_etp_layer_authoritative_not_overwritten(tmp_path):
    """ADR-001 §6: manual/osv ЭТП-профили НЕ перезатираются импортом."""
    # Bundle с ЭТП-слоем (source=osv).
    bundle = _make_bundle(tmp_path, with_etp=True)
    target_db = tmp_path / "ekcelo.sqlite"
    # Первый импорт — профиль вставлен.
    report1 = import_bundle(bundle, target_db)
    assert report1.etp_profiles_inserted == 1

    # Помечаем профиль в целевой как manual (выше osv) → второй импорт не должен трогать.
    conn = sqlite3.connect(target_db)
    conn.execute("UPDATE object_etp_profile SET source='manual', "
                 "building_extra='{\"year_built\": 2020}' WHERE cad_number=?",
                 ("61:44:0050706:31",))
    conn.commit()
    conn.close()

    report2 = import_bundle(bundle, target_db)
    assert report2.etp_profiles_skipped_authoritative == 1
    assert report2.etp_profiles_inserted == 0
    # И профиль остался manual'ьский.
    conn = sqlite3.connect(target_db)
    src, extra = conn.execute(
        "SELECT source, building_extra FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)
    ).fetchone()
    conn.close()
    assert src == "manual"
    assert "2020" in extra
