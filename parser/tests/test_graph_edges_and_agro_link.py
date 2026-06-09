"""Тесты F (рёбра графа), G (связь агро↔земля/кадастр), H (единый v_graph_edges)."""
import sqlite3

from egrn_parser.parsers import graph_edges as G
from egrn_parser.parsers import agro_link as AL
from egrn_parser.parsers import land_db as DB

_MULTI = {"type": "MultiPolygon", "coordinates": [
    [[[37.0, 45.0], [37.01, 45.0], [37.01, 45.01], [37.0, 45.0]]],
    [[[37.5, 45.5], [37.51, 45.5], [37.51, 45.51], [37.5, 45.5]]]]}


def _full_graph_db():
    """БД с минимальными таблицами-источниками рёбер + примерами."""
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE linked_objects(link_id INTEGER PRIMARY KEY, primary_cad_number TEXT,
        primary_object_class TEXT, linked_cad_number TEXT, linked_object_class TEXT, link_type TEXT);
    CREATE TABLE entity_registry(entity_id INTEGER PRIMARY KEY, inn TEXT);
    CREATE TABLE rights(right_id INTEGER PRIMARY KEY, object_class TEXT,
        object_key_type TEXT, object_key_value TEXT, right_category TEXT, right_type TEXT);
    CREATE TABLE right_holders(holder_id INTEGER PRIMARY KEY, right_id INTEGER,
        holder_type TEXT, name TEXT, inn TEXT, entity_id INTEGER, subject_uuid TEXT);
    CREATE TABLE fixed_asset(asset_id INTEGER PRIMARY KEY, name TEXT, account TEXT,
        cost REAL, on_cadastre INTEGER DEFAULT 1, cad_number TEXT);
    CREATE TABLE ownership_chain(chain_id INTEGER PRIMARY KEY, child_entity_id INTEGER,
        parent_entity_id INTEGER, share_pct REAL, is_active INTEGER DEFAULT 1);
    CREATE TABLE entity_relations(rel_id INTEGER PRIMARY KEY, source_entity_id INTEGER,
        target_entity_id INTEGER, relation_type TEXT, post TEXT, is_active INTEGER DEFAULT 1);
    """)
    DB.upsert_geometry_contours(c, "23:15:0804000:10", _MULTI)          # 2 mku_contour
    c.execute("INSERT INTO linked_objects VALUES(1,'23:15:0804000:10','land','23:15:0804000:99','building','located_on')")
    c.executemany("INSERT INTO entity_registry VALUES(?,?)", [(1, "7700000001"), (2, "7700000002")])
    c.execute("INSERT INTO rights VALUES(1,'building','cad_number','23:15:0804000:99','right','собственность')")
    c.execute("INSERT INTO right_holders VALUES(1,1,'legal','ООО Ромашка','7700000002',2,NULL)")
    c.execute("INSERT INTO fixed_asset VALUES(1,'Насос','01.01',100,1,'23:15:0804000:99')")
    c.execute("INSERT INTO fixed_asset VALUES(2,'ОКС-склад','01.08',500,0,NULL)")   # 01.08 без КН
    c.execute("INSERT INTO ownership_chain VALUES(1,2,1,75.0,1)")        # entity1 owns entity2
    c.execute("INSERT INTO entity_relations VALUES(1,2,1,'director','Директор',1)")
    c.commit()
    return c


# ── F: рёбра ─────────────────────────────────────────────────────────────────
def test_located_on_edge():
    c = _full_graph_db()
    e = G.located_on_edges(c)
    assert e == [{"from_node": "land_23:15:0804000:10",
                  "to_node": "build_23:15:0804000:99", "edge_type": "located_on"}]


def test_right_holder_edge():
    c = _full_graph_db()
    e = G.right_holder_edges(c)
    assert len(e) == 1
    assert e[0]["from_node"] == "build_23:15:0804000:99"
    assert e[0]["to_node"] == "entity_7700000002"
    assert e[0]["edge_type"] == "right_holder"


def test_asset_of_edge_only_with_cad():
    c = _full_graph_db()
    e = G.asset_of_edges(c)
    assert e == [{"from_node": "asset_1", "to_node": "build_23:15:0804000:99",
                  "edge_type": "asset_of"}]              # ОКС 01.08 без КН — нет ребра


def test_ownership_and_relation_edges():
    c = _full_graph_db()
    owns = G.ownership_edges(c)
    assert owns[0]["from_node"] == "entity_7700000001" and owns[0]["edge_type"] == "owns"
    rel = G.relation_edges(c)
    assert rel[0]["edge_type"] == "director"


def test_all_graph_edges_count():
    c = _full_graph_db()
    e = G.all_graph_edges(c)
    types = sorted({x["edge_type"] for x in e})
    assert "mku_contour" in types and "located_on" in types
    assert "right_holder" in types and "asset_of" in types
    assert "owns" in types and "director" in types
    # 2 contour + 1 located + 1 right + 1 asset + 1 owns + 1 director = 7
    assert len(e) == 7


def test_emitters_graceful_without_tables():
    c = sqlite3.connect(":memory:")
    assert G.all_graph_edges(c) == []                    # нет таблиц → пусто


def test_object_node_id_mapping():
    assert G.object_node_id("land", "1:1:1:1") == "land_1:1:1:1"
    assert G.object_node_id("ОКС здание", "1:1:1:2") == "build_1:1:1:2"
    assert G.object_node_id("xz", "1:1:1:3") == "obj_1:1:1:3"


# ── G: связь агро↔земля + кадастр ────────────────────────────────────────────
def _agro_db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE agro_parcel(parcel_id INTEGER PRIMARY KEY, parcel_code TEXT,
        season_year INTEGER, land_cad TEXT, contour_no INTEGER);
    CREATE TABLE fixed_asset(asset_id INTEGER PRIMARY KEY, name TEXT, account TEXT,
        cost REAL, on_cadastre INTEGER DEFAULT 1, cad_number TEXT);
    """)
    c.execute("INSERT INTO agro_parcel VALUES(1,'уч.519',2025,NULL,NULL)")
    c.execute("INSERT INTO fixed_asset VALUES(1,'ОКС-склад','01.08',500,0,NULL)")
    c.commit()
    return c


