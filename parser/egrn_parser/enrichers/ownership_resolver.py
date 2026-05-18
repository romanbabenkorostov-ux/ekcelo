"""
egrn_parser/enrichers/ownership_resolver.py — определение directOwnerId.

Алгоритм (ТЗ раздел 11.4.6, п. 6):
  directOwnerId = правообладатель с максимальной долей.
  При равенстве долей — лексикографический минимум ИНН.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from egrn_parser.db.connection import get_connection

log = logging.getLogger(__name__)


def resolve_direct_owners(db_path: Path | str) -> dict[str, Optional[str]]:
    """
    Вернуть dict {cad_number: direct_owner_inn} для всех активных объектов
    с зарегистрированными правами.
    """
    db_path = Path(db_path)
    result: dict[str, Optional[str]] = {}

    with get_connection(db_path, readonly=True) as conn:
        rows = conn.execute(
            """
            SELECT r.object_key_value AS cad_number,
                   rh.inn,
                   r.share_numerator,
                   r.share_denominator
            FROM rights r
            JOIN right_holders rh ON rh.right_id = r.right_id
            WHERE r.right_category = 'right'
              AND r.is_active = 1
              AND rh.inn IS NOT NULL
            ORDER BY r.object_key_value, r.share_numerator DESC
            """
        ).fetchall()

    # Группировка по объекту
    by_object: dict[str, list[dict]] = {}
    for row in rows:
        key = row["cad_number"]
        by_object.setdefault(key, []).append(dict(row))

    for cad, holders in by_object.items():
        # Найти максимальную долю
        def share_ratio(h: dict) -> float:
            num = h.get("share_numerator") or 1
            den = h.get("share_denominator") or 1
            return num / den

        max_ratio = max(share_ratio(h) for h in holders)
        top = [h for h in holders if abs(share_ratio(h) - max_ratio) < 1e-9]
        # При равенстве — лексикографический минимум ИНН
        top.sort(key=lambda h: h.get("inn") or "")
        result[cad] = top[0].get("inn") if top else None

    return result
