"""Тесты экспорта объектов в KMZ: контуры + спираль внутри ЗУ (geo_kmz)."""
import sqlite3
import zipfile
from pathlib import Path

from egrn_parser import geo_kmz as K

_SQ = [[38.90, 45.00], [38.92, 45.00], [38.92, 45.02], [38.90, 45.02]]


def test_spiral_points_inside_parcel():
    pts = K.spiral_points(_SQ, 10)
    assert len(pts) == 10
    assert all(K.point_in_ring(p, _SQ) for p in pts)     # все внутри ЗУ
    # точки различны (раскладка, не одна точка)
    assert len(set(pts)) == 10


def test_spiral_empty_for_degenerate():
    assert K.spiral_points(_SQ, 0) == []
    assert K.spiral_points([[0, 0], [1, 1]], 5) == []     # < 3 вершин


def test_build_kml_contours_and_spiral():
    parcels = [{
        "cad": "23:15:0000000:2267", "polygon": [_SQ],
        "objects": [
            {"name": "ОКС-1", "geometry": {"type": "Polygon",
                "coords": [[[38.905, 45.005], [38.91, 45.005], [38.91, 45.01], [38.905, 45.005]]]}},
            {"name": "ОКС-2", "geometry": None},
            {"name": "ОКС-3", "geometry": None}]}]
    res = K.build_kml(parcels)
    assert res["stats"]["objects_with_contour"] == 1
    assert res["stats"]["objects_spiral"] == 2
    assert "<Polygon>" in res["kml"] and "<Point>" in res["kml"]


def test_build_kmz_is_valid_zip(tmp_path):
    out = tmp_path / "objects.kmz"
    res = K.build_kmz(out, [{"cad": "x", "polygon": [_SQ],
                             "objects": [{"name": "o", "geometry": None}]}])
    with zipfile.ZipFile(out) as z:
        assert "doc.kml" in z.namelist()
        assert z.read("doc.kml").decode("utf-8").startswith("<?xml")
    assert res["stats"]["objects_spiral"] == 1


def test_description_info_table_and_no_coords():
    parcels = [{
        "cad": "23:15:0000000:2267", "polygon": [_SQ],
        "info": {"Кадастровый номер": "23:15:0000000:2267", "Площадь уточнённая, кв. м": 42359},
        "objects": [
            {"name": "ОКС-к", "geometry": {"type": "Polygon",
                "coords": [[[38.905, 45.005], [38.91, 45.005], [38.91, 45.01], [38.905, 45.005]]]},
             "info": {"Наименование": "Ликерный цех"}},
            {"name": "ОКС-с", "geometry": None, "info": {"Наименование": "Склад"}}]}]
    kml = K.build_kml(parcels)["kml"]
    assert "Площадь уточнённая, кв. м" in kml and "42359" in kml      # ЗУ info
    assert "Ликерный цех" in kml                                     # контур info
    assert "Склад" in kml                                            # спираль info
    assert "Без координат границ по Росреестру" in kml               # пометка спирали
    assert "<description>" in kml and "CDATA" in kml


def test_build_kmz_writes_info_sidecar(tmp_path):
    out = tmp_path / "objects.kmz"
    res = K.build_kmz(out, [{"cad": "23:15:0000000:2267", "polygon": [_SQ],
                             "info": {"Кадастровый номер": "23:15:0000000:2267"},
                             "objects": [{"name": "o", "geometry": None, "info": {"a": "b"}}]}])
    import json
    data = json.loads(Path(res["info_json"]).read_text(encoding="utf-8"))
    assert data[0]["cad"] == "23:15:0000000:2267"
    assert data[0]["info"]["Кадастровый номер"] == "23:15:0000000:2267"
    assert data[0]["objects"][0]["geometry_type"] == "spiral"


def test_parcel_without_geometry_no_spiral():
    res = K.build_kml([{"cad": "no-geo", "polygon": None,
                        "objects": [{"name": "obj", "geometry": None}]}])
    assert res["stats"]["objects_spiral"] == 0           # спираль негде ставить
    assert "obj" in res["kml"]                            # объект помечен (комментарий)


