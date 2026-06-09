"""
egrn_parser/parsers/land_ingest.py — мост ingest → БД для слоя земли (ADR-005).

Связывает уже готовые куски в реальный поток:
  • sidecar `_data/contours.json` (вывод 01b) → `land_db.upsert_geometry_contours`
    (геометрия NSPD/PKK → land_contours, классификация ЗУ/МКУ по числу полигонов).
  • текст выписки Росреестра → `land_layout.parse_land_extract` →
    `land_db.upsert_land_extract` (ЕЗП: дочерние КН как контуры).

Чистый слой склейки: вся логика — в land_layout/land_db, здесь только обход
входных структур и идемпотентная запись.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from egrn_parser.parsers import land_db as _db
from egrn_parser.parsers import land_layout as _L


def ingest_sidecar_contours(conn: sqlite3.Connection, sidecar: dict, *,
                            source: str = "nspd") -> dict[str, Any]:
    """`_data/contours.json` → land_contours (геометрия → ЗУ/МКУ).

    `sidecar` = {"objects": {cn: payload}}; payload из 01b/v8 несёт `geojson`
    (WGS84) для WFS/PKK-источников. Объекты без geojson (screenshot_cv) —
    пропускаются (геометрии для контуров нет). Известный ЕЗП не понижается
    (см. land_db.upsert_geometry_contours).
    """
    objects = (sidecar or {}).get("objects") or {}
    out: dict[str, Any] = {"written": [], "skipped_no_geom": [], "totals": {
        "objects": len(objects), "written": 0, "contours": 0, "skipped": 0}}
    for cn, payload in objects.items():
        cn_norm = _L.normalize_cad(cn)
        geom = (payload or {}).get("geojson")
        if not isinstance(geom, dict):
            out["skipped_no_geom"].append(cn_norm or cn)
            out["totals"]["skipped"] += 1
            continue
        src = f"{source}:{payload.get('источник', '?')}"
        res = _db.upsert_geometry_contours(conn, cn_norm, geom, source=src)
        out["written"].append({"cad": cn_norm, "layout": res["layout"],
                               "contours": res["contours"]["total"]})
        out["totals"]["written"] += 1
        out["totals"]["contours"] += res["contours"]["total"]
    return out


def ingest_land_extract_text(conn: sqlite3.Connection, text: str, *,
                             source: str = "rosreestr_pdf") -> dict[str, Any]:
    """Текст выписки Росреестра → ЕЗП/ЗУ/МКУ + контуры (дочерние КН для ЕЗП)."""
    result = _L.parse_land_extract(text)
    return _db.upsert_land_extract(conn, result, source=source)
