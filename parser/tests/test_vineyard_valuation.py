"""Тест оценочной вьюхи виноградника (контур ЗУ × насаждение × уход), ADR-006 §J."""
import json
import sqlite3

from egrn_parser.parsers import agro_reports as R
from egrn_parser.parsers import vineyard_perechen as VP
from egrn_parser.parsers import land_db as LDB

_PLANTING = (
    "Многолетние насаждения (виноградные насаждения), расположенные на Предмете залога 66:\n"
    "Индивидуальный номер виноградного насаждения в федеральном реестре виноградных насаждений: 60-2023-00006240;\n"
    "Площадь виноградного насаждения: 16,66 га;\n"
    "Наименование сорта винограда (сорта привоя): Алиготе;\n"
    "Код сорта винограда в государственном реестре селекционных достижений, допущенных к использованию: 4950399;\n"
    "Год высадки: 2022 год;\n"
    "Наименование сорта винограда (сорта подвоя): Берландиери Х Рипариа Кобер 5 ББ;\n"
    "Количество виноградных кустов сорта винограда: 40 931 штука.\n"
)
_GEOM = {"type": "Polygon", "coordinates": [[[38.9, 45.0], [38.91, 45.0],
                                             [38.91, 45.01], [38.9, 45.01], [38.9, 45.0]]]}


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript(open("../schema/migrations/0005_agro_layer.sql").read())
    return c


def test_valuation_view_collects_land_planting_care():
    c = _db()
    # насаждение (perechen) с привязкой к КН ЗУ
    VP.ingest_plantings(c, _PLANTING, land_cad_by_pledge={66: "23:15:0804000:66"})
    # контур ЗУ (площадь/центроид)
    LDB.upsert_geometry_contours(c, "23:15:0804000:66", _GEOM)
    # пара событий ухода
    pid = c.execute("SELECT parcel_id FROM agro_parcel").fetchone()[0]
    cid = c.execute("SELECT cycle_id FROM agro_crop_cycle").fetchone()[0]
    for et in ("operation", "operation", "treatment"):
        c.execute("INSERT INTO agro_event(parcel_id,cycle_id,season_year,event_type,attrs,source,confidence)"
                  " VALUES(?,?,?,?,?,?,?)", (pid, cid, 2022, et, "{}", "techcard", 0.7))
    c.commit()

    rows = R.vineyard_valuation(c)
    assert len(rows) == 1
    v = rows[0]
    assert v["variety"] == "Алиготе"
    assert v["planting_year"] == 2022
    assert v["vine_age_years"] >= 3                  # 2026 − 2022 (зависит от 'now')
    assert v["land_cad"] == "23:15:0804000:66"
    assert v["vines_count"] == 40931
    assert v["federal_reg_no"] == "60-2023-00006240"
    assert v["contour_area_sqm"] and v["contour_area_sqm"] > 0
    assert v["centroid_lon"] is not None and v["centroid_lat"] is not None
    assert v["n_care_operations"] == 2 and v["n_treatments"] == 1


def test_valuation_view_no_contour_is_ok():
    """Без контура ЗУ (нет геометрии) — насаждение всё равно в оценке, площадь NULL."""
    c = _db()
    VP.ingest_plantings(c, _PLANTING)               # без land_cad
    rows = R.vineyard_valuation(c)
    assert len(rows) == 1
    assert rows[0]["contour_area_sqm"] is None
    assert rows[0]["n_care_operations"] == 0
