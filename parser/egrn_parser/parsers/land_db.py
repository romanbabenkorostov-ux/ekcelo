"""
egrn_parser/parsers/land_db.py — запись результата классификации земли
(land_layout) в БД: `land_layout_type` + `land_contours` (ADR-005, миграция 0004).

ЕЗП: дочерние КН → строки land_contours (contour_cad заполнен). МКУ: контуры из
геометрии (contour_cad NULL) — пишутся при наличии геометрии. ЗУ: один контур.
Идемпотентно по UNIQUE(parent_cad, contour_no). Совместимо с БД без land_objects
(тогда пишется только land_contours).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from egrn_parser.parsers import land_layout as _L

_ENSURE_CONTOURS_DDL = """
CREATE TABLE IF NOT EXISTS land_contours (
    contour_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_cad   TEXT NOT NULL,
    contour_no   INTEGER NOT NULL,
    contour_cad  TEXT,
    geom_geojson TEXT,
    area_sqm     REAL,
    centroid_lon REAL,
    centroid_lat REAL,
    geom_source  TEXT,
    source       TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(parent_cad, contour_no)
);
"""


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Создать land_contours; добавить land_objects.land_layout_type при наличии таблицы."""
    conn.executescript(_ENSURE_CONTOURS_DDL)
    if _has_table(conn, "land_objects") and "land_layout_type" not in _columns(conn, "land_objects"):
        conn.execute("ALTER TABLE land_objects ADD COLUMN land_layout_type TEXT")


def set_layout(conn: sqlite3.Connection, cad_number: str, layout: str) -> bool:
    """Проставить land_layout_type в land_objects (если строка есть). True — обновлено."""
    if not _has_table(conn, "land_objects"):
        return False
    cur = conn.execute(
        "UPDATE land_objects SET land_layout_type=? WHERE cad_number=?",
        (layout, cad_number))
    return cur.rowcount > 0


def upsert_contours(conn: sqlite3.Connection, parent_cad: str,
                    contours: list[dict[str, Any]], *, source: Optional[str] = None) -> dict[str, int]:
    """Записать контуры родителя. `contours` — список {contour_cad?, geom_geojson?,
    area_sqm?, geom_source?}; contour_no присваивается по порядку (1..N)."""
    ensure_schema(conn)
    ins = upd = 0
    for i, c in enumerate(contours, 1):
        existed = conn.execute(
            "SELECT 1 FROM land_contours WHERE parent_cad=? AND contour_no=?",
            (parent_cad, i)).fetchone() is not None
        conn.execute(
            """INSERT INTO land_contours
                   (parent_cad, contour_no, contour_cad, geom_geojson, area_sqm,
                    centroid_lon, centroid_lat, geom_source, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(parent_cad, contour_no) DO UPDATE SET
                   contour_cad  = COALESCE(excluded.contour_cad, land_contours.contour_cad),
                   geom_geojson = COALESCE(excluded.geom_geojson, land_contours.geom_geojson),
                   area_sqm     = COALESCE(excluded.area_sqm, land_contours.area_sqm),
                   centroid_lon = COALESCE(excluded.centroid_lon, land_contours.centroid_lon),
                   centroid_lat = COALESCE(excluded.centroid_lat, land_contours.centroid_lat),
                   geom_source  = COALESCE(excluded.geom_source, land_contours.geom_source)""",
            (parent_cad, i, c.get("contour_cad"), c.get("geom_geojson"),
             c.get("area_sqm"), c.get("centroid_lon"), c.get("centroid_lat"),
             c.get("geom_source"), source))
        upd += existed
        ins += not existed
    conn.commit()
    return {"inserted": ins, "updated": upd, "total": len(contours)}


def upsert_land_extract(conn: sqlite3.Connection, result: dict[str, Any], *,
                        source: str = "rosreestr_pdf") -> dict[str, Any]:
    """Записать результат `land_layout.parse_land_extract`: layout + контуры.

    ЕЗП → дочерние КН как контуры (contour_cad). ЗУ/МКУ без геометрии — контуры
    не пишутся (нужна геометрия), только land_layout_type.
    """
    ensure_schema(conn)
    cad = result.get("cad_number")
    layout = result.get("layout")
    out: dict[str, Any] = {"cad_number": cad, "layout": layout,
                           "layout_set": False, "contours": {"inserted": 0, "updated": 0, "total": 0}}
    if not cad:
        return out
    out["layout_set"] = set_layout(conn, cad, layout)
    children = result.get("children") or []
    if children:
        out["contours"] = upsert_contours(
            conn, cad, [{"contour_cad": ch} for ch in children], source=source)
    conn.commit()
    return out


def _current_layout(conn: sqlite3.Connection, cad: str) -> Optional[str]:
    """Текущий land_layout_type объекта (если land_objects есть и строка найдена)."""
    if not _has_table(conn, "land_objects"):
        return None
    row = conn.execute(
        "SELECT land_layout_type FROM land_objects WHERE cad_number=?", (cad,)).fetchone()
    return row[0] if row else None


def upsert_geometry_contours(conn: sqlite3.Connection, parent_cad: str,
                             geom: dict, *, name: Optional[str] = None,
                             layout: Optional[str] = None,
                             source: str = "geometry") -> dict[str, Any]:
    """МКУ/ЗУ: геометрия (MultiPolygon/Polygon) → land_contours (contour_cad=NULL).

    Классифицирует представление (≥2 контуров → МКУ), проставляет land_layout_type
    и пишет контуры по полигонам. Идемпотентно (parent_cad, contour_no).

    ВАЖНО (ADR-005): ЕЗП определяется по дочерним КН/маркеру, НЕ по числу
    полигонов. Геометрия многоконтурного ЕЗП — тоже MultiPolygon, поэтому она
    НЕ должна понижать уже известный ЕЗП до МКУ. Если объект уже помечен ЕЗП
    (или `layout='ЕЗП'` передан явно) — раскладка сохраняется, NULL-cad контуры
    геометрии не создаются (геометрия ЕЗП привязывается к дочерним КН отдельно).
    """
    ensure_schema(conn)
    contours = _L.split_geometry_contours(geom)
    known = layout or _current_layout(conn, parent_cad)
    if known == _L.ЕЗП:
        return {"cad_number": parent_cad, "layout": _L.ЕЗП, "layout_set": False,
                "skipped": "ЕЗП: геометрия не пишется как NULL-cad контуры",
                "contours": {"inserted": 0, "updated": 0, "total": 0}}
    resolved = layout or _L.detect_land_layout(
        cad_number=parent_cad, name=name, contours_count=len(contours) or None)
    out: dict[str, Any] = {"cad_number": parent_cad, "layout": resolved,
                           "layout_set": set_layout(conn, parent_cad, resolved)}
    out["contours"] = upsert_contours(conn, parent_cad, contours, source=source)
    conn.commit()
    return out


def land_graph_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Рёбра граф-слоя из land_contours (GRAPH_SCHEMA §Рёбра).

    Узлы: land_<parent>, contour_<parent>_<no>. Тип ребра — по contour_cad:
    заполнен → 'ezp_child' (дочерний КН ЕЗП), NULL → 'mku_contour' (контур МКУ).
    """
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT parent_cad, contour_no, contour_cad FROM land_contours "
        "ORDER BY parent_cad, contour_no").fetchall()
    edges = []
    for parent_cad, contour_no, contour_cad in rows:
        edges.append({
            "from_node": f"land_{parent_cad}",
            "to_node": f"contour_{parent_cad}_{contour_no}",
            "edge_type": "ezp_child" if contour_cad else "mku_contour",
            "to_cad": contour_cad,
        })
    return edges
