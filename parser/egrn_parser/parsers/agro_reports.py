"""
egrn_parser/parsers/agro_reports.py — агро-агрегаты (ADR-006 §D).

Вьюхи-отчёты поверх agro_event/agro_crop_cycle/agro_parcel (миграция 0008).
Показатели событий — из JSON `attrs` (json_extract / json_each). Здесь:
`ensure_views` (идемпотентно создаёт вьюхи) + функции-запросы → list[dict].
"""
from __future__ import annotations

import sqlite3
from typing import Any

_VIEWS_DDL = """
CREATE VIEW IF NOT EXISTS v_agro_harvest_by_variety AS
SELECT e.season_year, p.parcel_code,
       COALESCE(json_extract(e.attrs,'$.variety'), cc.variety) AS variety,
       COUNT(*) AS harvest_events,
       SUM(json_extract(e.attrs,'$.volume_kg')) AS volume_kg
FROM agro_event e
JOIN agro_parcel p ON p.parcel_id = e.parcel_id
LEFT JOIN agro_crop_cycle cc ON cc.cycle_id = e.cycle_id
WHERE e.event_type='harvest'
GROUP BY e.season_year, p.parcel_code, variety;

CREATE VIEW IF NOT EXISTS v_agro_harvest_timing AS
SELECT e.event_date, p.parcel_code,
       COALESCE(json_extract(e.attrs,'$.variety'), cc.variety) AS variety,
       json_extract(e.attrs,'$.volume_kg')   AS volume_kg,
       json_extract(e.attrs,'$.acidity_g_l') AS acidity_g_l,
       json_extract(e.attrs,'$.sugar_brix')  AS sugar_brix,
       e.season_year
FROM agro_event e
JOIN agro_parcel p ON p.parcel_id = e.parcel_id
LEFT JOIN agro_crop_cycle cc ON cc.cycle_id = e.cycle_id
WHERE e.event_type='harvest'
ORDER BY e.event_date;

CREATE VIEW IF NOT EXISTS v_agro_pesticide_load AS
SELECT e.season_year, p.parcel_code,
       json_extract(s.value,'$.name') AS active_substance,
       json_extract(s.value,'$.unit') AS unit,
       COUNT(*) AS applications,
       SUM(json_extract(s.value,'$.rate')) AS total_rate
FROM agro_event e
JOIN agro_parcel p ON p.parcel_id = e.parcel_id
JOIN json_each(e.attrs,'$.active_substances') s
WHERE e.event_type='treatment'
GROUP BY e.season_year, p.parcel_code, active_substance, unit;

CREATE VIEW IF NOT EXISTS v_agro_lot_techscheme AS
SELECT p.lot_id, cc.season_year, p.parcel_code, cc.cycle_kind, cc.crop,
       cc.variety, p.area_ha, cc.sow_date, cc.harvest_date, cc.agro_season
FROM agro_crop_cycle cc
JOIN agro_parcel p ON p.parcel_id = cc.parcel_id
WHERE cc.crop_status='fact'
ORDER BY p.lot_id, cc.season_year, p.parcel_code;
"""


_VALUATION_DDL = """
CREATE VIEW IF NOT EXISTS v_vineyard_valuation AS
SELECT p.parcel_id, p.parcel_code, p.land_cad, p.area_ha,
       json_extract(p.attrs,'$.federal_reg_no') AS federal_reg_no,
       CAST(json_extract(p.attrs,'$.vines_count') AS INTEGER) AS vines_count,
       json_extract(p.attrs,'$.rootstock') AS rootstock,
       cc.variety,
       CAST(cc.sow_date AS INTEGER) AS planting_year,
       (CAST(strftime('%Y','now') AS INTEGER) - CAST(cc.sow_date AS INTEGER)) AS vine_age_years,
       lc.contour_area_sqm, lc.centroid_lon, lc.centroid_lat,
       COALESCE(ev.n_operations,0) AS n_care_operations,
       COALESCE(ev.n_treatments,0) AS n_treatments
FROM agro_parcel p
JOIN agro_crop_cycle cc ON cc.parcel_id=p.parcel_id AND cc.crop='виноград'
LEFT JOIN (SELECT parent_cad, SUM(area_sqm) AS contour_area_sqm,
                  AVG(centroid_lon) AS centroid_lon, AVG(centroid_lat) AS centroid_lat
           FROM land_contours GROUP BY parent_cad) lc ON lc.parent_cad=p.land_cad
LEFT JOIN (SELECT parcel_id,
                  SUM(CASE WHEN event_type='operation' THEN 1 ELSE 0 END) AS n_operations,
                  SUM(CASE WHEN event_type='treatment' THEN 1 ELSE 0 END) AS n_treatments
           FROM agro_event GROUP BY parcel_id) ev ON ev.parcel_id=p.parcel_id;
"""


def ensure_views(conn: sqlite3.Connection) -> None:
    """Идемпотентно создать агро-вьюхи (миграция 0008)."""
    conn.executescript(_VIEWS_DDL)


def ensure_valuation_view(conn: sqlite3.Connection) -> None:
    """Идемпотентно создать оценочную вьюху виноградника (миграция 0009).

    Требует таблиц agro_parcel/agro_crop_cycle/agro_event; land_contours создаётся
    при отсутствии (land_db.ensure_schema), чтобы вьюха работала без земли."""
    from egrn_parser.parsers import land_db as _land_db
    _land_db.ensure_schema(conn)
    conn.executescript(_VALUATION_DDL)


def vineyard_valuation(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Оценочный профиль виноградника: контур ЗУ × насаждение × уход (ADR-006 §J)."""
    ensure_valuation_view(conn)
    cur = conn.execute("SELECT * FROM v_vineyard_valuation")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _rows(conn: sqlite3.Connection, view: str) -> list[dict[str, Any]]:
    ensure_views(conn)
    cur = conn.execute(f"SELECT * FROM {view}")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def harvest_by_variety(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Урожай по сортам/сезонам/полям (Σ volume_kg)."""
    return _rows(conn, "v_agro_harvest_by_variety")


def harvest_timing(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Сроки сбора + кислотность/сахар по событиям harvest."""
    return _rows(conn, "v_agro_harvest_timing")


def pesticide_load(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Пестицидная нагрузка: Σ rate по действующему веществу/полю/сезону."""
    return _rows(conn, "v_agro_pesticide_load")


def lot_techscheme(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Техсхема лота: фактические циклы по полям за сезон."""
    return _rows(conn, "v_agro_lot_techscheme")
