"""tests/test_etl_checko.py — ETL: checko innogrn.db → object_etp_profile."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp.etl_checko import (
    EnrichReport,
    enrich_lot_from_checko,
    main as etl_main,
)
from parser.exporters.etp.init_db_cli import main as init_main


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

_INNOGRN_DDL = """
CREATE TABLE subjects (
    id_subject       INTEGER PRIMARY KEY AUTOINCREMENT,
    is_branch        BOOLEAN NOT NULL DEFAULT 0,
    inn              TEXT NOT NULL,
    type             TEXT NOT NULL,
    name_short       TEXT,
    is_active        BOOLEAN,
    status_text      TEXT,
    special_regime   TEXT,
    reg_date         DATE,
    termination_date DATE,
    ust_kap          REAL,
    schr             INTEGER,
    region           TEXT
);
CREATE TABLE okveds (
    id_okveds    INTEGER PRIMARY KEY AUTOINCREMENT,
    number_okved TEXT NOT NULL,
    name_okved   TEXT NOT NULL
);
CREATE TABLE subject_okveds (
    id_subject INTEGER NOT NULL,
    id_okveds  INTEGER NOT NULL,
    is_main    BOOLEAN DEFAULT FALSE
);
"""


def _make_innogrn(path: Path, subjects: list[dict], okveds: list[tuple[str, str, bool, str]] = ()) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_INNOGRN_DDL)
    for s in subjects:
        conn.execute(
            "INSERT INTO subjects(inn, type, name_short, is_active, status_text, "
            "special_regime, reg_date, termination_date, ust_kap, schr, region) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (s["inn"], s.get("type", "legal"), s.get("name_short"),
             s.get("is_active"), s.get("status_text"),
             s.get("special_regime"), s.get("reg_date"), s.get("termination_date"),
             s.get("ust_kap"), s.get("schr"), s.get("region")),
        )
    for okved_num, okved_name, is_main, inn in okveds:
        conn.execute(
            "INSERT INTO okveds(number_okved, name_okved) VALUES (?,?)",
            (okved_num, okved_name),
        )
        ok_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        sub_id = conn.execute("SELECT id_subject FROM subjects WHERE inn=?", (inn,)).fetchone()[0]
        conn.execute(
            "INSERT INTO subject_okveds(id_subject, id_okveds, is_main) VALUES (?,?,?)",
            (sub_id, ok_id, is_main),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def ek_db_with_lot(tmp_path):
    db = tmp_path / "ekcelo.sqlite"
    init_main(["--db", str(db), "--with-template"])
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    # Добавляем entity_registry + right с известным inn для cad :31.
    conn.execute(
        "INSERT INTO entity_registry(inn, name_full, entity_type) "
        "VALUES ('7707083893', 'ООО \"Тест\"', 'legal')"
    )
    conn.execute(
        "INSERT INTO rights(cad_number, right_type, right_holder_inn) "
        "VALUES ('61:44:0050706:31', 'собственность', '7707083893')"
    )
    conn.commit()
    return db, conn


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_skip_when_innogrn_db_missing(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    report = enrich_lot_from_checko(conn, tmp_path / "absent.db", "lot:pirushin:001")
    assert all(it.skipped_reason == "innogrn_db_missing" for it in report.items)
    assert report.changed_count == 0


def test_skip_when_inn_not_in_innogrn(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(innogrn, subjects=[{"inn": "9999999999", "type": "legal"}])
    report = enrich_lot_from_checko(conn, innogrn, "lot:pirushin:001")
    cad31 = next(it for it in report.items if it.cad_number == "61:44:0050706:31")
    assert cad31.skipped_reason == "inn_not_in_innogrn"
    assert cad31.inn == "7707083893"


def test_enriches_existing_profile_with_owner_checko(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(
        innogrn,
        subjects=[{
            "inn": "7707083893", "type": "legal",
            "is_active": True, "status_text": "Действует",
            "special_regime": "УСН", "reg_date": "2010-01-01",
            "ust_kap": 50000.0, "schr": 12, "region": "Ростовская область",
        }],
        okveds=[("68.20.2", "Аренда и управление недвижимостью", True, "7707083893")],
    )
    report = enrich_lot_from_checko(conn, innogrn, "lot:pirushin:001")
    conn.commit()
    cad31 = next(it for it in report.items if it.cad_number == "61:44:0050706:31")
    assert cad31.did_change
    assert "owner_checko" in cad31.legal_extra_filled

    row = conn.execute(
        "SELECT legal_extra FROM object_etp_profile WHERE cad_number='61:44:0050706:31'"
    ).fetchone()
    legal = json.loads(row[0])
    oc = legal["owner_checko"]
    assert oc["status_text"] == "Действует"
    assert oc["special_regime"] == "УСН"
    assert oc["schr"] == 12
    assert oc["main_okved"]["number"] == "68.20.2"


def test_idempotent_owner_checko_not_overwritten(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(innogrn, subjects=[{"inn": "7707083893", "type": "legal", "is_active": True}])

    enrich_lot_from_checko(conn, innogrn, "lot:pirushin:001")
    conn.commit()

    # Меняем checko-данные (имитация устаревшего кэша); второй вызов не должен перезатереть.
    conn.execute("UPDATE object_etp_profile SET source='manual' WHERE cad_number='61:44:0050706:31'")
    conn.commit()

    report2 = enrich_lot_from_checko(conn, innogrn, "lot:pirushin:001")
    cad31 = next(it for it in report2.items if it.cad_number == "61:44:0050706:31")
    assert cad31.skipped_reason == "owner_checko_already_present"


def test_skip_when_cad_has_no_right_holder(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(innogrn, subjects=[{"inn": "7707083893", "type": "legal"}])
    # CAD :7 (land) есть в lot, но без rights → no_right_holder_inn.
    report = enrich_lot_from_checko(conn, innogrn, "lot:pirushin:001")
    cad7 = next(it for it in report.items if it.cad_number == "61:44:0050706:7")
    assert cad7.skipped_reason == "no_right_holder_inn"


def test_empty_lot_yields_empty_report(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(innogrn, subjects=[])
    report = enrich_lot_from_checko(conn, innogrn, "lot:nonexistent:999")
    assert report.items == []


def test_cli_dry_run_does_not_commit(ek_db_with_lot, tmp_path, capsys):
    db, conn = ek_db_with_lot
    conn.close()
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(innogrn, subjects=[{"inn": "7707083893", "type": "legal", "is_active": True}])
    rc = etl_main([
        "--db", str(db),
        "--innogrn-db", str(innogrn),
        "--lot", "lot:pirushin:001",
        "--dry-run",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run, rolled back" in out

    # Проверяем, что БД не изменена.
    check = sqlite3.connect(db)
    row = check.execute(
        "SELECT legal_extra FROM object_etp_profile WHERE cad_number='61:44:0050706:31'"
    ).fetchone()
    legal = json.loads(row[0]) if row[0] else {}
    assert "owner_checko" not in legal
    check.close()


def test_cli_commits_changes(ek_db_with_lot, tmp_path):
    db, conn = ek_db_with_lot
    conn.close()
    innogrn = tmp_path / "innogrn.db"
    _make_innogrn(innogrn, subjects=[{"inn": "7707083893", "type": "legal", "is_active": True}])
    rc = etl_main([
        "--db", str(db),
        "--innogrn-db", str(innogrn),
        "--lot", "lot:pirushin:001",
    ])
    assert rc == 0
    check = sqlite3.connect(db)
    row = check.execute(
        "SELECT legal_extra FROM object_etp_profile WHERE cad_number='61:44:0050706:31'"
    ).fetchone()
    legal = json.loads(row[0])
    assert legal["owner_checko"]["is_active"] == 1
    check.close()