def test_link_parcel_to_land():
    c = _agro_db()
    assert AL.link_parcel_to_land(c, "уч.519", 2025, land_cad="23:15:0804000:10", contour_no=1)
    row = c.execute("SELECT land_cad, contour_no FROM agro_parcel").fetchone()
    assert row == ("23:15:0804000:10", 1)
    assert not AL.link_parcel_to_land(c, "уч.999", 2025, land_cad="x")   # нет строки


def test_asset_cadastre_lifecycle():
    c = _agro_db()
    pending = AL.assets_pending_cadastre(c)
    assert len(pending) == 1 and pending[0]["account"] == "01.08"
    assert AL.register_asset_cadastre(c, 1, "23:15:0804000:77")
    row = c.execute("SELECT cad_number, on_cadastre FROM fixed_asset WHERE asset_id=1").fetchone()
    assert row == ("23:15:0804000:77", 1)
    assert AL.assets_pending_cadastre(c) == []           # больше не кандидат
    # теперь у ОС есть КН → появляется ребро asset_of
    assert G.asset_of_edges(c)[0]["to_node"] == "build_23:15:0804000:77"


# ── H: единый v_graph_edges (миграция 0007) ──────────────────────────────────
def test_v_graph_edges_view_matches_emitter():
    c = _full_graph_db()
    c.executescript(open("../schema/migrations/0006_land_graph_edges.sql").read())
    c.executescript(open("../schema/migrations/0007_graph_edges_union.sql").read())
    view_rows = c.execute("SELECT from_node, to_node, edge_type FROM v_graph_edges").fetchall()
    assert len(view_rows) == len(G.all_graph_edges(c)) == 7
    types = sorted({r[2] for r in view_rows})
    assert types == ["asset_of", "director", "located_on", "mku_contour", "owns", "right_holder"]
