"""tests/test_auto_export_hook.py — флаг --export у трёх ETL CLI.

Проверяет, что:
- `--export` после успешного ETL создаёт `<out>/object_etp_profile.json`.
- `--export` совместим с `--dry-run` (экспорт пропускается без записи).
- `--export-out` / `--export-project` работают для всех 3 CLI.
- Без `--export` файл экспорта НЕ создаётся (бэк-совместимость).
"""
from __future__ import annotations

import io
import json
import sqlite3
import textwrap
from pathlib import Path

import piexif
import pytest
from piexif.helper import UserComment
from PIL import Image

from parser.exporters.etp.etl_exif_cli import main as exif_main
from parser.exporters.etp.etl_osv_cli import main as osv_main
from parser.exporters.etp.nspd_enrich_cli import main as nspd_main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
TEMPLATE = REPO_ROOT / "parser" / "exporters" / "etp" / "templates" / "osv_template.yaml"


# ─────────────────────────────────────────────────────────────────────────────
#  Common DB
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_file(tmp_path) -> Path:
    db = tmp_path / "ekcelo.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    for cad in ("61:44:0050706:31", "61:44:0050706:42", "61:44:0050706:7"):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    conn.commit()
    conn.close()
    return db


# ─────────────────────────────────────────────────────────────────────────────
#  etl_osv_cli + --export
# ─────────────────────────────────────────────────────────────────────────────

def test_osv_cli_with_export_writes_json(db_file, tmp_path):
    out = tmp_path / "exports"
    rc = osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db_file),
        "--export",
        "--export-out", str(out),
    ])
    assert rc == 0
    assert (out / "object_etp_profile.json").exists()
    payload = json.loads((out / "object_etp_profile.json").read_text(encoding="utf-8"))
    assert payload["object_etp_profile"]  # хотя бы 1 профиль из template


def test_osv_cli_without_export_does_not_write(db_file, tmp_path):
    out = tmp_path / "exports"
    rc = osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db_file),
        "--export-out", str(out),   # без --export сам флаг роли не играет
    ])
    assert rc == 0
    assert not (out / "object_etp_profile.json").exists()


def test_osv_cli_dry_run_with_export_skips(db_file, tmp_path, capsys):
    out = tmp_path / "exports"
    rc = osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db_file),
        "--dry-run",
        "--export",
        "--export-out", str(out),
    ])
    assert rc == 0
    assert not (out / "object_etp_profile.json").exists()
    captured = capsys.readouterr().out
    assert "skip-export" in captured


def test_osv_cli_export_with_project_filter(db_file, tmp_path):
    out = tmp_path / "exports"
    osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db_file),
        "--export",
        "--export-out", str(out),
        "--export-project", "pirushin",
    ])
    sub = out / "pirushin" / "object_etp_profile.json"
    assert sub.exists()
    payload = json.loads(sub.read_text(encoding="utf-8"))
    assert payload["$project_slug"] == "pirushin"


# ─────────────────────────────────────────────────────────────────────────────
#  nspd_enrich_cli + --export
# ─────────────────────────────────────────────────────────────────────────────

def test_nspd_cli_with_export_writes_json(db_file, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "61:44:0050706:31.json").write_text(json.dumps({
        "cad_number": "61:44:0050706:31",
        "wall_material": "кирпич",
    }), encoding="utf-8")
    out = tmp_path / "exports"
    rc = nspd_main([
        "--db", str(db_file),
        "--nspd", str(nspd_dir),
        "--export",
        "--export-out", str(out),
    ])
    assert rc == 0
    assert (out / "object_etp_profile.json").exists()


def test_nspd_cli_dry_run_with_export_skips(db_file, tmp_path, capsys):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "61:44:0050706:31.json").write_text(json.dumps({
        "cad_number": "61:44:0050706:31",
        "wall_material": "кирпич",
    }), encoding="utf-8")
    out = tmp_path / "exports"
    nspd_main([
        "--db", str(db_file),
        "--nspd", str(nspd_dir),
        "--dry-run",
        "--export",
        "--export-out", str(out),
    ])
    assert not (out / "object_etp_profile.json").exists()
    assert "skip-export" in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
#  etl_exif_cli + --export
# ─────────────────────────────────────────────────────────────────────────────

def _make_jpg(path: Path, payload: dict) -> None:
    img = Image.new("RGB", (4, 4), color=(255, 255, 255))
    uc = UserComment.dump(json.dumps(payload, ensure_ascii=False), encoding="unicode")
    exif_bytes = piexif.dump({"Exif": {piexif.ExifIFD.UserComment: uc}})
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif_bytes)
    path.write_bytes(buf.getvalue())


def test_exif_cli_with_export_writes_json(db_file, tmp_path):
    photos = tmp_path / "Фото"
    photos.mkdir()
    _make_jpg(photos / "p.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    out = tmp_path / "exports"
    rc = exif_main([
        "--db", str(db_file),
        "--photos", str(photos),
        "--export",
        "--export-out", str(out),
    ])
    assert rc == 0
    assert (out / "object_etp_profile.json").exists()


def test_exif_cli_no_photos_does_not_export(db_file, tmp_path):
    """Если фото не найдены — CLI выходит rc=0 ДО подключения к БД, экспорт пропускается."""
    photos = tmp_path / "empty"
    photos.mkdir()
    out = tmp_path / "exports"
    rc = exif_main([
        "--db", str(db_file),
        "--photos", str(photos),
        "--export",
        "--export-out", str(out),
    ])
    assert rc == 0
    assert not (out / "object_etp_profile.json").exists()
