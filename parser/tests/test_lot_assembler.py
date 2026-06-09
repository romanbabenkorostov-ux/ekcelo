"""Тесты Lot-сборщика (C5): отбор include/exclude/as_of → lots/lot_items + manifest."""
import re
import sqlite3

from egrn_parser import lot_assembler as LA


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE objects(cad_number TEXT PRIMARY KEY, object_type TEXT, updated_at TEXT);
    CREATE TABLE lots(lot_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        primary_cad_number TEXT, created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE lot_items(lot_id TEXT, cad_number TEXT, role TEXT, ord INTEGER,
        PRIMARY KEY(lot_id, cad_number));
    """)
    rows = [
        ("61:44:0050706:31", "building", "2024-01-10"),
        ("61:44:0050706:10", "land", "2024-01-10"),
        ("61:44:0050706:99", "construction", "2024-06-01"),  # позже as_of
        ("23:15:0804000:5", "land", "2024-01-10"),           # другой квартал
        ("61:44:0050706:50", "flat", "2024-01-10"),
    ]
    c.executemany("INSERT INTO objects VALUES(?,?,?)", rows)
    c.commit()
    return c


def test_select_by_glob_and_type():
    c = _db()
    m = LA.select_members(c, include={"globs": ["61:44:0050706:*"]})
    cads = [x["cad_number"] for x in m]
    assert cads == sorted(cads)                              # детерминированный порядок
    assert "23:15:0804000:5" not in cads                    # другой квартал отсеян
    # роли по типам
    role = {x["cad_number"]: x["role"] for x in m}
    assert role["61:44:0050706:10"] == "land"
    assert role["61:44:0050706:31"] == "building"
    assert role["61:44:0050706:99"] == "structure"          # construction → structure
    assert role["61:44:0050706:50"] == "room"               # flat → room


def test_exclude_wins_over_include():
    c = _db()
    m = LA.select_members(c, include={"globs": ["61:44:*"]},
                          exclude={"cads": ["61:44:0050706:50"]})
    cads = [x["cad_number"] for x in m]
    assert "61:44:0050706:50" not in cads


def test_as_of_filters_newer_objects():
    c = _db()
    m = LA.select_members(c, include={"globs": ["61:44:*"]}, as_of="2024-03-01")
    cads = [x["cad_number"] for x in m]
    assert "61:44:0050706:99" not in cads                   # updated 2024-06-01 > as_of
    m2 = LA.select_members(c, include={"globs": ["61:44:*"]}, as_of="2024-12-31")
    assert "61:44:0050706:99" in [x["cad_number"] for x in m2]


def test_assemble_lot_writes_and_manifest():
    c = _db()
    frag = LA.assemble_lot(c, "lot-A", "Тестовый лот",
                           include={"types": ["land", "building"]},
                           as_of="2024-12-31", primary_cad="61:44:0050706:31")
    # manifest-фрагмент по контракту
    assert frag["lot_id"] == "lot-A"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", frag["as_of_date"])
    assert frag["members"] == sorted(frag["members"])
    assert "23:15:0804000:5" in frag["members"]             # land другого квартала
    assert frag["include"] == {"types": ["land", "building"]}
    # запись в БД
    assert c.execute("SELECT primary_cad_number FROM lots WHERE lot_id='lot-A'").fetchone()[0] \
        == "61:44:0050706:31"
    items = c.execute("SELECT cad_number, role, ord FROM lot_items WHERE lot_id='lot-A' "
                      "ORDER BY ord").fetchall()
    assert items[0][2] == 1 and items[-1][2] == len(items)  # ord 1..N


def test_assemble_idempotent_and_deterministic():
    c = _db()
    f1 = LA.assemble_lot(c, "lot-B", "L", include={"globs": ["61:44:*"]}, as_of="2024-12-31")
    f2 = LA.assemble_lot(c, "lot-B", "L", include={"globs": ["61:44:*"]}, as_of="2024-12-31")
    assert f1["members"] == f2["members"]                   # одинаковый состав
    assert c.execute("SELECT COUNT(*) FROM lot_items WHERE lot_id='lot-B'").fetchone()[0] \
        == len(f1["members"])                               # без дублей


def test_role_override():
    c = _db()
    frag = LA.assemble_lot(c, "lot-C", "L", include={"cads": ["61:44:0050706:99"]},
                           as_of="2024-12-31", roles={"61:44:0050706:99": "equipment"})
    role = c.execute("SELECT role FROM lot_items WHERE lot_id='lot-C'").fetchone()[0]
    assert role == "equipment"
