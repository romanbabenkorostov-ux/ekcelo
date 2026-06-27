"""Тесты экспорта объектов в KMZ: контуры + спираль внутри ЗУ (geo_kmz)."""
import sqlite3
import zipfile

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
