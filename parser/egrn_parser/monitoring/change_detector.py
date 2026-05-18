"""
egrn_parser/monitoring/change_detector.py — сравнение состояния объекта
с предыдущим запуском.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from egrn_parser.db.connection import get_connection
from egrn_parser.merge.differ import diff_objects

log = logging.getLogger(__name__)


def detect_changes(db_path: Path | str, parsed_result: dict) -> dict:
    """
    Сравнить разобранный результат с текущей записью в БД.
    Возвращает {"has_changes": bool, "changed_fields": dict, "action": str}.
    """
    db_path    = Path(db_path)
    cad_number = parsed_result.get("cad_number")
    obj_type   = parsed_result.get("object_type", "building")
    obj_data   = parsed_result.get("object", {})

    if not cad_number:
        return {"has_changes": False, "changed_fields": {}, "action": "skip"}

    table = "land_objects" if obj_type == "land" else "building_objects"

    with get_connection(db_path, readonly=True) as conn:
        existing = conn.execute(
            f"SELECT * FROM {table} WHERE cad_number = ?", (cad_number,)
        ).fetchone()

    if not existing:
        return {"has_changes": True, "changed_fields": {}, "action": "insert"}

    existing_dict = dict(existing)

    # Проверка content_hash
    if existing_dict.get("content_hash") and existing_dict["content_hash"] == obj_data.get("content_hash"):
        return {"has_changes": False, "changed_fields": {}, "action": "skip"}

    changed = diff_objects(existing_dict, obj_data, obj_type)
    return {
        "has_changes":    bool(changed),
        "changed_fields": changed,
        "action":         "replace" if changed else "skip",
    }
