-- =============================================
-- 0008 — Агро-агрегаты (вьюхи отчётов), ADR-006 §D
-- Поверх agro_event/agro_crop_cycle/agro_parcel. Показатели событий — из JSON
-- attrs (json_extract / json_each). Группировки управляются agro_attribute_dict.
-- Зависит от 0005 (агро-слой). Программный аналог — agro_reports.py.
-- =============================================

-- Урожай по сортам/сезонам/полям: Σ harvest.volume_kg.
CREATE VIEW IF NOT EXISTS v_agro_harvest_by_variety AS
SELECT
    e.season_year,
    p.parcel_code,
    COALESCE(json_extract(e.attrs, '$.variety'), cc.variety) AS variety,
    COUNT(*)                                          AS harvest_events,
    SUM(json_extract(e.attrs, '$.volume_kg'))         AS volume_kg
FROM agro_event e
JOIN agro_parcel p          ON p.parcel_id = e.parcel_id
LEFT JOIN agro_crop_cycle cc ON cc.cycle_id = e.cycle_id
WHERE e.event_type = 'harvest'
GROUP BY e.season_year, p.parcel_code, variety;

-- Сроки сбора + качество (кислотность/сахар) — по событиям harvest.
CREATE VIEW IF NOT EXISTS v_agro_harvest_timing AS
SELECT
    e.event_date,
    p.parcel_code,
    COALESCE(json_extract(e.attrs, '$.variety'), cc.variety) AS variety,
    json_extract(e.attrs, '$.volume_kg')   AS volume_kg,
    json_extract(e.attrs, '$.acidity_g_l') AS acidity_g_l,
    json_extract(e.attrs, '$.sugar_brix')  AS sugar_brix,
    e.season_year
FROM agro_event e
JOIN agro_parcel p          ON p.parcel_id = e.parcel_id
LEFT JOIN agro_crop_cycle cc ON cc.cycle_id = e.cycle_id
WHERE e.event_type = 'harvest'
ORDER BY e.event_date;

-- Пестицидная нагрузка: разворот active_substances[] → Σ rate по веществу/полю.
CREATE VIEW IF NOT EXISTS v_agro_pesticide_load AS
SELECT
    e.season_year,
    p.parcel_code,
    json_extract(s.value, '$.name') AS active_substance,
    json_extract(s.value, '$.unit') AS unit,
    COUNT(*)                        AS applications,
    SUM(json_extract(s.value, '$.rate')) AS total_rate
FROM agro_event e
JOIN agro_parcel p ON p.parcel_id = e.parcel_id
JOIN json_each(e.attrs, '$.active_substances') s
WHERE e.event_type = 'treatment'
GROUP BY e.season_year, p.parcel_code, active_substance, unit;

-- Техсхема лота: фактические циклы по полям за сезон (что и где растёт).
CREATE VIEW IF NOT EXISTS v_agro_lot_techscheme AS
SELECT
    p.lot_id,
    cc.season_year,
    p.parcel_code,
    cc.cycle_kind,
    cc.crop,
    cc.variety,
    p.area_ha,
    cc.sow_date,
    cc.harvest_date,
    cc.agro_season
FROM agro_crop_cycle cc
JOIN agro_parcel p ON p.parcel_id = cc.parcel_id
WHERE cc.crop_status = 'fact'
ORDER BY p.lot_id, cc.season_year, p.parcel_code;