def test_collect_from_db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE land_contours(parent_cad TEXT, contour_no INTEGER, geom_geojson TEXT);
    CREATE TABLE building_objects(cad_number TEXT, parent_cad_number TEXT);
    CREATE TABLE linked_objects(primary_cad_number TEXT, linked_cad_number TEXT);
    """)
    import json
    poly = json.dumps({"type": "Polygon", "coordinates": [_SQ]})
    c.execute("INSERT INTO land_contours VALUES('23:15:0000000:2267',1,?)", (poly,))
    c.execute("INSERT INTO building_objects VALUES('23:15:0000000:100','23:15:0000000:2267')")
    c.execute("INSERT INTO linked_objects VALUES('23:15:0000000:2267','23:15:0000000:200')")
    c.commit()
    parcels = K.collect_from_db(c, ["23:15:0000000:2267"])
    assert len(parcels) == 1
    assert parcels[0]["polygon"] is not None
    cads = {o["name"] for o in parcels[0]["objects"]}
    assert cads == {"23:15:0000000:100", "23:15:0000000:200"}
    # у объектов геометрии нет → при сборке KMZ уйдут в спираль
    res = K.build_kml(parcels)
    assert res["stats"]["objects_spiral"] == 2


def test_collect_modes_select():
    """Режимы a/в/г выбирают разные источники объектов."""
    import json
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE land_contours(parent_cad TEXT,contour_no INTEGER,geom_geojson TEXT,geom_source TEXT);
    CREATE TABLE building_objects(cad_number TEXT,parent_cad_number TEXT);
    CREATE TABLE agro_parcel(parcel_id INTEGER PRIMARY KEY,parcel_code TEXT,land_cad TEXT,
        geom_geojson TEXT,season_year INT,source TEXT,confidence REAL);
    """)
    c.execute("INSERT INTO land_contours VALUES('P',1,?,'nspd')",
              (json.dumps({"type":"Polygon","coordinates":[_SQ]}),))
    c.execute("INSERT INTO building_objects VALUES('B1','P')")
    c.execute("INSERT INTO agro_parcel VALUES(1,'vino','P',NULL,2024,'perechen',0.7)")
    c.commit()
    only_linked = K.collect_from_db(c, ["P"], modes=["a"])[0]["objects"]
    assert [o["name"] for o in only_linked] == ["B1"]
    only_agro = K.collect_from_db(c, ["P"], modes=["в"])[0]["objects"]
    assert [o["name"] for o in only_agro] == ["агро:vino"]
    all3 = {o["name"] for o in K.collect_from_db(c, ["P"])[0]["objects"]}
    assert {"B1", "агро:vino"} <= all3


def test_nspd_fetch_fallback():
    """2в: у ЗУ нет контура в БД → берётся из geometry_fetcher (NSPD) и кэшируется."""
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE land_contours(parent_cad TEXT,contour_no INTEGER,geom_geojson TEXT,geom_source TEXT);")
    fetched = K.collect_from_db(c, ["NOGEO"], modes=["a"],
                                geometry_fetcher=lambda cad: {"type":"Polygon","coordinates":[_SQ]})
    assert fetched[0]["polygon"] is not None
    # закэшировано в land_contours
    assert c.execute("SELECT COUNT(*) FROM land_contours WHERE parent_cad='NOGEO'").fetchone()[0] == 1


def test_building_sources_order_and_cads():
    """Источники строений: nspd(2)+db(1)+cads(3) комбинируются, дедуп по КН."""
    import json
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE land_contours(parent_cad TEXT,contour_no INTEGER,geom_geojson TEXT,geom_source TEXT)")
    c.execute("INSERT INTO land_contours VALUES('P',1,?,'nspd')",
              (json.dumps({"type": "Polygon", "coordinates": [_SQ]}),))
    c.commit()
    parcels = K.collect_from_db(
        c, ["P"], building_sources=("nspd", "db", "cads"),
        building_discovery=lambda poly: [{"name": "DISC", "geometry": {"type": "Polygon", "coords": [_SQ]}}],
        extra_building_cads=["LIST1"])
    names = [o["name"] for o in parcels[0]["objects"]]
    assert "DISC" in names and "LIST1" in names       # обнаружение + список
