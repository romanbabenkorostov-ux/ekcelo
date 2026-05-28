"""tests/test_init_db_cli.py — bootstrap новой SQLite для разработки."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp.init_db_cli import main as init_main


def test_creates_new_db_with_schema(tmp_path):
    db = tmp_path / "fresh.sqlite"
    rc = init_main(["--db", str(db)])
    assert rc == 0
    assert db.exists()
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"objects", "entity_registry", "rights", "object_restrictions"}.issubset(tables)
    assert {"object_etp_profile", "lots", "lot_items"}.issubset(tables)


def test_inserts_baseline_objects(tmp_path):
    db = tmp_path / "fresh.sqlite"
    init_main(["--db", str(db)])
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT cad_number FROM objects ORDER BY cad_number").fetchall()
    assert [r[0] for r in rows] == [
        "61:44:0050706:31",
        "61:44:0050706:42",
        "61:44:0050706:7",
    ]


def test_with_template_applies_osv(tmp_path):
    db = tmp_path / "fresh.sqlite"
    rc = init_main(["--db", str(db), "--with-template"])
    assert rc == 0
    conn = sqlite3.connect(db)
    profiles = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    lots = conn.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
    assert profiles == 1
    assert lots == 1


def test_existing_db_without_force_returns_1(tmp_path, capsys):
    db = tmp_path / "fresh.sqlite"
    init_main(["--db", str(db)])
    rc = init_main(["--db", str(db)])
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_force_overwrites_existing(tmp_path):
    db = tmp_path / "fresh.sqlite"
    init_main(["--db", str(db), "--with-template"])
    # Перезаписали — template не применён → 0 профилей.
    rc = init_main(["--db", str(db), "--force"])
    assert rc == 0
    conn = sqlite3.connect(db)
    profiles = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert profiles == 0


def test_template_baseline_includes_stage5_fields(tmp_path):
    """Шаблон содержит building_type, year_built, use_type_permitted (Stage 5)."""
    import json
    db = tmp_path / "fresh.sqlite"
    init_main(["--db", str(db), "--with-template"])
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT building_extra, legal_extra FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",),
    ).fetchone()
    building = json.loads(row[0])
    legal = json.loads(row[1])
    assert building["building_type"] == "кирпичное"
    assert building["year_built"] == 1975
    assert legal["use_type_permitted"]
