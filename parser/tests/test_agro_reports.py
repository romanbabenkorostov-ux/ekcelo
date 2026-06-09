"""Тесты E: агро-агрегаты (урожай по сортам, сроки, пест. нагрузка, техсхема лота)."""
import json
import sqlite3

from egrn_parser.parsers import agro_reports as R


def _db():
    """Минимальный агро-слой + синтетические события (виноград, 2 сорта, лот L1)."""
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE agro_parcel(parcel_id INTEGER PRIMARY KEY, parcel_code TEXT,
        season_year INTEGER, area_ha REAL, lot_id TEXT);
    CREATE TABLE agro_crop_cycle(cycle_id INTEGER PRIMARY KEY, parcel_id INTEGER,
        cycle_kind TEXT, crop TEXT, variety TEXT, sow_date TEXT, harvest_date TEXT,
        season_year INTEGER, agro_season TEXT, crop_status TEXT);
    CREATE TABLE agro_event(event_id INTEGER PRIMARY KEY, parcel_id INTEGER,
        cycle_id INTEGER, season_year INTEGER, event_type TEXT, event_date TEXT, attrs TEXT);
    """)
    c.execute("INSERT INTO agro_parcel VALUES(1,'уч.519',2025,4.06,'L1')")
    c.execute("INSERT INTO agro_parcel VALUES(2,'уч.714',2025,11.39,'L1')")
    c.execute("INSERT INTO agro_crop_cycle VALUES(1,1,'perennial','виноград','Одесский Чёрный','2021-04-01',NULL,2025,'2025','fact')")
    c.execute("INSERT INTO agro_crop_cycle VALUES(2,2,'perennial','виноград','Мерло','2022-04-01',NULL,2025,'2025','fact')")
    c.execute("INSERT INTO agro_crop_cycle VALUES(3,1,'perennial','виноград','Каберне',NULL,NULL,2025,'2025','plan')")  # план — не в техсхеме
    # сборы: уч.519 два прохода (разная кислотность), уч.714 один
    ev = [
        (1, 1, 1, 2025, "harvest", "2025-09-10", {"variety": "Одесский Чёрный", "volume_kg": 5000, "acidity_g_l": 6.5}),
        (2, 1, 1, 2025, "harvest", "2025-09-25", {"variety": "Одесский Чёрный", "volume_kg": 3000, "acidity_g_l": 5.8}),
        (3, 2, 2, 2025, "harvest", "2025-09-18", {"variety": "Мерло", "volume_kg": 11000, "sugar_brix": 23.4}),
        # обработка: 2 действующих вещества
        (4, 1, 1, 2025, "treatment", "2025-06-01", {"kind": "опрыскивание",
            "active_substances": [{"name": "сера", "rate": 4.0, "unit": "кг/га"},
                                  {"name": "медь", "rate": 1.5, "unit": "кг/га"}]}),
        (5, 2, 2, 2025, "treatment", "2025-06-05", {"kind": "опрыскивание",
            "active_substances": [{"name": "сера", "rate": 2.0, "unit": "кг/га"}]}),
    ]
    for eid, pid, cid, yr, et, dt, attrs in ev:
        c.execute("INSERT INTO agro_event VALUES(?,?,?,?,?,?,?)",
                  (eid, pid, cid, yr, et, dt, json.dumps(attrs, ensure_ascii=False)))
    c.commit()
    return c


def test_harvest_by_variety():
    rows = {r["variety"]: r for r in R.harvest_by_variety(_db())}
    assert rows["Одесский Чёрный"]["volume_kg"] == 8000      # 5000+3000
    assert rows["Одесский Чёрный"]["harvest_events"] == 2
    assert rows["Мерло"]["volume_kg"] == 11000


def test_harvest_timing_sorted_with_quality():
    rows = R.harvest_timing(_db())
    assert [r["event_date"] for r in rows] == ["2025-09-10", "2025-09-18", "2025-09-25"]
    first = rows[0]
    assert first["acidity_g_l"] == 6.5 and first["volume_kg"] == 5000


def test_pesticide_load_unrolled():
    rows = {r["active_substance"]: r for r in R.pesticide_load(_db())}
    # сера применена на двух полях (4.0 + 2.0), но группировка по полю → 2 строки
    sera = [r for r in R.pesticide_load(_db()) if r["active_substance"] == "сера"]
    assert sum(r["total_rate"] for r in sera) == 6.0
    assert rows["медь"]["total_rate"] == 1.5
    assert rows["медь"]["unit"] == "кг/га"


def test_lot_techscheme_fact_only():
    rows = R.lot_techscheme(_db())
    # только fact-циклы (план «Каберне» исключён) → 2 строки
    assert len(rows) == 2
    varieties = {r["variety"] for r in rows}
    assert varieties == {"Одесский Чёрный", "Мерло"}
    assert all(r["lot_id"] == "L1" for r in rows)
    merlot = next(r for r in rows if r["variety"] == "Мерло")
    assert merlot["area_ha"] == 11.39


def test_empty_db_no_crash():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE agro_parcel(parcel_id INTEGER PRIMARY KEY, parcel_code TEXT,
        season_year INTEGER, area_ha REAL, lot_id TEXT);
    CREATE TABLE agro_crop_cycle(cycle_id INTEGER PRIMARY KEY, parcel_id INTEGER,
        cycle_kind TEXT, crop TEXT, variety TEXT, sow_date TEXT, harvest_date TEXT,
        season_year INTEGER, agro_season TEXT, crop_status TEXT);
    CREATE TABLE agro_event(event_id INTEGER PRIMARY KEY, parcel_id INTEGER,
        cycle_id INTEGER, season_year INTEGER, event_type TEXT, event_date TEXT, attrs TEXT);
    """)
    assert R.harvest_by_variety(c) == [] and R.pesticide_load(c) == []


def test_migration_0008_executable():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE agro_parcel(parcel_id INTEGER PRIMARY KEY, parcel_code TEXT,
        season_year INTEGER, area_ha REAL, lot_id TEXT);
    CREATE TABLE agro_crop_cycle(cycle_id INTEGER PRIMARY KEY, parcel_id INTEGER,
        cycle_kind TEXT, crop TEXT, variety TEXT, sow_date TEXT, harvest_date TEXT,
        season_year INTEGER, agro_season TEXT, crop_status TEXT);
    CREATE TABLE agro_event(event_id INTEGER PRIMARY KEY, parcel_id INTEGER,
        cycle_id INTEGER, season_year INTEGER, event_type TEXT, event_date TEXT, attrs TEXT);
    """)
    c.executescript(open("../schema/migrations/0008_agro_aggregates.sql").read())
    n = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name LIKE 'v_agro_%'").fetchone()[0]
    assert n == 4
