"""
egrn_parser/parsers/agro_link.py — связь агро-слоя с землёй и кадастром
(ADR-006 §E, мост к ADR-005).

- `link_parcel_to_land` — мягкая привязка `agro_parcel` к КН/контуру (может
  отсутствовать/меняться по сезонам).
- `assets_pending_cadastre` — ОКС на счёте 01.08 (`on_cadastre=0`): кандидаты на
  постановку на учёт.
- `register_asset_cadastre` — при оформлении прав: проставить `cad_number` и
  `on_cadastre=1` (после чего ОС линкуется на узел `build_<cad>` в граф-слое).
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional


def link_parcel_to_land(conn: sqlite3.Connection, parcel_code: str, season_year: int,
                        *, land_cad: Optional[str] = None,
                        contour_no: Optional[int] = None) -> bool:
    """Привязать поле сезона к КН/контуру (ADR-006 §E). True — строка обновлена."""
    cur = conn.execute(
        "UPDATE agro_parcel SET land_cad = COALESCE(?, land_cad), "
        "contour_no = COALESCE(?, contour_no) "
        "WHERE parcel_code = ? AND season_year = ?",
        (land_cad, contour_no, parcel_code, season_year))
    conn.commit()
    return cur.rowcount > 0


def assets_pending_cadastre(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """ОКС на 01.08 (`on_cadastre=0`) — кандидаты на постановку на кадастровый учёт."""
    rows = conn.execute(
        "SELECT asset_id, name, account, cost FROM fixed_asset "
        "WHERE on_cadastre = 0 ORDER BY asset_id").fetchall()
    return [{"asset_id": a, "name": n, "account": acc, "cost": c}
            for a, n, acc, c in rows]


def register_asset_cadastre(conn: sqlite3.Connection, asset_id: int,
                            cad_number: str) -> bool:
    """Оформление прав на ОКС: проставить cad_number + on_cadastre=1.

    После этого `graph_edges.asset_of_edges` свяжет ОС с узлом `build_<cad>`."""
    cur = conn.execute(
        "UPDATE fixed_asset SET cad_number = ?, on_cadastre = 1 WHERE asset_id = ?",
        (cad_number, asset_id))
    conn.commit()
    return cur.rowcount > 0
