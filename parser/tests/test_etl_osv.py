"""tests/test_etl_osv.py — Stage 4: импорт survey-листа в БД."""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from parser.exporters.etp.etl_osv import apply_osv, load_osv


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
SAMPLE_TEMPLATE = REPO_ROOT / "parser" / "exporters" / "etp" / "templates" / "osv_template.yaml"


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """In-memory БД с миграцией + минимальной objects (для FK)."""
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


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "survey.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  Loader: schema + validation
# ─────────────────────────────────────────────────────────────────────────────

def test_load_template_succeeds():
    doc = load_osv(SAMPLE_TEMPLATE)
    assert doc.schema_version == "1.0"
    assert doc.default_source == "osv"
    assert len(doc.profiles) >= 1
    assert len(doc.lots) >= 1


def test_load_empty_top_level_yaml(tmp_path):
    doc = load_osv(_write_yaml(tmp_path, ""))
    assert doc.profiles == []
    assert doc.lots == []


def test_load_rejects_unknown_source(tmp_path):
    bad = _write_yaml(tmp_path, """
        default_source: gpt5
    """)
    with pytest.raises(ValueError, match="default_source"):
        load_osv(bad)


def test_load_rejects_confidence_out_of_range(tmp_path):
    bad = _write_yaml(tmp_path, """
        profiles:
          - cad_number: "61:44:0050706:31"
            confidence: 1.5
    """)
    with pytest.raises(ValueError, match="confidence"):
        load_osv(bad)


def test_load_rejects_lot_id_bad_charset(tmp_path):
    bad = _write_yaml(tmp_path, """
        lots:
          - lot_id: "лот:001"
            name: x
    """)
    with pytest.raises(ValueError, match="lot_id"):
        load_osv(bad)


def test_load_rejects_lot_id_too_long(tmp_path):
    bad = _write_yaml(tmp_path, f"""
        lots:
          - lot_id: "lot:{'a' * 300}"
            name: x
    """)
    with pytest.raises(ValueError, match="lot_id"):
        load_osv(bad)


def test_load_rejects_duplicate_cad_number(tmp_path):
    bad = _write_yaml(tmp_path, """
        profiles:
          - cad_number: "61:44:0050706:31"
          - cad_number: "61:44:0050706:31"
    """)
    with pytest.raises(ValueError, match="Duplicate profile"):
        load_osv(bad)


def test_load_rejects_duplicate_lot_id(tmp_path):
    bad = _write_yaml(tmp_path, """
        lots:
          - lot_id: "lot:a:1"
            name: x
          - lot_id: "lot:a:1"
            name: y
    """)
    with pytest.raises(ValueError, match="Duplicate lot_id"):
        load_osv(bad)


def test_load_rejects_bad_role(tmp_path):
    bad = _write_yaml(tmp_path, """
        lots:
          - lot_id: "lot:a:1"
            name: x
            items:
              - cad_number: "61:44:0050706:31"
                role: garage
    """)
    with pytest.raises(ValueError, match="role"):
        load_osv(bad)


def test_load_rejects_bad_deal_type(tmp_path):
    bad = _write_yaml(tmp_path, """
        lots:
          - lot_id: "lot:a:1"
            name: x
            deal_type: mortgage
    """)
    with pytest.raises(ValueError, match="deal_type"):
        load_osv(bad)


# ─────────────────────────────────────────────────────────────────────────────
#  Apply: insert / update / replace items
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_inserts_profile(db, tmp_path):
    yaml = _write_yaml(tmp_path, """
        profiles:
          - cad_number: "61:44:0050706:31"
            location_extra:
              landmark: "у парка"
    """)
    report = apply_osv(db, load_osv(yaml))
    assert report.profiles_inserted == 1
    assert report.profiles_updated == 0
    row = db.execute("SELECT location_extra, source, confidence FROM object_etp_profile WHERE cad_number=?",
                     ("61:44:0050706:31",)).fetchone()
    assert row is not None
    assert "парка" in row[0]
    assert row[1] == "osv"
    assert row[2] == 1.0


