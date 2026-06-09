-- =============================================
-- 0010 — Накопленная погода по геоточке + погода в оценочной вьюхе (ADR-006 §J)
-- weather_accumulated — снимок накопленных условий (GDD/осадки/радиация/ветер) за
-- период по насаждению/геоточке (источник Open-Meteo, weather_open_meteo.py).
-- Пересоздаёт v_vineyard_valuation (0009) с колонками погоды.
-- Зависит от 0005 (агро) и 0009 (оценочная вьюха).
-- =============================================

CREATE TABLE IF NOT EXISTS weather_accumulated (
    weather_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_id     INTEGER,                 -- насаждение (agro_parcel), опц.
    lat           REAL,
    lon           REAL,
    start_date    TEXT,
    end_date      TEXT,
    n_days        INTEGER,
    gdd           REAL,                     -- Σ активных температур (база base_temp)
    precip_mm     REAL,
    radiation_mj  REAL,
    wind_max      REAL,
    gust_max      REAL,
    temp_mean_avg REAL,
    base_temp     REAL DEFAULT 10.0,        -- биологический ноль (виноград = 10°C)
    source        TEXT DEFAULT 'open_meteo',
    fetched_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(parcel_id, start_date, end_date)
);
CREATE INDEX IF NOT EXISTS idx_weather_parcel ON weather_accumulated(parcel_id, end_date);

-- Пересоздать оценочную вьюху с накопленной погодой (последний снимок на насаждение).
DROP VIEW IF EXISTS v_vineyard_valuation;
CREATE VIEW v_vineyard_valuation AS
SELECT
    p.parcel_id, p.parcel_code, p.land_cad, p.area_ha,
    json_extract(p.attrs, '$.federal_reg_no')        AS federal_reg_no,
    CAST(json_extract(p.attrs, '$.vines_count') AS INTEGER) AS vines_count,
    json_extract(p.attrs, '$.rootstock')             AS rootstock,
    cc.variety,
    CAST(cc.sow_date AS INTEGER)                     AS planting_year,
    (CAST(strftime('%Y', 'now') AS INTEGER) - CAST(cc.sow_date AS INTEGER)) AS vine_age_years,
    lc.contour_area_sqm, lc.centroid_lon, lc.centroid_lat,
    COALESCE(ev.n_operations, 0)                     AS n_care_operations,
    COALESCE(ev.n_treatments, 0)                     AS n_treatments,
    w.gdd          AS accum_gdd,
    w.precip_mm    AS accum_precip_mm,
    w.radiation_mj AS accum_radiation_mj,
    w.n_days       AS weather_days
FROM agro_parcel p
JOIN agro_crop_cycle cc ON cc.parcel_id = p.parcel_id AND cc.crop = 'виноград'
LEFT JOIN (
    SELECT parent_cad, SUM(area_sqm) AS contour_area_sqm,
           AVG(centroid_lon) AS centroid_lon, AVG(centroid_lat) AS centroid_lat
    FROM land_contours GROUP BY parent_cad
) lc ON lc.parent_cad = p.land_cad
LEFT JOIN (
    SELECT parcel_id,
           SUM(CASE WHEN event_type = 'operation' THEN 1 ELSE 0 END) AS n_operations,
           SUM(CASE WHEN event_type = 'treatment' THEN 1 ELSE 0 END) AS n_treatments
    FROM agro_event GROUP BY parcel_id
) ev ON ev.parcel_id = p.parcel_id
LEFT JOIN (
    SELECT parcel_id, gdd, precip_mm, radiation_mj, n_days,
           ROW_NUMBER() OVER (PARTITION BY parcel_id ORDER BY end_date DESC) AS rn
    FROM weather_accumulated WHERE parcel_id IS NOT NULL
) w ON w.parcel_id = p.parcel_id AND w.rn = 1;
