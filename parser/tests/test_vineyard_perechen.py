"""Тесты парсера перечня виноградных насаждений (залоговые описания) → агро-слой."""
import sqlite3
from pathlib import Path

from egrn_parser.parsers import vineyard_perechen as VP

FIX = Path(__file__).parent / "fixtures" / "agro" / "vineyard_perechen_sample.txt"
TEXT = FIX.read_text(encoding="utf-8")


def test_parse_three_plantings():
    pl = VP.parse_planting_descriptions(TEXT)
    assert len(pl) == 3
    aligote = pl[0]
    assert aligote["pledge_item"] == 66
    assert aligote["federal_reg_no"] == "60-2023-00006240"
    assert aligote["area_ha"] == 16.66
    assert aligote["variety"] == "Алиготе"
    assert aligote["variety_code"] == "4950399"
    assert aligote["area_variety_ha"] == 14.74
    assert aligote["planting_year"] == 2022
    assert aligote["rootstock"].startswith("Берландиери")
    assert aligote["vines_count"] == 40931            # «40 931» с пробелом


def test_vines_thousands_space():
    pl = VP.parse_planting_descriptions(TEXT)
    cab_sov = next(p for p in pl if p["variety"] == "Каберне Совиньон")
    assert cab_sov["vines_count"] == 3000             # «3 000»
    assert cab_sov["planting_year"] == 2021


def test_to_agro_records_with_land_link():
    pl = VP.parse_planting_descriptions(TEXT)
    recs = VP.plantings_to_agro_records(pl, land_cad_by_pledge={66: "23:15:0804000:66"})
    r0 = recs[0]
    assert r0["parcel"]["parcel_code"] == "ПЗ-66"
    assert r0["parcel"]["area_ha"] == 16.66
    assert r0["parcel"]["land_cad"] == "23:15:0804000:66"
    assert r0["parcel"]["attrs"]["federal_reg_no"] == "60-2023-00006240"
    assert r0["parcel"]["attrs"]["vines_count"] == 40931
    assert r0["cycle"]["crop"] == "виноград" and r0["cycle"]["cycle_kind"] == "perennial"
    assert r0["cycle"]["variety"] == "Алиготе" and r0["cycle"]["sow_date"] == "2022"


def _agro_db():
    c = sqlite3.connect(":memory:")
    c.executescript(open("../schema/migrations/0005_agro_layer.sql").read())
    return c


def test_ingest_plantings():
    c = _agro_db()
    res = VP.ingest_plantings(c, TEXT, land_cad_by_pledge={69: "23:15:0804000:69"})
    assert res == {"plantings": 3, "written": 3}
    assert c.execute("SELECT COUNT(*) FROM agro_parcel").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM agro_crop_cycle WHERE crop='виноград'").fetchone()[0] == 3
    # land-привязка проставлена для ПЗ-69
    cad = c.execute("SELECT land_cad FROM agro_parcel WHERE parcel_code='ПЗ-69'").fetchone()[0]
    assert cad == "23:15:0804000:69"
    # сорта в циклах
    varieties = {r[0] for r in c.execute("SELECT variety FROM agro_crop_cycle")}
    assert varieties == {"Алиготе", "Каберне Фран", "Каберне Совиньон"}


def test_empty_text():
    assert VP.parse_planting_descriptions("") == []
    assert VP.parse_planting_descriptions("просто текст без насаждений") == []
