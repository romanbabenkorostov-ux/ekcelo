"""Тесты B (рёбра графа), C (площадь/центроид контуров), D (профили agro_event)."""
import sqlite3

from egrn_parser.parsers import land_db as DB
from egrn_parser.parsers import land_layout as L
from egrn_parser.parsers import agro_event_profiles as P

# ~1 км² квадрат у экватора-ish (Краснодар ~45°N): 0.001° ≈ 111 м по широте.
_SQUARE = {"type": "Polygon", "coordinates": [[
    [37.000, 45.000], [37.010, 45.000], [37.010, 45.010], [37.000, 45.010], [37.000, 45.000]]]}
_MULTI = {"type": "MultiPolygon", "coordinates": [
    [[[37.0, 45.0], [37.01, 45.0], [37.01, 45.01], [37.0, 45.0]]],
    [[[37.5, 45.5], [37.51, 45.5], [37.51, 45.51], [37.5, 45.5]]]]}


# ── C: площадь / центроид ────────────────────────────────────────────────────
def test_polygon_area_centroid_square():
    area, lon, lat = L.polygon_area_centroid(_SQUARE["coordinates"])
    # 0.010°×0.010° у 45°N: ~787м (lon, cos45) × ~1105м (lat) ≈ 0.87 млн м²
    assert 800_000 < area < 950_000
    assert abs(lon - 37.005) < 1e-3 and abs(lat - 45.005) < 1e-3


def test_polygon_area_with_hole():
    outer = [[37.0, 45.0], [37.01, 45.0], [37.01, 45.01], [37.0, 45.01], [37.0, 45.0]]
    hole = [[37.004, 45.004], [37.006, 45.004], [37.006, 45.006], [37.004, 45.006], [37.004, 45.004]]
    full, _, _ = L.polygon_area_centroid([outer])
    holed, _, _ = L.polygon_area_centroid([outer, hole])
    assert holed < full                      # дыра уменьшает площадь


def test_split_geometry_contours_enriched():
    contours = L.split_geometry_contours(_MULTI)
    assert len(contours) == 2
    for c in contours:
        assert c["area_sqm"] and c["area_sqm"] > 0
        assert c["centroid_lon"] is not None and c["centroid_lat"] is not None
        assert c["geom_source"] == "geometry"


def test_geometry_contours_area_written_to_db():
    c = sqlite3.connect(":memory:")
    DB.upsert_geometry_contours(c, "23:15:0804000:10", _MULTI)
    rows = c.execute("SELECT area_sqm, centroid_lon, centroid_lat FROM land_contours "
                     "ORDER BY contour_no").fetchall()
    assert len(rows) == 2
    assert all(r[0] and r[0] > 0 and r[1] and r[2] for r in rows)


# ── B: рёбра графа ───────────────────────────────────────────────────────────
def test_land_graph_edges_mku():
    c = sqlite3.connect(":memory:")
    DB.upsert_geometry_contours(c, "23:15:0804000:10", _MULTI)
    edges = DB.land_graph_edges(c)
    assert len(edges) == 2
    assert all(e["edge_type"] == "mku_contour" and e["to_cad"] is None for e in edges)
    assert edges[0]["from_node"] == "land_23:15:0804000:10"
    assert edges[0]["to_node"] == "contour_23:15:0804000:10_1"


def test_land_graph_edges_ezp():
    c = sqlite3.connect(":memory:")
    DB.upsert_land_extract(c, {"cad_number": "23:15:0804000:51", "layout": "ЕЗП",
                               "children": ["23:15:0804000:52", "23:15:0804000:53"]})
    edges = DB.land_graph_edges(c)
    assert len(edges) == 2
    assert all(e["edge_type"] == "ezp_child" for e in edges)
    assert edges[0]["to_cad"] == "23:15:0804000:52"


def test_graph_views_migration():
    c = sqlite3.connect(":memory:")
    DB.upsert_geometry_contours(c, "x", _MULTI)
    c.executescript(open("../schema/migrations/0006_land_graph_edges.sql").read())
    rows = c.execute("SELECT from_node, to_node, edge_type FROM v_land_graph_edges").fetchall()
    assert len(rows) == 2 and rows[0][2] == "mku_contour"
    nodes = c.execute("SELECT graph_node_id, area_sqm FROM v_land_graph_nodes").fetchall()
    assert len(nodes) == 2 and all(n[1] for n in nodes)


# ── D: профили agro_event.attrs ──────────────────────────────────────────────
def test_harvest_valid():
    assert P.validate_event_attrs("harvest",
        {"variety": "Мерло", "volume_kg": 1140, "acidity_g_l": 6.2}) == []


def test_harvest_missing_required():
    errs = P.validate_event_attrs("harvest", {"acidity_g_l": 6.2})
    assert any("variety" in e for e in errs) and any("volume_kg" in e for e in errs)


def test_harvest_wrong_type():
    errs = P.validate_event_attrs("harvest", {"variety": "Мерло", "volume_kg": "много"})
    assert any("volume_kg" in e and "число" in e for e in errs)


def test_treatment_substances():
    ok = P.validate_event_attrs("treatment", {"kind": "опрыскивание",
        "active_substances": [{"name": "глифосат", "rate": 2.5, "unit": "л/га"}]})
    assert ok == []
    bad = P.validate_event_attrs("treatment", {"kind": "x",
        "active_substances": [{"rate": 2.5}]})           # name отсутствует
    assert any("name" in e for e in bad)


def test_unknown_event_type():
    errs = P.validate_event_attrs("teleport", {"x": 1})
    assert errs and "неизвестный тип" in errs[0]


def test_unknown_keys_allowed():
    assert P.validate_event_attrs("sowing",
        {"seeding_rate": 200, "exotic_field": "ok"}) == []


def test_attrs_as_json_string():
    assert P.is_valid_event("harvest", '{"variety":"Мерло","volume_kg":1000}')
    assert not P.is_valid_event("harvest", "{not json")
