"""Тесты единого gap-fill merge ЭТП-слоя §6 (приоритет источников, item 5)."""
import json
import sqlite3

from egrn_parser import etp_merge as EM


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE object_etp_profile(
        cad_number TEXT PRIMARY KEY, location_extra TEXT, building_extra TEXT,
        layout TEXT, legal_extra TEXT, risks TEXT, extras TEXT,
        source TEXT NOT NULL, confidence REAL NOT NULL,
        updated_at TEXT DEFAULT(datetime('now')));
    """)
    return c


CAD = "61:44:0050706:31"


def test_create_then_gapfill_no_overwrite():
    c = _db()
    # manual задаёт износ
    EM.merge_profile(c, CAD, {"building_extra": {"wear_degree": 35}},
                     source="manual", confidence=0.95)
    # nspd (ниже) пытается перезаписать износ + добавить материал
    res = EM.merge_profile(c, CAD,
        {"building_extra": {"wear_degree": 60, "wall_material": "кирпичное"}},
        source="nspd", confidence=0.8)
    be = json.loads(c.execute("SELECT building_extra FROM object_etp_profile").fetchone()[0])
    assert be["wear_degree"] == 35                 # manual не затёрт nspd
    assert be["wall_material"] == "кирпичное"      # пустое поле заполнено
    assert res["overwrite"] is False
    # ROW source остаётся manual (выше)
    assert c.execute("SELECT source FROM object_etp_profile").fetchone()[0] == "manual"


def test_higher_source_overwrites_lower():
    c = _db()
    EM.merge_profile(c, CAD, {"building_extra": {"wear_degree": 60}},
                     source="nspd", confidence=0.8)
    EM.merge_profile(c, CAD, {"building_extra": {"wear_degree": 35}},
                     source="manual", confidence=0.95)            # выше → перезапись
    be = json.loads(c.execute("SELECT building_extra FROM object_etp_profile").fetchone()[0])
    assert be["wear_degree"] == 35
    assert c.execute("SELECT source FROM object_etp_profile").fetchone()[0] == "manual"


def test_idempotent():
    c = _db()
    EM.merge_profile(c, CAD, {"layout": {"finish_level": "стандарт"}},
                     source="osv", confidence=0.9)
    r2 = EM.merge_profile(c, CAD, {"layout": {"finish_level": "стандарт"}},
                          source="osv", confidence=0.9)
    assert r2["fields_changed"] == 0               # ничего не изменилось
    assert c.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0] == 1


def test_nested_gapfill():
    c = _db()
    EM.merge_profile(c, CAD, {"building_extra": {"engineering": {"heating": "центр."}}},
                     source="manual", confidence=0.9)
    EM.merge_profile(c, CAD, {"building_extra": {"engineering": {"water": "есть",
                                                                 "heating": "автоном."}}},
                     source="exif", confidence=0.5)
    eng = json.loads(c.execute("SELECT building_extra FROM object_etp_profile").fetchone()[0])["engineering"]
    assert eng["heating"] == "центр."              # manual сохранён (вложенно)
    assert eng["water"] == "есть"                  # пустое заполнено


def test_empty_incoming_ignored():
    c = _db()
    EM.merge_profile(c, CAD, {"extras": {"notes": "важное"}}, source="osv", confidence=0.9)
    EM.merge_profile(c, CAD, {"extras": {"notes": "", "furniture": None}},
                     source="manual", confidence=0.95)
    ex = json.loads(c.execute("SELECT extras FROM object_etp_profile").fetchone()[0])
    assert ex["notes"] == "важное"                 # пустое manual не затёрло
    assert "furniture" not in ex


def test_unknown_source_rejected():
    c = _db()
    try:
        EM.merge_profile(c, CAD, {"extras": {}}, source="checko", confidence=0.5)
        assert False
    except ValueError as e:
        assert "checko" in str(e)


def test_etp_layer_present():
    c = _db()
    assert EM.etp_layer_present(c) is False
    EM.merge_profile(c, CAD, {"extras": {"notes": "x"}}, source="osv", confidence=0.9)
    assert EM.etp_layer_present(c) is True