def test_apply_updates_existing_profile(db, tmp_path):
    db.execute(
        "INSERT INTO object_etp_profile(cad_number, source, confidence) VALUES (?, 'nspd', 0.6)",
        ("61:44:0050706:31",),
    )
    db.commit()
    yaml = _write_yaml(tmp_path, """
        profiles:
          - cad_number: "61:44:0050706:31"
            confidence: 1.0
            location_extra:
              landmark: "после правки"
    """)
    report = apply_osv(db, load_osv(yaml))
    assert report.profiles_inserted == 0
    assert report.profiles_updated == 1
    row = db.execute("SELECT source, confidence, location_extra FROM object_etp_profile WHERE cad_number=?",
                     ("61:44:0050706:31",)).fetchone()
    assert row[0] == "osv"   # default_source перекрыл 'nspd'
    assert row[1] == 1.0
    assert "правки" in row[2]


def test_apply_inserts_lot_with_items(db, tmp_path):
    yaml = _write_yaml(tmp_path, """
        lots:
          - lot_id: "lot:test:001"
            name: "Test lot"
            deal_type: sale
            procedure_type: "приватизации"
            primary_cad_number: "61:44:0050706:31"
            platform_targets: [torgi.gov.ru, sberbank-ast.ru]
            items:
              - { cad_number: "61:44:0050706:31", role: room, ord: 1 }
              - { cad_number: "61:44:0050706:7",  role: land, ord: 2 }
    """)
    report = apply_osv(db, load_osv(yaml))
    assert report.lots_inserted == 1
    assert report.lot_items_inserted == 2
    items = db.execute("SELECT cad_number, role, ord FROM lot_items WHERE lot_id=? ORDER BY ord",
                       ("lot:test:001",)).fetchall()
    assert items == [("61:44:0050706:31", "room", 1), ("61:44:0050706:7", "land", 2)]


def test_apply_replaces_lot_items_on_update(db, tmp_path):
    """Повторный импорт лота с новым набором items → старые items удалены."""
    yaml1 = _write_yaml(tmp_path, """
        lots:
          - lot_id: "lot:test:002"
            name: "v1"
            items:
              - { cad_number: "61:44:0050706:31", role: room, ord: 1 }
              - { cad_number: "61:44:0050706:42", role: room, ord: 2 }
    """)
    apply_osv(db, load_osv(yaml1))
    yaml2 = _write_yaml(tmp_path, """
        lots:
          - lot_id: "lot:test:002"
            name: "v2"
            items:
              - { cad_number: "61:44:0050706:7", role: land, ord: 1 }
    """)
    report = apply_osv(db, load_osv(yaml2))
    assert report.lots_updated == 1
    assert report.lot_items_inserted == 1
    assert report.lot_items_deleted == 2
    items = db.execute("SELECT cad_number FROM lot_items WHERE lot_id=?",
                       ("lot:test:002",)).fetchall()
    assert items == [("61:44:0050706:7",)]


def test_apply_dry_run_does_not_persist(db, tmp_path):
    yaml = _write_yaml(tmp_path, """
        profiles:
          - cad_number: "61:44:0050706:42"
            location_extra: { landmark: "x" }
    """)
    report = apply_osv(db, load_osv(yaml), dry_run=True)
    assert report.dry_run is True
    assert report.profiles_inserted == 1
    rows = db.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 0


def test_apply_rolls_back_on_fk_error(db, tmp_path):
    """FK к objects: КН :999 нет — должен откатиться целиком."""
    yaml = _write_yaml(tmp_path, """
        profiles:
          - cad_number: "61:44:0050706:42"
            location_extra: { landmark: "ok" }
          - cad_number: "61:44:0050706:999"
            location_extra: { landmark: "bad" }
    """)
    with pytest.raises(sqlite3.IntegrityError):
        apply_osv(db, load_osv(yaml))
    # Первая запись не должна остаться (rollback).
    rows = db.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 0


def test_apply_default_source_and_confidence(db, tmp_path):
    yaml = _write_yaml(tmp_path, """
        default_source: nspd
        default_confidence: 0.7
        profiles:
          - cad_number: "61:44:0050706:31"
    """)
    apply_osv(db, load_osv(yaml))
    row = db.execute("SELECT source, confidence FROM object_etp_profile WHERE cad_number=?",
                     ("61:44:0050706:31",)).fetchone()
    assert row == ("nspd", 0.7)


def test_apply_template_end_to_end(db):
    """Полный шаблон osv_template.yaml применяется без ошибок."""
    doc = load_osv(SAMPLE_TEMPLATE)
    report = apply_osv(db, doc)
    assert report.profiles_inserted == 1
    assert report.lots_inserted == 1
    assert report.lot_items_inserted == 2
