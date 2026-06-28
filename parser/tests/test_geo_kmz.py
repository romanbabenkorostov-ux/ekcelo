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


def test_layer_order_and_styles():
    parcels = [{"cad": "ЗУ1", "kind": "zu", "polygon": [_SQ],
                "objects": [
                    {"name": "ОКС-к", "geometry": {"type": "Polygon",
                        "coords": [[[38.905, 45.005], [38.906, 45.005], [38.906, 45.006], [38.905, 45.005]]]}},
                    {"name": "ОКС-с", "geometry": None}]}]
    kml = K.build_kml(parcels)["kml"]
    # порядок слоёв: ЗУ → строения → точки
    i_zu = kml.index("Земельные участки")
    i_oks = kml.index("Строения (контуры)")
    i_pt = kml.index("Точки")
    assert i_zu < i_oks < i_pt
    # стили: ЗУ зелёный (ff00ff00), ОКС красный (ff0000ff), бордер 2
    assert "ff00ff00" in kml and "3300ff00" in kml      # зелёный + заливка ~80%
    assert "ff0000ff" in kml and "330000ff" in kml      # красный + заливка ~80%
    assert "<width>2</width>" in kml


def test_description_note_on_top():
    kml = K.build_kml([{"cad": "ЗУ", "polygon": [_SQ],
                        "objects": [{"name": "o", "geometry": None,
                                     "info": {"Наименование": "Склад"}}]}])["kml"]
    note = "Без координат границ по Росреестру"
    # пометка идёт ВЫШЕ атрибутов в табличке
    assert kml.index(note) < kml.index("Наименование")


def test_yandex_json_latlon_order_and_note():
    parcels = [{"cad": "23:15:0000000:2267", "kind": "zu", "polygon": [_SQ],
                "objects": [{"name": "ОКС-с", "geometry": None}]}]
    js = K._json_from_rendered(K._render_parcels(parcels))
    # ЗУ: полигон в порядке Яндекса [lat, lon]
    lat, lon = js[0]["geometry"]["coordinates"][0][0]
    assert 44 < lat < 46 and 38 < lon < 39
    # объект без координат → точка + пометка
    assert js[0]["objects"][0]["geometry"]["type"] == "Point"
    assert js[0]["objects"][0]["note"] == K._NO_COORDS_NOTE


def test_oks_as_input_polygon():
    # одиночный ОКС (kind='oks') со своим контуром — без объектов внутри
    parcels = [{"cad": "23:15:0000000:3189", "kind": "oks", "polygon": [_SQ],
                "info": {"Наименование": "Ликерный цех"}, "objects": []}]
    res = K.build_kml(parcels)
    assert "ОКС 23:15:0000000:3189" in res["kml"]
    assert res["stats"]["parcels_with_geom"] == 1


def test_oks_as_input_point_no_coords():
    parcels = [{"cad": "23:15:0000000:3189", "kind": "oks", "polygon": None,
                "point": [38.91, 45.01], "info": {}, "objects": []}]
    js = K._json_from_rendered(K._render_parcels(parcels))
    assert js[0]["geometry"]["type"] == "Point"
    assert js[0]["note"] == K._NO_COORDS_NOTE


def test_merge_previous_keeps_contour(tmp_path):
    # прошлый JSON: у объекта был контур
    prev = [{"cad": "ЗУ", "geometry": None, "objects": [
        {"cad": "ОКС1", "geometry": {"type": "Polygon",
            "coordinates": [[[45.0, 38.9], [45.0, 38.91], [45.01, 38.91], [45.0, 38.9]]]}}]}]
    pj = tmp_path / "prev.json"
    import json
    pj.write_text(json.dumps(prev, ensure_ascii=False), encoding="utf-8")
    # сейчас ОКС1 без контура → должен подхватить старый
    parcels = [{"cad": "ЗУ", "polygon": [_SQ],
                "objects": [{"name": "ОКС1", "geometry": None}]}]
    merged = K.merge_previous(parcels, pj)
    assert merged[0]["objects"][0]["geometry"]["type"] == "Polygon"


def test_output_basename():
    from datetime import datetime
    when = datetime(2026, 6, 28, 15, 30, 0)
    assert K.output_basename(["23:15:0000000:2267"], when) == "23_15_0000000_2267_20260628_153000"
    assert K.output_basename(["23:15:0000000:2267", "23:15:0314001:911"], when) == \
        "23_15_0000000_2267_и_далее_20260628_153000"


def test_build_outputs_three_files(tmp_path):
    res = K.build_outputs(tmp_path / "base", [{"cad": "x", "polygon": [_SQ],
                                               "objects": [{"name": "o", "geometry": None}]}])
    assert Path(res["kmz"]).exists() and Path(res["kml"]).exists() and Path(res["json"]).exists()
    assert Path(res["kml"]).read_text(encoding="utf-8").startswith("<?xml")


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
    # объект без контура → точка по спирали + пометка «без координат»
    o = data[0]["objects"][0]
    assert o["geometry"]["type"] == "Point" and o["note"] == K._NO_COORDS_NOTE


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
