-- =============================================
-- 0009 — Оценочная вьюха виноградника (ADR-006 §J)
-- Собирает ценообразующий профиль насаждения: контур ЗУ (земля) × насаждение
-- (сорт/возраст/площадь/кусты) × уход (agro_event). Урожай/почва/погода —
-- отдельные слои (по мере источников). Зависит от 0005 (агро) и 0004 (land_contours).
-- Программный аналог — agro_reports.vineyard_valuation.
-- =============================================

CREATE VIEW IF NOT EXISTS v_vineyard_valuation AS
SELECT
    p.parcel_id,
    p.parcel_code,
    p.land_cad,                                              -- привязка к контуру ЗУ (ADR-005)
    p.area_ha,
    json_extract(p.attrs, '$.federal_reg_no')        AS federal_reg_no,
    CAST(json_extract(p.attrs, '$.vines_count') AS INTEGER) AS vines_count,
    json_extract(p.attrs, '$.rootstock')             AS rootstock,
    cc.variety,
    CAST(cc.sow_date AS INTEGER)                     AS planting_year,
    (CAST(strftime('%Y', 'now') AS INTEGER) - CAST(cc.sow_date AS INTEGER)) AS vine_age_years,
    lc.contour_area_sqm,                                     -- площадь контуров ЗУ, м²
    lc.centroid_lon, lc.centroid_lat,                       -- геоточка (для погоды/почвы)
    COALESCE(ev.n_operations, 0)                     AS n_care_operations,
    COALESCE(ev.n_treatments, 0)                     AS n_treatments
FROM agro_parcel p
JOIN agro_crop_cycle cc ON cc.parcel_id = p.parcel_id AND cc.crop = 'виноград'
LEFT JOIN (
    SELECT parent_cad,
           SUM(area_sqm)     AS contour_area_sqm,
           AVG(centroid_lon) AS centroid_lon,
           AVG(centroid_lat) AS centroid_lat
    FROM land_contours
    GROUP BY parent_cad
) lc ON lc.parent_cad = p.land_cad
LEFT JOIN (
    SELECT parcel_id,
           SUM(CASE WHEN event_type = 'operation' THEN 1 ELSE 0 END) AS n_operations,
           SUM(CASE WHEN event_type = 'treatment' THEN 1 ELSE 0 END) AS n_treatments
    FROM agro_event
    GROUP BY parcel_id
) ev ON ev.parcel_id = p.parcel_id;
