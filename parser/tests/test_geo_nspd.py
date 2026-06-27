"""Тесты парса ПКК-геометрии (офлайн, репроекция 3857→WGS84)."""
import math

from egrn_parser import geo_nspd as N


def _to3857(lon, lat):
    x = lon * 6378137 * math.pi / 180
    y = math.log(math.tan(math.pi / 4 + lat * math.pi / 360)) * 6378137
    return [x, y]


def test_merc_to_wgs_roundtrip():
    x, y = _to3857(38.9, 45.0)
    lon, lat = N._merc_to_wgs(x, y)
    assert abs(lon - 38.9) < 1e-4 and abs(lat - 45.0) < 1e-4


def test_parse_pkk_polygon():
    ring = [_to3857(38.9, 45.0), _to3857(38.92, 45.0), _to3857(38.92, 45.02)]
    g = N.parse_pkk_feature({"feature": {"geometry": {"type": "Polygon", "coordinates": [ring]}}})
    assert g["type"] == "Polygon"
    assert abs(g["coordinates"][0][0][0] - 38.9) < 1e-4


def test_parse_pkk_multipolygon_takes_first():
    r1 = [_to3857(38.9, 45.0), _to3857(38.92, 45.0), _to3857(38.92, 45.02)]
    g = N.parse_pkk_feature({"feature": {"geometry": {"type": "MultiPolygon", "coordinates": [[r1]]}}})
    assert g["type"] == "Polygon" and len(g["coordinates"]) == 1


def test_parse_empty():
    assert N.parse_pkk_feature({}) is None
    assert N.parse_pkk_feature({"feature": {"geometry": {}}}) is None


def test_parse_wfs_features():
    body = {"features": [
        {"geometry": {"type": "Polygon", "coordinates": [[[38.9, 45.0], [38.92, 45.0], [38.92, 45.02]]]},
         "properties": {"cad_num": "23:15:0000000:1"}},
        {"geometry": None, "properties": {}}]}
    feats = N.parse_wfs_features(body)
    assert len(feats) == 1 and feats[0]["cad"] == "23:15:0000000:1"
    assert feats[0]["geometry"]["type"] == "Polygon"


def test_discover_buildings_filters_outside(monkeypatch):
    sq = [[38.9, 45.0], [38.92, 45.0], [38.92, 45.02], [38.9, 45.02]]
    body = {"features": [
        {"geometry": {"type": "Polygon", "coordinates": [[[38.905, 45.005], [38.908, 45.005], [38.908, 45.008]]]},
         "properties": {"cad_num": "IN"}},
        {"geometry": {"type": "Polygon", "coordinates": [[[39.5, 46.0], [39.51, 46.0], [39.51, 46.01]]]},
         "properties": {"cad_num": "OUT"}}]}
    monkeypatch.setattr(N, "_wfs_get", lambda *a, **k: body)
    disc = N.discover_buildings([sq])
    assert [o["name"] for o in disc] == ["IN"]       # OUT (центр вне ЗУ) отфильтрован
