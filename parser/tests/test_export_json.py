"""tests/test_export_json.py — Stage 4b: экспорт БД в JSON для viewer.

Покрывает:
- Глобальный экспорт (все профили, все лоты).
- Project-фильтр по префиксу lot_id.
- Формат JSON совместим с фикстурой (ключи + типы).
- CLI: запись в файл, exit codes, custom out-dir.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp.etl_osv import apply_osv, load_osv
from parser.exporters.etp.export_json import build_export_payload, write_export
from parser.exporters.etp.export_json_cli import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
TEMPLATE = REPO_ROOT / "parser" / "exporters" / "etp" / "templates" / "osv_template.yaml"
FIXTURE = REPO_ROOT / "parser" / "tests" / "fixtures" / "etp" / "object_etp_profile_sample.json"


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    """In-memory БД + миграция + objects для FK + 2 проекта данных."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    for cad in (
        "61:44:0050706:31", "61:44:0050706:42", "61:44:0050706:7",
        "77:01:0004012:1", "77:01:0004012:2",
    ):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    # Загружаем template — даёт нам lot:pirushin:001 + 1 профиль на :31.
    apply_osv(conn, load_osv(TEMPLATE))
    # Второй проект — для проверки фильтра.
    conn.execute(
        "INSERT INTO object_etp_profile(cad_number, source, confidence) VALUES (?,?,?)",
        ("77:01:0004012:1", "manual", 1.0),
    )
    conn.execute(
        "INSERT INTO lots(lot_id, name) VALUES ('lot:moscow:001', 'Moscow lot')"
    )
    conn.execute(
        "INSERT INTO lot_items(lot_id, cad_number, role, ord) "
        "VALUES ('lot:moscow:001', '77:01:0004012:1', 'room', 1)"
    )
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  build_export_payload
# ─────────────────────────────────────────────────────────────────────────────

def test_global_export_includes_all_data(db):
    payload = build_export_payload(db)
    assert set(payload.keys()) >= {"object_etp_profile", "lots", "lot_items"}
    cads = {p["cad_number"] for p in payload["object_etp_profile"]}
    assert cads == {"61:44:0050706:31", "77:01:0004012:1"}
    lot_ids = {l["lot_id"] for l in payload["lots"]}
    assert lot_ids == {"lot:pirushin:001", "lot:moscow:001"}
    assert len(payload["lot_items"]) == 3  # 2 от pirushin + 1 от moscow


def test_project_filter_pirushin(db):
    payload = build_export_payload(db, project_slug="pirushin")
    lot_ids = {l["lot_id"] for l in payload["lots"]}
    assert lot_ids == {"lot:pirushin:001"}
    # lot_items только pirushin
    assert all(it["lot_id"] == "lot:pirushin:001" for it in payload["lot_items"])
    # Профили = только тех КН, что упомянуты в pirushin (:31 + :7)
    cads = {p["cad_number"] for p in payload["object_etp_profile"]}
    assert "61:44:0050706:31" in cads
    assert "77:01:0004012:1" not in cads  # фильтр работает


def test_project_filter_no_match_returns_empty(db):
    payload = build_export_payload(db, project_slug="nonexistent")
    assert payload["lots"] == []
    assert payload["lot_items"] == []
    assert payload["object_etp_profile"] == []


def test_project_slug_metadata(db):
    payload = build_export_payload(db, project_slug="pirushin")
    assert payload["$project_slug"] == "pirushin"
    assert payload["$schema_version"] == "1.0"


# ─────────────────────────────────────────────────────────────────────────────
#  Формат совместим с фикстурой
# ─────────────────────────────────────────────────────────────────────────────

def test_profile_dict_keys_match_fixture(db):
    """Каждый профиль в экспорте имеет те же ключи, что профиль в фикстуре."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fx_keys = set(fx["object_etp_profile"][0].keys()) - {"$comment"}
    payload = build_export_payload(db)
    exp_keys = set(payload["object_etp_profile"][0].keys())
    # экспорт обязан включать все ключи фикстуры.
    assert fx_keys.issubset(exp_keys), f"missing keys: {fx_keys - exp_keys}"


def test_lot_dict_keys_match_fixture(db):
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fx_keys = set(fx["lots"][0].keys()) - {"$comment"}
    payload = build_export_payload(db)
    exp_keys = set(payload["lots"][0].keys())
    assert fx_keys.issubset(exp_keys), f"missing keys: {fx_keys - exp_keys}"


def test_json_columns_deserialized(db):
    """location_extra etc. возвращаются как dict, не строка."""
    payload = build_export_payload(db, project_slug="pirushin")
    profile = next(p for p in payload["object_etp_profile"]
                   if p["cad_number"] == "61:44:0050706:31")
    assert isinstance(profile["location_extra"], dict)
    assert "landmark" in profile["location_extra"]
    assert isinstance(profile["building_extra"], dict)


# ─────────────────────────────────────────────────────────────────────────────
#  write_export — файл
# ─────────────────────────────────────────────────────────────────────────────

def test_write_export_default_path(db, tmp_path):
    out_root = tmp_path / "exports"
    out_path = write_export(db, out_root)
    assert out_path == out_root / "object_etp_profile.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "object_etp_profile" in payload


def test_write_export_project_subdir(db, tmp_path):
    out_root = tmp_path / "exports"
    out_path = write_export(db, out_root, project_slug="pirushin")
    assert out_path == out_root / "pirushin" / "object_etp_profile.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["$project_slug"] == "pirushin"


def test_write_export_creates_missing_dirs(db, tmp_path):
    out_root = tmp_path / "deep" / "nested" / "path"
    out_path = write_export(db, out_root, project_slug="pirushin")
    assert out_path.parent.exists()
    assert out_path.exists()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_file(tmp_path) -> Path:
    """Persistent SQLite файл для CLI-тестов."""
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
    apply_osv(conn, load_osv(TEMPLATE))
    conn.commit()
    conn.close()
    return db


def test_cli_writes_file(db_file, tmp_path, capsys):
    out_root = tmp_path / "exports"
    rc = cli_main(["--db", str(db_file), "--out", str(out_root)])
    assert rc == 0
    out_path = out_root / "object_etp_profile.json"
    assert out_path.exists()
    printed = capsys.readouterr().out.strip()
    assert str(out_path) in printed


def test_cli_with_project_filter(db_file, tmp_path):
    out_root = tmp_path / "exports"
    rc = cli_main(["--db", str(db_file), "--out", str(out_root), "--project", "pirushin"])
    assert rc == 0
    assert (out_root / "pirushin" / "object_etp_profile.json").exists()


def test_cli_missing_db_returns_2(tmp_path, capsys):
    rc = cli_main(["--db", str(tmp_path / "nope.sqlite")])
    assert rc == 2
    assert "db not found" in capsys.readouterr().err
