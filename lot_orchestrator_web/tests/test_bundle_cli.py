"""CLI ekcelo-import-bundle (P0.2 sub-stage B)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lot_orchestrator_web.bundle_cli import main


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _make_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    db = bundle / "db.sqlite"
    conn = sqlite3.connect(db)
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
    conn.execute("INSERT INTO objects(cad_number, object_type, area) "
                 "VALUES ('61:44:0050706:31', 'room', 125.4)")
    conn.commit()
    conn.close()
    kmz = bundle / "project.kmz"
    kmz.write_bytes(b"PK\x03\x04fake")
    manifest = {
        "bundle_version": "1.0.0", "contracts_version": "1.0.0",
        "kmz_contract_version": "2.12.0", "kind": "object",
        "primary_cad_number": "61:44:0050706:31",
        "generated_at": datetime(2026, 6, 3, tzinfo=timezone.utc).isoformat(),
        "objects": ["61:44:0050706:31"],
        "files": [
            {"path": "db.sqlite", "sha256": _sha256(db.read_bytes()),
             "bytes": db.stat().st_size},
            {"path": "project.kmz", "sha256": _sha256(kmz.read_bytes()),
             "bytes": kmz.stat().st_size},
        ],
    }
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def test_cli_happy_path(tmp_path, capsys):
    bundle = _make_bundle(tmp_path)
    target = tmp_path / "ekcelo.sqlite"
    rc = main(["--bundle", str(bundle), "--db", str(target)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[OK]" in out
    assert "+1 ins" in out


def test_cli_noop_second_run(tmp_path, capsys):
    bundle = _make_bundle(tmp_path)
    target = tmp_path / "ekcelo.sqlite"
    main(["--bundle", str(bundle), "--db", str(target)])
    capsys.readouterr()  # drain
    rc = main(["--bundle", str(bundle), "--db", str(target)])
    assert rc == 0
    assert "[NOOP]" in capsys.readouterr().out


def test_cli_dry_run(tmp_path, capsys):
    bundle = _make_bundle(tmp_path)
    target = tmp_path / "ekcelo.sqlite"
    rc = main(["--bundle", str(bundle), "--db", str(target), "--dry-run"])
    assert rc == 0
    # Целевая БД пустая (схема создана, данных нет).
    conn = sqlite3.connect(target)
    n = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    conn.close()
    assert n == 0


def test_cli_no_verify_skips_hash_check(tmp_path):
    bundle = _make_bundle(tmp_path)
    # Подменяем kmz — sha не сойдётся.
    (bundle / "project.kmz").write_bytes(b"TAMPERED")
    target = tmp_path / "ekcelo.sqlite"
    rc = main(["--bundle", str(bundle), "--db", str(target), "--no-verify"])
    assert rc == 0


def test_cli_hash_mismatch_returns_3(tmp_path):
    bundle = _make_bundle(tmp_path)
    (bundle / "project.kmz").write_bytes(b"TAMPERED")
    target = tmp_path / "ekcelo.sqlite"
    rc = main(["--bundle", str(bundle), "--db", str(target)])
    assert rc == 3


def test_cli_missing_bundle_returns_2(tmp_path, capsys):
    rc = main(["--bundle", str(tmp_path / "missing"), "--db",
               str(tmp_path / "ekcelo.sqlite")])
    assert rc == 2
    assert "не каталог" in capsys.readouterr().err


def test_cli_json_output(tmp_path, capsys):
    bundle = _make_bundle(tmp_path)
    target = tmp_path / "ekcelo.sqlite"
    rc = main(["--bundle", str(bundle), "--db", str(target), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["objects_inserted"] == 1
    assert payload["is_noop"] is False
