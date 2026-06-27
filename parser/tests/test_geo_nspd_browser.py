"""Тесты офлайн-ядра geo_nspd_browser: разбор geoportal-ответа, репроекция,
выбор feature ЗУ, обнаружение ОКС. Браузерный путь (_run) не трогаем."""
from egrn_parser import geo_nspd_browser as B
from egrn_parser import geo_nspd as N


def _feat(cad, ring):
    return {"type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"options": {"cad_num": cad}}}


PARCEL = [[4205100.0, 5632700.0], [4205250.0, 5632700.0],
          [4205250.0, 5632830.0], [4205100.0, 5632830.0], [4205100.0, 5632700.0]]
OKS = [[4205150.0, 5632740.0], [4205180.0, 5632740.0],
       [4205180.0, 5632770.0], [4205150.0, 5632770.0], [4205150.0, 5632740.0]]


def test_extract_features_unwraps_data():
    payload = {"data": {"features": [_feat("23:15:0000000:2267", PARCEL)]}}
    assert len(B.extract_features(payload)) == 1


def test_extract_features_collection_and_bare():
    f = _feat("23:15:0000000:2267", PARCEL)
    assert len(B.extract_features({"type": "FeatureCollection", "features": [f]})) == 1
    assert len(B.extract_features(f)) == 1


def test_reproject_3857_to_wgs84():
    coords = B._geom_to_coords({"type": "Polygon", "coordinates": [PARCEL]})
    lon, lat = coords[0][0]
    assert 36 < lon < 40 and 44 < lat < 46          # Краснодарский край (23:15)


def test_reproject_passthrough_for_wgs84():
    g = {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.7, 55.7],
                                             [37.7, 55.8], [37.6, 55.7]]]}
    assert B._geom_to_coords(g)[0][0] == [37.6, 55.7]


def test_pick_parcel_exact_cad_wins():
    feats = [_feat("23:15:0000000:9999", OKS), _feat("23:15:0000000:2267", PARCEL)]
    picked = B.pick_parcel_feature(feats, "23:15:0000000:2267")
    assert B._feature_cad(picked) == "23:15:0000000:2267"


def test_feature_cad_from_nested_options():
    assert B._feature_cad(_feat("23:15:0303000:1130", OKS)) == "23:15:0303000:1130"


def test_collect_cads_from_attribute_table():
    # вкладка «ОКС в пределах» — таблица КН без геометрии
    payload = {"data": {"rows": [
        {"cad_num": "23:15:0303000:1130", "area": 5},
        {"options": {"cadastral_number": "23:15:0303000:9999"}}],
        "descr": "смежный 23:15:0000000:2267"}}
    assert B.collect_cads(payload) == {
        "23:15:0303000:1130", "23:15:0303000:9999", "23:15:0000000:2267"}


def test_collect_cads_empty_on_no_cads():
    assert B.collect_cads({"foo": "bar", "n": 42, "list": [1, 2, 3]}) == set()


def test_parcel_ids_from_feature():
    f = {"id": 34382281, "properties": {"category": 36368,
                                        "options": {"cad_num": "23:15:0000000:2267"}}}
    assert B._parcel_ids(f) == (34382281, 36368)


def test_parcel_ids_fallback_keys():
    f = {"properties": {"geomId": 50771174, "categoryId": 36368}}
    assert B._parcel_ids(f) == (50771174, 36368)


def test_parcel_ids_none_on_empty():
    assert B._parcel_ids(None) == (None, None)


def test_buildings_discovered_in_polygon():
    parcel = _feat("23:15:0000000:2267", PARCEL)
    oks = _feat("23:15:0000000:9999", OKS)
    poly = B._geom_to_coords(parcel["geometry"])
    cand = [{"cad": B._feature_cad(oks),
             "geometry": {"type": "Polygon", "coords": B._geom_to_coords(oks["geometry"])}}]
    found = N.features_in_polygon(cand, poly)
    assert [f["name"] for f in found] == ["23:15:0000000:9999"]
