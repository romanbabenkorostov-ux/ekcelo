"""tests/test_land_db.py — извлечение ЕЗП + запись land_contours (ADR-005)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import land_layout as L  # noqa: E402
from egrn_parser.parsers import land_db as DB      # noqa: E402

# Синтетическая ЕЗП-выписка (структура Росреестра, без ПД)
EZP_TEXT = """Земельный участок
23:15:0804000:51(Единое землепользование)
Категория земель:
Земли сельскохозяйственного назначения
Особые отметки:
Кадастровые номера обособленных (условных) участков, входящих в единое землепользование:
23:15:0804000:132, 23:15:0804000:133, 23:15:0804000:134, 23:15:0804000:139,
23:15:0804000:52, 23:15:0804000:54.

Получатель выписки:
"""


def test_parse_land_extract_ezp():
    r = L.parse_land_extract(EZP_TEXT)
    assert r["cad_number"] == "23:15:0804000:51"   # пометка снята
    assert r["layout"] == "ЕЗП"
    assert r["children"] == ["23:15:0804000:132", "23:15:0804000:133",
                             "23:15:0804000:134", "23:15:0804000:139",
                             "23:15:0804000:52", "23:15:0804000:54"]


def test_upsert_land_extract_writes_contours():
    r = L.parse_land_extract(EZP_TEXT)
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, name TEXT);")
    c.execute("INSERT INTO land_objects(cad_number) VALUES(?)", (r["cad_number"],))
    res = DB.upsert_land_extract(c, r)
    assert res["layout_set"] is True
    assert res["contours"]["inserted"] == 6
    assert c.execute("SELECT land_layout_type FROM land_objects").fetchone()[0] == "ЕЗП"
    rows = c.execute("SELECT contour_no, contour_cad FROM land_contours "
                     "ORDER BY contour_no").fetchall()
    assert rows[0] == (1, "23:15:0804000:132")
    assert len(rows) == 6


def test_upsert_idempotent():
    r = L.parse_land_extract(EZP_TEXT)
    c = sqlite3.connect(":memory:")
    DB.upsert_land_extract(c, r)
    res2 = DB.upsert_land_extract(c, r)
    assert res2["contours"]["inserted"] == 0
    assert c.execute("SELECT COUNT(*) FROM land_contours").fetchone()[0] == 6


def test_works_without_land_objects_table():
    # БД без land_objects — пишем только контуры, layout_set=False
    r = L.parse_land_extract(EZP_TEXT)
    c = sqlite3.connect(":memory:")
    res = DB.upsert_land_extract(c, r)
    assert res["layout_set"] is False
    assert res["contours"]["inserted"] == 6


def test_zu_no_children():
    r = L.parse_land_extract("Земельный участок\n23:15:0804000:777\nПлощадь, м2:\n5000")
    assert r["layout"] == "ЗУ" and r["children"] == []


_MULTIPOLY = {"type": "MultiPolygon", "coordinates": [
    [[[37.1, 45.1], [37.2, 45.1], [37.2, 45.2], [37.1, 45.1]]],
    [[[37.5, 45.5], [37.6, 45.5], [37.6, 45.6], [37.5, 45.5]]],
    [[[37.8, 45.8], [37.9, 45.8], [37.9, 45.9], [37.8, 45.8]]],
]}


def test_mku_from_geometry():
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, name TEXT, "
                    "land_layout_type TEXT);")
    c.execute("INSERT INTO land_objects(cad_number) VALUES('23:15:0804000:100')")
    res = DB.upsert_geometry_contours(c, "23:15:0804000:100", _MULTIPOLY)
    assert res["layout"] == "МКУ"                       # ≥2 контуров
    assert res["contours"]["inserted"] == 3
    assert c.execute("SELECT land_layout_type FROM land_objects").fetchone()[0] == "МКУ"
    # у МКУ-контуров нет своего КН
    cads = c.execute("SELECT contour_cad FROM land_contours").fetchall()
    assert all(x[0] is None for x in cads)
    # геометрия — Polygon на контур
    g = c.execute("SELECT geom_geojson FROM land_contours WHERE contour_no=1").fetchone()[0]
    assert '"Polygon"' in g


def test_single_polygon_is_zu():
    poly = {"type": "Polygon", "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 1]]]}
    c = sqlite3.connect(":memory:")
    res = DB.upsert_geometry_contours(c, "23:15:0804000:5", poly)
    assert res["layout"] == "ЗУ" and res["contours"]["inserted"] == 1


def test_geometry_contours_idempotent():
    c = sqlite3.connect(":memory:")
    DB.upsert_geometry_contours(c, "x", _MULTIPOLY)
    res2 = DB.upsert_geometry_contours(c, "x", _MULTIPOLY)
    assert res2["contours"]["inserted"] == 0
    assert c.execute("SELECT COUNT(*) FROM land_contours").fetchone()[0] == 3


def test_ezp_geometry_not_downgraded_to_mku():
    """ЕЗП-геометрия — тоже MultiPolygon, но НЕ должна понижать ЕЗП до МКУ
    и не должна затирать дочерние КН контуров NULL-cad полигонами."""
    cad = "23:15:0804000:51"
    children = ["23:15:0804000:52", "23:15:0804000:53", "23:15:0804000:54"]
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, name TEXT, "
                    "land_layout_type TEXT);")
    c.execute("INSERT INTO land_objects(cad_number) VALUES(?)", (cad,))
    DB.upsert_land_extract(c, {"cad_number": cad, "layout": "ЕЗП", "children": children})
    res = DB.upsert_geometry_contours(c, cad, _MULTIPOLY, name="Единое землепользование")
    assert res["layout"] == "ЕЗП" and res["contours"]["inserted"] == 0
    assert c.execute("SELECT land_layout_type FROM land_objects").fetchone()[0] == "ЕЗП"
    cads = [r[0] for r in c.execute(
        "SELECT contour_cad FROM land_contours ORDER BY contour_no")]
    assert cads == children          # дочерние КН целы, NULL-cad не добавлены


def test_explicit_layout_override():
    c = sqlite3.connect(":memory:")
    res = DB.upsert_geometry_contours(c, "z", _MULTIPOLY, layout="ЕЗП")
    assert res["layout"] == "ЕЗП" and res["contours"]["inserted"] == 0
