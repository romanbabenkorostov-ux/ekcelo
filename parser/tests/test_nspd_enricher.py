"""tests/test_nspd_enricher.py — Stage 5: NSPD gap-fill в object_etp_profile."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp.nspd_enricher import (
    enrich_from_directory,
    merge_nspd_into_profile,
    normalize_permitted_uses,
    normalize_wall_material,
    normalize_year,
)
from parser.exporters.etp.nspd_enrich_cli import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    for cad in ("61:44:0050706:31", "61:44:0050706:42", "61:44:0050706:7"):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  Нормализаторы
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("кирпич", "кирпичное"),
    ("Кирпичные", "кирпичное"),
    ("ПАНЕЛЬ", "панельное"),
    ("монолит", "монолитное"),
    ("блочные стены", "блочное"),
    ("деревянные", "деревянное"),
])
def test_normalize_wall_material_known(raw, expected):
    assert normalize_wall_material(raw) == expected


def test_normalize_wall_material_unknown_passes_through():
    # Саман — не содержит ни одного known-префикса (substring match нет).
    assert normalize_wall_material("саман") == "саман"


def test_normalize_wall_material_empty():
    for v in (None, "", "   "):
        assert normalize_wall_material(v) is None


@pytest.mark.parametrize("raw,expected", [
    (1975, 1975), ("1975", 1975), ("  2010  ", 2010),
])
def test_normalize_year_ok(raw, expected):
    assert normalize_year(raw) == expected


@pytest.mark.parametrize("raw", [None, "abc", "9999", "100", ""])
def test_normalize_year_invalid(raw):
    assert normalize_year(raw) is None


def test_normalize_permitted_uses_list_joins():
    assert normalize_permitted_uses(["A", "B"]) == "A; B"
    assert normalize_permitted_uses(["A", "", "  B  "]) == "A; B"


def test_normalize_permitted_uses_string():
    assert normalize_permitted_uses("офис") == "офис"
    assert normalize_permitted_uses("  ") is None


# ─────────────────────────────────────────────────────────────────────────────
#  merge_nspd_into_profile
# ─────────────────────────────────────────────────────────────────────────────

def test_merge_creates_profile_when_none(db):
    """Объект без профиля → создаётся новый с source=nspd."""
    report = merge_nspd_into_profile(db, "61:44:0050706:31", {
        "wall_material": "кирпич",
        "year_built": 1975,
    })
    assert report.profile_created
    assert report.building_extra_filled == ["building_type", "year_built"]
    row = db.execute(
        "SELECT building_extra, source, confidence FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)).fetchone()
    payload = json.loads(row[0])
    assert payload["building_type"] == "кирпичное"
    assert payload["year_built"] == 1975
    assert row[1] == "nspd"
    assert row[2] == 0.8


def test_merge_does_not_overwrite_existing_building_fields(db):
    """Если building_extra.building_type уже есть (от osv), NSPD не трогает."""
    db.execute(
        "INSERT INTO object_etp_profile(cad_number, building_extra, source, confidence) "
        "VALUES (?, ?, 'osv', 1.0)",
        ("61:44:0050706:31",
         json.dumps({"building_type": "монолитное", "wear_degree": "хорошее"})),
    )
    db.commit()
    report = merge_nspd_into_profile(db, "61:44:0050706:31", {
        "wall_material": "кирпич",     # должен быть проигнорирован
        "year_built": 1975,            # должен быть добавлен (пусто)
    })
    assert report.building_extra_filled == ["year_built"]
    payload = json.loads(db.execute(
        "SELECT building_extra FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)).fetchone()[0])
    assert payload["building_type"] == "монолитное"   # osv сохранён
    assert payload["year_built"] == 1975              # NSPD дополнил
    assert payload["wear_degree"] == "хорошее"        # не тронут


def test_merge_skips_when_all_fields_filled(db):
    db.execute(
        "INSERT INTO object_etp_profile(cad_number, building_extra, legal_extra, "
        "source, confidence) VALUES (?,?,?,?,?)",
        ("61:44:0050706:31",
         json.dumps({"building_type": "кирпичное", "year_built": 1975}),
         json.dumps({"use_type_permitted": "офис"}),
         "osv", 1.0),
    )
    db.commit()
    report = merge_nspd_into_profile(db, "61:44:0050706:31", {
        "wall_material": "монолит",
        "year_built": 2000,
        "permitted_uses": "склад",
    })
    assert not report.changed
    assert report.skipped_reason == "all_fields_already_filled"


def test_merge_handles_year_used_fallback(db):
    """Если нет year_built, используется year_used."""
    report = merge_nspd_into_profile(db, "61:44:0050706:31", {
        "year_used": "1980",
    })
    assert "year_built" in report.building_extra_filled
    payload = json.loads(db.execute(
        "SELECT building_extra FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)).fetchone()[0])
    assert payload["year_built"] == 1980


def test_merge_permitted_uses_into_legal_extra(db):
    report = merge_nspd_into_profile(db, "61:44:0050706:31", {
        "permitted_uses": ["офисное", "торговое"],
    })
    assert report.legal_extra_filled == ["use_type_permitted"]
    payload = json.loads(db.execute(
        "SELECT legal_extra FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)).fetchone()[0])
    assert payload["use_type_permitted"] == "офисное; торговое"


def test_merge_no_actionable_fields_skips(db):
    report = merge_nspd_into_profile(db, "61:44:0050706:31", {
        "address": "г. Ростов",   # NSPD-поле, нерелевантное для нас
    })
    assert not report.changed
    assert report.skipped_reason == "no_actionable_nspd_fields"


def test_merge_fk_error_propagates(db):
    with pytest.raises(sqlite3.IntegrityError):
        merge_nspd_into_profile(db, "99:99:9999999:9", {
            "wall_material": "кирпич",
        })


# ─────────────────────────────────────────────────────────────────────────────
#  enrich_from_directory
# ─────────────────────────────────────────────────────────────────────────────

def test_enrich_from_directory_processes_files(db, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "61_44_0050706_31.json").write_text(json.dumps({
        "cad_number": "61:44:0050706:31",
        "wall_material": "кирпич",
        "year_built": 1980,
    }), encoding="utf-8")
    (nspd_dir / "61_44_0050706_42.json").write_text(json.dumps({
        "wall_material": "панель",
        "year_used": 1995,
    }), encoding="utf-8")  # cad_number отсутствует → берётся из имени файла (маска _unmask_cad)

    reports = enrich_from_directory(db, nspd_dir)
    assert len(reports) == 2
    assert all(r.changed for r in reports)

    r31 = db.execute("SELECT building_extra FROM object_etp_profile WHERE cad_number=?",
                     ("61:44:0050706:31",)).fetchone()
    payload = json.loads(r31[0])
    assert payload["building_type"] == "кирпичное"
    assert payload["year_built"] == 1980

    r42 = db.execute("SELECT building_extra FROM object_etp_profile WHERE cad_number=?",
                     ("61:44:0050706:42",)).fetchone()
    payload = json.loads(r42[0])
    assert payload["building_type"] == "панельное"
    assert payload["year_built"] == 1995


def test_enrich_from_directory_handles_array_format(db, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "session_export.json").write_text(json.dumps([
        {"cad_number": "61:44:0050706:31", "wall_material": "кирпич"},
        {"cad_number": "61:44:0050706:42", "wall_material": "монолит"},
    ]), encoding="utf-8")
    reports = enrich_from_directory(db, nspd_dir)
    assert len(reports) == 2


def test_enrich_from_directory_handles_objects_wrapper(db, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "session_export.json").write_text(json.dumps({
        "session": "x",
        "objects": [
            {"cad_number": "61:44:0050706:31", "wall_material": "кирпич"},
        ]
    }), encoding="utf-8")
    reports = enrich_from_directory(db, nspd_dir)
    assert len(reports) == 1
    assert reports[0].changed


def test_enrich_from_directory_skips_invalid_json(db, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "broken.json").write_text("not json", encoding="utf-8")
    reports = enrich_from_directory(db, nspd_dir)
    assert reports == []


def test_enrich_from_directory_records_fk_errors(db, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "99_99_9999999_9.json").write_text(json.dumps({
        "wall_material": "кирпич",
    }), encoding="utf-8")
    reports = enrich_from_directory(db, nspd_dir)
    assert len(reports) == 1
    assert reports[0].skipped_reason and "fk_error" in reports[0].skipped_reason


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
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
    for cad in ("61:44:0050706:31", "61:44:0050706:42"):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    conn.commit()
    conn.close()
    return db


def test_cli_writes_changes(db_file, tmp_path, capsys):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "61_44_0050706_31.json").write_text(json.dumps({
        "cad_number": "61:44:0050706:31",
        "wall_material": "кирпич",
    }), encoding="utf-8")

    rc = cli_main(["--db", str(db_file), "--nspd", str(nspd_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "APPLIED" in out
    assert "fields_filled: 1" in out


def test_cli_dry_run_does_not_persist(db_file, tmp_path):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    (nspd_dir / "61_44_0050706_31.json").write_text(json.dumps({
        "cad_number": "61:44:0050706:31",
        "wall_material": "кирпич",
    }), encoding="utf-8")

    rc = cli_main(["--db", str(db_file), "--nspd", str(nspd_dir), "--dry-run"])
    assert rc == 0
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 0


def test_cli_missing_db_returns_2(tmp_path, capsys):
    nspd_dir = tmp_path / "nspd"
    nspd_dir.mkdir()
    rc = cli_main(["--db", str(tmp_path / "nope.sqlite"), "--nspd", str(nspd_dir)])
    assert rc == 2
    assert "db not found" in capsys.readouterr().err


def test_cli_missing_nspd_dir_returns_2(db_file, tmp_path, capsys):
    rc = cli_main(["--db", str(db_file), "--nspd", str(tmp_path / "nope")])
    assert rc == 2
    assert "nspd dir not found" in capsys.readouterr().err
