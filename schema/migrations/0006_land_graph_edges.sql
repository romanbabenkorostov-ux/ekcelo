-- =============================================
-- 0006 — Граф-слой: рёбра контуров земли (логические вьюхи)
-- GRAPH_SCHEMA_land_and_entities.md §Рёбра. Граф = логический (вьюхи поверх
-- табличной модели). Узлы: land_<parent>, contour_<parent>_<no>.
-- Тип ребра по contour_cad: заполнен → ezp_child (дочерний КН ЕЗП),
-- NULL → mku_contour (контур МКУ). Программный аналог: land_db.land_graph_edges.
-- =============================================

CREATE VIEW IF NOT EXISTS v_land_graph_edges AS
SELECT
    'land_' || parent_cad                              AS from_node,
    'contour_' || parent_cad || '_' || contour_no      AS to_node,
    CASE WHEN contour_cad IS NOT NULL
         THEN 'ezp_child' ELSE 'mku_contour' END       AS edge_type,
    contour_cad                                        AS to_cad,
    parent_cad,
    contour_no
FROM land_contours;

-- Узлы-контуры (для кросс-матча graph_node_id == node.id в граф-слое).
CREATE VIEW IF NOT EXISTS v_land_graph_nodes AS
SELECT
    'contour_' || parent_cad || '_' || contour_no      AS graph_node_id,
    parent_cad,
    contour_no,
    contour_cad,
    area_sqm,
    centroid_lon,
    centroid_lat,
    CASE WHEN contour_cad IS NOT NULL
         THEN 'ezp_child' ELSE 'mku_contour' END       AS node_kind
FROM land_contours;
