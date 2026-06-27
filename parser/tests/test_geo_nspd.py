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
