"""Единый граф-эмиттер: C2 `relations` → graph.json.

Снимает дубль словарей graph_json v1.1 (Block-2) и v14 (KMZ-ветка): и узлы, и рёбра
выводятся ИЗ табличной модели (entities / relations / relation_types / assertions),
а не из параллельных SQL-запросов по сырым таблицам.

Выход совместим с вьювером (C1 graph_node_id, C4 graphNode/graphEdge):
  nodes[{id,type,level,label,cadNumber,...}], edges[{id,source,target,kind,domain,
  confidence,directed,metadata}], groups[], metadata{}.

Запуск:
    EKCELO_DB_URL=sqlite:///c2.db python -m contracts.db.graph_emit out/graph.json
"""
import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from contracts.db.models import (
    Assertion, AssertionStatus, Entity, EntityKind, Geometry, Relation, RelationType,
)

SCHEMA_VERSION = "graph.json/2.0-c2"

# entity.kind → уровень иерархии для вьювера (по топологии CONTAINS).
_LEVEL = {
    EntityKind.land: 0,
    EntityKind.building: 1, EntityKind.structure: 1, EntityKind.ons: 1, EntityKind.bu: 1,
    EntityKind.room: 2, EntityKind.accessory: 2, EntityKind.equipment: 2,
    EntityKind.device: 2, EntityKind.level: 2,
}
# relation_types.code → kind ребра во вьювере (нижний регистр, совместимо с v1.1).
_EDGE_KIND = {
    "OWNS": "owns", "LEASES": "leases", "CONTAINS": "contains", "CONTROLS": "controls",
    "INSIDE": "contains", "LOCATED_ON": "contains",
    "MORTGAGED_BY": "encumbrance", "ARRESTED_BY": "encumbrance", "RESTRICTED_BY": "restriction",
}


def emit_graph(session: Session) -> dict:
    # entity.id → graph_node_id (для рёбер) + узлы
    ent_rows = session.scalars(select(Entity)).all()
    id_to_gnid = {e.id: e.graph_node_id for e in ent_rows}

    # bbox по entity (если есть геометрия)
    bbox_by_entity: dict = {}
    for g in session.scalars(select(Geometry)).all():
        if g.entity_id is not None and g.bbox and g.entity_id not in bbox_by_entity:
            bbox_by_entity[g.entity_id] = g.bbox

    nodes = []
    for e in ent_rows:
        nodes.append({
            "id": e.graph_node_id,
            "type": e.kind.value,
            "level": _LEVEL.get(e.kind),
            "label": e.label,
            "cadNumber": e.cad_number,
            "refTable": e.ref_table,
            "bbox": bbox_by_entity.get(e.id),
        })

    # активная уверенность по ребру: max(confidence) среди active assertions
    conf_by_rel: dict = {}
    for a in session.scalars(
        select(Assertion).where(Assertion.status == AssertionStatus.active)
    ).all():
        prev = conf_by_rel.get(a.relation_id)
        if prev is None or a.confidence_score > prev:
            conf_by_rel[a.relation_id] = a.confidence_score

    rt_by_id = {rt.id: rt for rt in session.scalars(select(RelationType)).all()}

    edges = []
    for r in session.scalars(select(Relation).where(Relation.superseded_at.is_(None))).all():
        rt = rt_by_id.get(r.relation_type_id)
        code = rt.code if rt else "REL"
        edges.append({
            "id": f"edge:{str(r.id)[:8]}",
            "source": id_to_gnid.get(r.from_entity_id),
            "target": id_to_gnid.get(r.to_entity_id),
            "kind": _EDGE_KIND.get(code, code.lower()),
            "code": code,
            "domain": r.domain.value,
            "confidence": conf_by_rel.get(r.id),
            "directed": True,
            "metadata": r.meta or {},
        })

    by_kind: dict = {}
    for n in nodes:
        by_kind[n["type"]] = by_kind.get(n["type"], 0) + 1

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "nodes": nodes,
        "edges": edges,
        "groups": [],
        "metadata": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "nodesByKind": by_kind,
            "geometryAvailable": session.scalar(select(func.count()).select_from(Geometry)) > 0,
        },
    }


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "graph.json"
    engine = create_engine(os.environ.get("EKCELO_DB_URL", "sqlite:///c2.db"))
    with Session(engine) as s:
        graph = emit_graph(s)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2, default=str)
    print(f"graph.json: {graph['metadata']['nodeCount']} nodes, "
          f"{graph['metadata']['edgeCount']} edges → {out}")


if __name__ == "__main__":
    main()
