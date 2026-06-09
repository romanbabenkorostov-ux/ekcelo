"""Тесты land_ingest: sidecar контуров → БД + текст выписки → ЕЗП (ADR-005)."""
import sqlite3

from egrn_parser.parsers import land_ingest as LI

_POLY = {"type": "Polygon", "coordinates": [[[37.1, 45.1], [37.2, 45.1], [37.2, 45.2], [37.1, 45.1]]]}
_MULTI = {"type": "MultiPolygon", "coordinates": [
    [[[37.1, 45.1], [37.2, 45.1], [37.2, 45.2], [37.1, 45.1]]],
    [[[37.5, 45.5], [37.6, 45.5], [37.6, 45.6], [37.5, 45.5]]],
]}


def _sidecar():
    return {"schema_version": "1.0", "objects": {
        "23:15:0804000:10": {"источник": "wfs", "тип": "MultiPolygon",
                             "полигонов": 2, "geojson": _MULTI},
        "23:15:0804000:11": {"источник": "pkk", "тип": "Polygon",
                             "полигонов": 1, "geojson": _POLY},
        "23:15:0804000:12": {"источник": "screenshot_cv", "тип": "Polygon",
                             "полигонов": 1, "geojson": None},  # без геометрии
    }}


def test_ingest_sidecar_mku_and_zu():
    c = sqlite3.connect(":memory:")
    res = LI.ingest_sidecar_contours(c, _sidecar())
    assert res["totals"]["written"] == 2
    assert res["totals"]["skipped"] == 1
    assert res["totals"]["contours"] == 3            # 2 (МКУ) + 1 (ЗУ)
    layouts = {w["cad"]: w["layout"] for w in res["written"]}
    assert layouts["23:15:0804000:10"] == "МКУ"
    assert layouts["23:15:0804000:11"] == "ЗУ"
    assert res["skipped_no_geom"] == ["23:15:0804000:12"]
    # в БД: 3 контура, МКУ-контуры без своего КН
    rows = c.execute("SELECT parent_cad, contour_no, contour_cad FROM land_contours "
                     "ORDER BY parent_cad, contour_no").fetchall()
    assert len(rows) == 3
    assert all(r[2] is None for r in rows)


def test_ingest_sidecar_idempotent():
    c = sqlite3.connect(":memory:")
    LI.ingest_sidecar_contours(c, _sidecar())
    LI.ingest_sidecar_contours(c, _sidecar())
    assert c.execute("SELECT COUNT(*) FROM land_contours").fetchone()[0] == 3


def test_ingest_empty_sidecar():
    c = sqlite3.connect(":memory:")
    res = LI.ingest_sidecar_contours(c, {"objects": {}})
    assert res["totals"] == {"objects": 0, "written": 0, "contours": 0, "skipped": 0}


def test_ingest_land_extract_text_ezp():
    c = sqlite3.connect(":memory:")
    text = ("Земельный участок 23:15:0804000:51 (Единое землепользование). "
            "обособленных (условных) участков, входящих в единое землепользование: "
            "23:15:0804000:52, 23:15:0804000:53 .")
    res = LI.ingest_land_extract_text(c, text)
    assert res["layout"] == "ЕЗП"
    assert res["contours"]["total"] == 2
    cads = [r[0] for r in c.execute(
        "SELECT contour_cad FROM land_contours ORDER BY contour_no")]
    assert cads == ["23:15:0804000:52", "23:15:0804000:53"]


def test_ezp_text_then_geometry_not_downgraded():
    """ЕЗП из текста, затем геометрия MultiPolygon того же КН — НЕ понижается."""
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, "
                    "name TEXT, land_layout_type TEXT);")
    c.execute("INSERT INTO land_objects(cad_number) VALUES('23:15:0804000:51')")
    LI.ingest_land_extract_text(c, "23:15:0804000:51 (Единое землепользование). "
        "входящих в единое землепользование: 23:15:0804000:52, 23:15:0804000:53 .")
    sidecar = {"objects": {"23:15:0804000:51": {"источник": "wfs",
                "тип": "MultiPolygon", "полигонов": 2, "geojson": _MULTI}}}
    LI.ingest_sidecar_contours(c, sidecar)
    assert c.execute("SELECT land_layout_type FROM land_objects").fetchone()[0] == "ЕЗП"
