"""Тесты A: парсер техкарты виноградника (реальный образец) + ingest в агро-слой."""
import sqlite3
from pathlib import Path

import pytest

from egrn_parser.parsers import agro_techcard as TC

FIX = Path(__file__).parent / "fixtures" / "agro" / "vineyard_techcard_sample.xlsx"
pytestmark = pytest.mark.skipif(not FIX.exists(), reason="нет образца техкарты")


def test_vineyard_detected_and_meta():
    p = TC.parse_workbook(FIX)
    assert p["is_vineyard"] is True and p["crop"] == "виноград"
    assert p["meta"]["area_ha"] == 204.0
    assert p["meta"]["saplings"] == 560000


def test_operations_and_substances_counts():
    p = TC.parse_workbook(FIX)
    assert len(p["operations"]) == 54
    pest = [s for s in p["substances"] if s["kind"] == "pesticide"]
    fert = [s for s in p["substances"] if s["kind"] == "fertilizer"]
    assert len(pest) == 12 and len(fert) == 8
    polyram = next(s for s in p["substances"] if s["name"] == "Полирам")
    assert polyram["rate_per_ha"] == 2.5 and polyram["price"] == 950.0
    # годы из шапок листов (закладка 2024, уход 2025)
    assert {o["year"] for o in p["operations"] if o["year"]} == {2024, 2025}


def test_no_header_rows_leaked():
    p = TC.parse_workbook(FIX)
    for o in p["operations"]:
        assert o["unit_cost"] is not None                 # только строки с ценой
        assert not o["name"].upper().startswith("ИТОГО")


def test_to_agro_records_mapping():
    rec = TC.to_agro_records(TC.parse_workbook(FIX))
    assert rec["cycle"]["crop"] == "виноград"
    assert rec["cycle"]["cycle_kind"] == "perennial"
    assert rec["cycle"]["planting_year"] == 2024 and rec["cycle"]["season_year"] == 2025
    types = {}
    for e in rec["events"]:
        types[e["event_type"]] = types.get(e["event_type"], 0) + 1
    assert types["treatment"] == 12       # ровно 12 пестицидов СЗР
    # пестицид → active_substances
    treat = next(e for e in rec["events"]
                 if e["attrs"].get("preparation") == "Полирам")
    assert treat["attrs"]["active_substances"][0]["rate"] == 2.5


def test_non_vineyard_skipped():
    """Лист без маркеров винограда → is_vineyard=False, пустые записи."""
    import openpyxl
    tmp = FIX.parent / "_wheat_tmp.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["№", "Работа", "ед", "стоим"])
    ws.append([1, "Сев озимой пшеницы", "га", 1000])
    wb.save(tmp)
    try:
        p = TC.parse_workbook(tmp)
        assert p["is_vineyard"] is False and p["operations"] == []
        assert TC.to_agro_records(p)["parcel"] is None
    finally:
        tmp.unlink()


def _agro_db():
    c = sqlite3.connect(":memory:")
    c.executescript(open("../schema/migrations/0005_agro_layer.sql").read())
    return c


def test_ingest_into_agro_layer():
    c = _agro_db()
    res = TC.ingest(c, FIX)
    assert res["is_vineyard"] is True
    assert res["written"]["parcel"] == 1 and res["written"]["cycle"] == 1
    assert res["written"]["events"] == 74                 # 54 операции + 20 веществ
    # в БД
    assert c.execute("SELECT COUNT(*) FROM agro_parcel").fetchone()[0] == 1
    assert c.execute("SELECT crop, cycle_kind, sow_date FROM agro_crop_cycle").fetchone() \
        == ("виноград", "perennial", "2024")
    n_treat = c.execute("SELECT COUNT(*) FROM agro_event WHERE event_type='treatment'").fetchone()[0]
    assert n_treat >= 12
    # все события прошли профиль-валидацию (operation/treatment loose) → invalid пуст
    assert res["invalid"] == []


def test_ingest_non_vineyard_writes_nothing():
    import openpyxl
    tmp = FIX.parent / "_corn_tmp.xlsx"
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append([1, "Сев кукурузы", "га", 500]); wb.save(tmp)
    try:
        c = _agro_db()
        res = TC.ingest(c, tmp)
        assert res["is_vineyard"] is False
        assert c.execute("SELECT COUNT(*) FROM agro_parcel").fetchone()[0] == 0
    finally:
        tmp.unlink()
