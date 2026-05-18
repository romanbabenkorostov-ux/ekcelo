"""
egrn_parser/exporters/graph_json.py — экспорт graph.json v1.1 для Block 2.

ТЗ раздел 11.4.
Обратно совместим с v1.0. Новые поля: objectRestrictions, floorsAboveGround,
undergroundFloors, floorsInspection, conditionInspection, metadata.*ModeAvailable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from egrn_parser.db.connection import get_connection
from egrn_parser import __graph_json_version__
from egrn_parser.enrichers.ownership_resolver import resolve_direct_owners

log = logging.getLogger(__name__)


def export_graph_json(
    db_path: Path | str,
    out_path: Path | str,
    run_id: str | None = None,
) -> Path:
    """
    Построить graph.json v1.1 и сохранить в out_path.

    Алгоритм (ТЗ 11.4.6):
    1. Читаем system_meta.graph_json_version
    2. Строим узлы уровней 0/1/2/3
    3. Добавляем holder и right-узлы для режима «Права»
    4. Узлы без родителей → level=-1, группа orphans
    5. directOwnerId через max(share_num/share_den), при равенстве — min(inn)
    6. objectRestrictions[] из JSON-поля объекта
    """
    db_path  = Path(db_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    direct_owners = resolve_direct_owners(db_path)

    nodes: list[dict] = []
    edges: list[dict] = []
    groups: list[dict] = []
    orphan_node_ids: list[str] = []
    edge_counter = 0

    def next_edge_id() -> str:
        nonlocal edge_counter
        edge_counter += 1
        return f"edge_{edge_counter:06d}"

    with get_connection(db_path, readonly=True) as conn:
        # ── Метаданные ────────────────────────────────────────────────────────
        extract_count = conn.execute("SELECT COUNT(*) FROM extracts").fetchone()[0]
        object_count  = (
            conn.execute("SELECT COUNT(*) FROM land_objects").fetchone()[0] +
            conn.execute("SELECT COUNT(*) FROM building_objects").fetchone()[0]
        )
        right_count   = conn.execute("SELECT COUNT(*) FROM rights WHERE is_active=1").fetchone()[0]
        last_date_row = conn.execute(
            "SELECT MAX(extract_date) FROM extracts"
        ).fetchone()
        last_date = last_date_row[0] if last_date_row else None
        has_geom  = conn.execute("SELECT COUNT(*) FROM object_geometries").fetchone()[0] > 0

        # ── Level 0: Земельные участки ────────────────────────────────────────
        land_rows = conn.execute(
            "SELECT * FROM land_objects WHERE lifecycle_status != 'deregistered'"
        ).fetchall()

        land_cad_set: set[str] = set()
        for row in land_rows:
            r = dict(row)
            cad = r["cad_number"]
            land_cad_set.add(cad)
            node_id = f"land:{cad}"

            obj_rest = _parse_json_field(r.get("object_restrictions"))

            node: dict[str, Any] = {
                "id":            node_id,
                "type":          "land",
                "level":         0,
                "label":         f"ЗУ {cad}",
                "shortLabel":    cad.split(":")[-1],
                "cadNumber":     cad,
                "objectClass":   "land",
                "area":          r.get("area"),
                "category":      r.get("land_category"),
                "permittedUse":  _json_to_first(r.get("permitted_uses")),
                "cadastralValue":r.get("cadastral_value"),
                "address":       r.get("address"),
                "geometry":      _build_geometry(conn, cad),
                "objectRestrictions": _build_restrictions(obj_rest),
                "floorsAboveGround":  None,
                "undergroundFloors":  None,
                "floorsInspection":   None,
                "conditionInspection":None,
                "isActive":      r.get("lifecycle_status") == "active",
                "directOwnerId": direct_owners.get(cad),
                "lastExtractDate": _last_extract_date(conn, cad),
                "events":        _build_events(conn, cad),
            }
            nodes.append(node)

        # ── Level 1: ОКС ──────────────────────────────────────────────────────
        bldg_rows = conn.execute(
            "SELECT * FROM building_objects WHERE lifecycle_status != 'deregistered'"
        ).fetchall()

        bldg_node_map: dict[str, str] = {}
        for row in bldg_rows:
            r = dict(row)
            cad = r["cad_number"]
            obj_type = r.get("object_type", "building")
            node_id  = f"{obj_type}:{cad}"
            bldg_node_map[cad] = node_id

            obj_rest = _parse_json_field(r.get("object_restrictions"))

            node = {
                "id":            node_id,
                "type":          obj_type,
                "level":         1,
                "label":         f"{obj_type.upper()} {cad}",
                "shortLabel":    cad.split(":")[-1],
                "cadNumber":     cad,
                "objectClass":   "building",
                "area":          r.get("area"),
                "name":          r.get("name"),
                "purpose":       r.get("purpose"),
                "cadastralValue":r.get("cadastral_value"),
                "address":       r.get("address"),
                "geometry":      _build_geometry(conn, cad),
                "objectRestrictions": _build_restrictions(obj_rest),
                "floorsAboveGround":  r.get("floors_above_ground"),
                "undergroundFloors":  r.get("underground_floors"),
                "floorsInspection":   r.get("floors_inspection"),
                "conditionInspection":r.get("condition_inspection"),
                "isActive":      r.get("lifecycle_status") == "active",
                "directOwnerId": direct_owners.get(cad),
                "lastExtractDate": _last_extract_date(conn, cad),
                "events":        _build_events(conn, cad),
            }
            nodes.append(node)

            # Ребро: ЗУ → ОКС (contains)
            land_cads = _parse_json_field(r.get("land_cad_numbers")) or []
            if isinstance(land_cads, list):
                for land_cad in land_cads:
                    if land_cad in land_cad_set:
                        edges.append({
                            "id":       next_edge_id(),
                            "source":   f"land:{land_cad}",
                            "target":   node_id,
                            "kind":     "contains",
                            "directed": True,
                            "label":    None,
                            "metadata":{"since": None, "until": None},
                        })

            # Ребро: здание → помещение (contains)
            parent = r.get("parent_cad_number")
            if parent and parent in bldg_node_map:
                edges.append({
                    "id":       next_edge_id(),
                    "source":   bldg_node_map[parent],
                    "target":   node_id,
                    "kind":     "contains",
                    "directed": True,
                    "label":    None,
                    "metadata":{"since": None, "until": None},
                })

            # Orphan: нет ЗУ и нет родителя-ОКС
            if not land_cads and not parent:
                node["level"] = -1
                orphan_node_ids.append(node_id)

        # ── Level 2: Принадлежности ───────────────────────────────────────────
        acc_rows = conn.execute(
            "SELECT * FROM accessories WHERE is_disposed = 0"
        ).fetchall()
        for row in acc_rows:
            r = dict(row)
            acc_id   = r["accessory_id"]
            node_id  = f"acc:{acc_id}"
            node = {
                "id":          node_id,
                "type":        "accessory",
                "level":       2,
                "label":       r.get("item_name", f"Принадлежность #{acc_id}"),
                "shortLabel":  str(acc_id),
                "isActive":    True,
                "parentCadNumber": r.get("re_cad_number"),
                "geometry":    {"lat": r.get("lat"), "lon": r.get("lon"), "wkt": None},
            }
            nodes.append(node)

            parent_cad = r.get("re_cad_number")
            if parent_cad:
                parent_node = bldg_node_map.get(parent_cad) or (
                    f"land:{parent_cad}" if parent_cad in land_cad_set else None
                )
                if parent_node:
                    edges.append({
                        "id":       next_edge_id(),
                        "source":   parent_node,
                        "target":   node_id,
                        "kind":     "contains",
                        "directed": True,
                        "label":    None,
                        "metadata":{},
                    })
                else:
                    node["level"] = -1
                    orphan_node_ids.append(node_id)

        # ── Владельцы: holder-узлы и owns-рёбра (режим Права) ────────────────
        rights_rows = conn.execute(
            """
            SELECT r.*, rh.holder_type, rh.name AS holder_name, rh.inn AS holder_inn
            FROM rights r
            LEFT JOIN right_holders rh ON rh.right_id = r.right_id
            WHERE r.is_active = 1 AND r.right_category = 'right'
            """
        ).fetchall()

        holder_node_ids: set[str] = set()
        for row in rights_rows:
            r = dict(row)
            inn = r.get("holder_inn")
            if inn and inn not in holder_node_ids:
                holder_node_ids.add(inn)
                nodes.append({
                    "id":          f"entity:{inn}",
                    "type":        "holder",
                    "level":       None,
                    "label":       r.get("holder_name") or f"ИНН {inn}",
                    "shortLabel":  inn[-4:] if inn else "?",
                    "inn":         inn,
                })

            obj_cad = r.get("object_key_value")
            target_node = bldg_node_map.get(obj_cad) or (
                f"land:{obj_cad}" if obj_cad in land_cad_set else None
            )
            if inn and target_node:
                kind = "leases" if r.get("right_type_code") == "lease" else "owns"
                edges.append({
                    "id":       next_edge_id(),
                    "source":   f"entity:{inn}",
                    "target":   target_node,
                    "kind":     kind,
                    "directed": True,
                    "label":    r.get("right_type"),
                    "metadata":{
                        "rightNumber": r.get("right_number"),
                        "since":       r.get("right_date"),
                        "share":       (f"{r['share_numerator']}/{r['share_denominator']}"
                                        if r.get("share_numerator") else None),
                    },
                })

        # ── Группы компаний ───────────────────────────────────────────────────
        group_rows = conn.execute("SELECT * FROM company_groups").fetchall()
        for row in group_rows:
            r = dict(row)
            members = [
                f"entity:{e['inn']}"
                for e in conn.execute(
                    "SELECT inn FROM entity_registry WHERE group_id = ? AND inn IS NOT NULL",
                    (r["group_id"],)
                ).fetchall()
            ]
            groups.append({
                "id":      f"grp:{r['group_name']}",
                "type":    "company_group",
                "label":   f"Группа «{r['group_name']}»",
                "members": members,
            })

        # ── Цепочки владения ─────────────────────────────────────────────────
        chain_rows = conn.execute(
            "SELECT oc.*, ce.inn AS child_inn, pe.inn AS parent_inn "
            "FROM ownership_chain oc "
            "JOIN entity_registry ce ON ce.entity_id = oc.child_entity_id "
            "JOIN entity_registry pe ON pe.entity_id = oc.parent_entity_id "
            "WHERE oc.is_active = 1"
        ).fetchall()
        for row in chain_rows:
            r = dict(row)
            if r.get("child_inn") and r.get("parent_inn"):
                edges.append({
                    "id":       next_edge_id(),
                    "source":   f"entity:{r['parent_inn']}",
                    "target":   f"entity:{r['child_inn']}",
                    "kind":     "controls",
                    "directed": True,
                    "label":    f"{r.get('share_pct')}%" if r.get("share_pct") else None,
                    "metadata":{"sharePct": r.get("share_pct"), "source": r.get("source")},
                })

        # ── Корневые ЮЛ (внутри with-блока) ─────────────────────────────────
        root_entities_rows = conn.execute(
            "SELECT inn FROM entity_registry WHERE group_id IS NULL AND inn IS NOT NULL"
        ).fetchall()
        root_entities = [row["inn"] for row in root_entities_rows]

    # ── Группа orphans ────────────────────────────────────────────────────────
    if orphan_node_ids:
        groups.append({
            "id":      "orphans",
            "type":    "orphan",
            "label":   "Неподтверждённые объекты",
            "members": orphan_node_ids,
        })

    graph = {
        "schemaVersion":  __graph_json_version__,
        "generatedAt":    datetime.now(timezone.utc).isoformat(),
        "sourceRunId":    run_id,
        "rootEntities":   root_entities,
        "nodes":          nodes,
        "edges":          edges,
        "groups":         groups,
        "metadata": {
            "extractCount":           extract_count,
            "objectCount":            object_count,
            "rightCount":             right_count,
            "lastExtractDate":        last_date,
            "ownershipModeAvailable": bool(rights_rows if 'rights_rows' in dir() else False),
            "rightsModeAvailable":    right_count > 0,
            "geometryAvailable":      has_geom,
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2, default=str)

    log.info(
        "✓ graph.json v%s: %d узлов, %d рёбер, %d групп → %s",
        __graph_json_version__, len(nodes), len(edges), len(groups), out_path.name,
    )
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def _json_to_first(s: Optional[str]) -> Optional[str]:
    obj = _parse_json_field(s)
    if isinstance(obj, list) and obj:
        return obj[0]
    return obj if isinstance(obj, str) else None


def _build_geometry(conn, cad_number: str) -> dict:
    row = conn.execute(
        "SELECT geom_wkt FROM object_geometries WHERE cad_number = ? AND is_current = 1 LIMIT 1",
        (cad_number,),
    ).fetchone()
    geom = {"lat": None, "lon": None, "wkt": None}
    if row and row["geom_wkt"]:
        geom["wkt"] = row["geom_wkt"]
    return geom


def _build_restrictions(rest_list: Any) -> list:
    if not isinstance(rest_list, list):
        return []
    out = []
    for item in rest_list:
        if not isinstance(item, dict):
            continue
        out.append({
            "type":        item.get("type", "other"),
            "typeRu":      _restriction_type_ru(item.get("type", "other")),
            "description": item.get("description"),
            "basisDoc":    item.get("basis_doc"),
        })
    return out


def _restriction_type_ru(code: str) -> str:
    _MAP = {
        "czuit_zone":       "Зона с особыми условиями использования территории",
        "okn_territory":    "Территория объекта культурного наследия",
        "agri_lands":       "Сельскохозяйственные угодья",
        "public_servitude": "Публичный сервитут",
        "other":            "Иное ограничение",
    }
    return _MAP.get(code, code)


def _last_extract_date(conn, cad_number: str) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(extract_date) FROM extracts WHERE cad_number = ?",
        (cad_number,),
    ).fetchone()
    return row[0] if row else None


def _build_events(conn, cad_number: str) -> list:
    rows = conn.execute(
        "SELECT event_type, event_date, notes FROM object_events WHERE cad_number = ? ORDER BY event_seq",
        (cad_number,),
    ).fetchall()
    return [
        {"date": row["event_date"], "type": row["event_type"], "description": row["notes"]}
        for row in rows
    ]
