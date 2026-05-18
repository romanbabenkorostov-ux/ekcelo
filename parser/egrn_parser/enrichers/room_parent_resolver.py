"""
egrn_parser/enrichers/room_parent_resolver.py — алгоритм resolve_room_parent().

ТЗ раздел 7.5: подтянуть этажность родительского здания к записи помещения.

Алгоритм:
1. Для каждого помещения в building_objects WHERE object_type IN ('room','parking')
   и WHERE parent_cad_number IS NOT NULL:
   a. Найти запись родителя в building_objects (WHERE cad_number = parent_cad_number).
   b. Если найдена — скопировать floors_above_ground и underground_floors
      в parent_floors_above_ground и parent_underground_floors помещения.
   c. Если родитель не найден в building_objects — искать в land_objects.
   d. Установить parent_object_class соответственно.
"""

from __future__ import annotations

import logging
from pathlib import Path

from egrn_parser.db.connection import get_connection

log = logging.getLogger(__name__)


def resolve_room_parent(db_path: Path | str) -> int:
    """
    Обновить parent_floors_above_ground / parent_underground_floors
    для всех помещений и машино-мест в базе данных.

    Возвращает количество обновлённых записей.
    """
    db_path = Path(db_path)
    updated = 0

    with get_connection(db_path) as conn:
        # Получить все помещения/ММ с указанным parent_cad_number
        rooms = conn.execute(
            """
            SELECT cad_number, parent_cad_number
            FROM building_objects
            WHERE object_type IN ('room', 'parking')
              AND parent_cad_number IS NOT NULL
              AND (parent_floors_above_ground IS NULL OR parent_underground_floors IS NULL)
            """
        ).fetchall()

        for room in rooms:
            room_cad    = room["cad_number"]
            parent_cad  = room["parent_cad_number"]

            # Ищем родителя среди зданий
            parent = conn.execute(
                """
                SELECT floors_above_ground, underground_floors, object_type
                FROM building_objects
                WHERE cad_number = ?
                """,
                (parent_cad,),
            ).fetchone()

            if parent:
                parent_class = "building"
                floors_ag    = parent["floors_above_ground"]
                underground  = parent["underground_floors"]
            else:
                # Родитель — земельный участок? (маловероятно, но проверяем)
                land = conn.execute(
                    "SELECT cad_number FROM land_objects WHERE cad_number = ?",
                    (parent_cad,),
                ).fetchone()
                if land:
                    parent_class = "land"
                    floors_ag    = None
                    underground  = None
                else:
                    parent_class = "unknown"
                    floors_ag    = None
                    underground  = None

            conn.execute(
                """
                UPDATE building_objects
                SET parent_floors_above_ground = ?,
                    parent_underground_floors   = ?,
                    parent_object_class         = ?,
                    updated_at                  = datetime('now')
                WHERE cad_number = ?
                """,
                (floors_ag, underground, parent_class, room_cad),
            )
            changes = conn.execute("SELECT changes()").fetchone()[0]
            updated += changes

    log.info("resolve_room_parent: обновлено %d помещений", updated)
    return updated
