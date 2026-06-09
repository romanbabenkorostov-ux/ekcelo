"""
egrn_parser/parsers/graph_edges.py — рёбра логического граф-слоя
(GRAPH_SCHEMA_land_and_entities.md). Граф = вьюхи/эмиттеры поверх табличной
модели, отдельный движок не вводится.

Узлы (graph_node_id):
  land_<cad> · contour_<parent>_<no> · build_<cad> · entity_<inn|id> · asset_<id>

Рёбра (edge_type):
  ezp_child/mku_contour (land_contours)  — см. land_db.land_graph_edges
  located_on            (linked_objects)
  right_holder          (rights + right_holders → entity)
  asset_of              (fixed_asset.cad_number → build)
  owns                  (ownership_chain)
  director/managing_org/predecessor/successor (entity_relations)

Каждый эмиттер устойчив к отсутствию таблицы (вернёт []). `all_graph_edges`
собирает всё в единый список {from_node, to_node, edge_type, ...}.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from egrn_parser.parsers import land_db as _db

# Классы объектов → префикс узла (best-effort; неизвестное → obj_).
_LAND_HINTS = ("land", "zu", "ezp", "mku", "участок", "землепольз")
_BUILD_HINTS = ("build", "oks", "окс", "зда", "строен", "помещ", "сооруж")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


def object_node_id(object_class: str | None, cad: str) -> str:
    """Класс объекта + КН → graph_node_id (land_/build_/obj_)."""
    c = (object_class or "").strip().lower()
    if any(h in c for h in _LAND_HINTS):
        return f"land_{cad}"
    if any(h in c for h in _BUILD_HINTS):
        return f"build_{cad}"
    return f"obj_{cad}"


def entity_node_id(entity_id: Any = None, inn: str | None = None,
                   subject_uuid: str | None = None) -> str | None:
    """Субъект → entity_<inn|id|uuid>. None если ничего нет."""
    if inn:
        return f"entity_{inn}"
    if entity_id is not None:
        return f"entity_{entity_id}"
    if subject_uuid:
        return f"entity_{subject_uuid}"
    return None


def contour_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """ezp_child/mku_contour из land_contours (делегирует land_db)."""
    return _db.land_graph_edges(conn)


def located_on_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """located_on (и пр. link_type) из linked_objects: объект → объект."""
    if not _has_table(conn, "linked_objects"):
        return []
    rows = conn.execute(
        "SELECT primary_object_class, primary_cad_number, linked_object_class, "
        "linked_cad_number, link_type FROM linked_objects "
        "ORDER BY primary_cad_number, linked_cad_number").fetchall()
    return [{"from_node": object_node_id(pc, pcad),
             "to_node": object_node_id(lc, lcad),
             "edge_type": ltype or "located_on"}
            for pc, pcad, lc, lcad, ltype in rows]


def right_holder_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """right_holder: объект (rights) → субъект (right_holders → entity)."""
    if not (_has_table(conn, "rights") and _has_table(conn, "right_holders")):
        return []
    rows = conn.execute(
        "SELECT r.object_class, r.object_key_value, r.right_category, r.right_type, "
        "h.entity_id, h.inn, h.subject_uuid "
        "FROM rights r JOIN right_holders h ON h.right_id = r.right_id "
        "ORDER BY r.right_id, h.holder_id").fetchall()
    edges = []
    for ocls, okey, rcat, rtype, eid, inn, uuid in rows:
        to_node = entity_node_id(eid, inn, uuid)
        if not to_node:
            continue
        edges.append({"from_node": object_node_id(ocls, okey), "to_node": to_node,
                      "edge_type": "right_holder",
                      "right_category": rcat, "right_type": rtype})
    return edges


def asset_of_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """asset_of: техника (fixed_asset) → ОКС (build_<cad>), если cad_number есть."""
    if not _has_table(conn, "fixed_asset"):
        return []
    rows = conn.execute(
        "SELECT asset_id, cad_number FROM fixed_asset "
        "WHERE cad_number IS NOT NULL AND cad_number <> '' ORDER BY asset_id").fetchall()
    return [{"from_node": f"asset_{aid}", "to_node": f"build_{cad}",
             "edge_type": "asset_of"} for aid, cad in rows]


def ownership_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """owns: parent_entity → child_entity (ownership_chain, share_pct)."""
    if not _has_table(conn, "ownership_chain"):
        return []
    rows = conn.execute(
        "SELECT pc.inn, oc.parent_entity_id, cc.inn, oc.child_entity_id, oc.share_pct "
        "FROM ownership_chain oc "
        "LEFT JOIN entity_registry pc ON pc.entity_id = oc.parent_entity_id "
        "LEFT JOIN entity_registry cc ON cc.entity_id = oc.child_entity_id "
        "WHERE oc.is_active = 1 ORDER BY oc.chain_id").fetchall()
    edges = []
    for pinn, pid, cinn, cid, share in rows:
        f, t = entity_node_id(pid, pinn), entity_node_id(cid, cinn)
        if f and t:
            edges.append({"from_node": f, "to_node": t, "edge_type": "owns",
                          "share_pct": share})
    return edges


def relation_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """director/managing_org/predecessor/successor из entity_relations."""
    if not _has_table(conn, "entity_relations"):
        return []
    rows = conn.execute(
        "SELECT se.inn, er.source_entity_id, te.inn, er.target_entity_id, "
        "er.relation_type, er.post FROM entity_relations er "
        "LEFT JOIN entity_registry se ON se.entity_id = er.source_entity_id "
        "LEFT JOIN entity_registry te ON te.entity_id = er.target_entity_id "
        "WHERE er.is_active = 1 ORDER BY er.rel_id").fetchall()
    edges = []
    for sinn, sid, tinn, tid, rtype, post in rows:
        f, t = entity_node_id(sid, sinn), entity_node_id(tid, tinn)
        if f and t:
            edges.append({"from_node": f, "to_node": t,
                          "edge_type": rtype or "related", "post": post})
    return edges


_EMITTERS = (contour_edges, located_on_edges, right_holder_edges,
             asset_of_edges, ownership_edges, relation_edges)


def all_graph_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Единый список рёбер по всем источникам (устойчив к отсутствию таблиц)."""
    edges: list[dict[str, Any]] = []
    for emit in _EMITTERS:
        edges.extend(emit(conn))
    return edges
