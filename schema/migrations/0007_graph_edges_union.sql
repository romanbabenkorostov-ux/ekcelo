-- =============================================
-- 0007 — Единый контракт рёбер граф-слоя (v_graph_edges)
-- GRAPH_SCHEMA §«Что добавить»: UNION ALL по источникам с колонкой edge_type.
-- Зависит от 0006 (v_land_graph_edges). Программный канонический аналог —
-- graph_edges.all_graph_edges (устойчив к отсутствию таблиц; вьюха требует их).
-- Узлы: land_<cad> · contour_<parent>_<no> · build_<cad> · entity_<inn|id> · asset_<id>.
-- Применять к БД с полной схемой parser (linked_objects/rights/right_holders/
-- fixed_asset/ownership_chain/entity_relations/land_contours).
-- =============================================

CREATE VIEW IF NOT EXISTS v_graph_edges AS
-- контуры: ezp_child / mku_contour
SELECT from_node, to_node, edge_type, NULL AS info
FROM v_land_graph_edges

UNION ALL
-- located_on (и пр. link_type): объект → объект
SELECT
    CASE WHEN lower(primary_object_class) LIKE '%участок%' OR lower(primary_object_class) LIKE '%land%'
              OR lower(primary_object_class) LIKE '%zu%' OR lower(primary_object_class) LIKE '%ezp%'
              OR lower(primary_object_class) LIKE '%mku%' OR lower(primary_object_class) LIKE '%землепольз%'
         THEN 'land_' || primary_cad_number
         WHEN lower(primary_object_class) LIKE '%build%' OR lower(primary_object_class) LIKE '%окс%'
              OR lower(primary_object_class) LIKE '%oks%' OR lower(primary_object_class) LIKE '%зда%'
              OR lower(primary_object_class) LIKE '%строен%' OR lower(primary_object_class) LIKE '%помещ%'
              OR lower(primary_object_class) LIKE '%сооруж%'
         THEN 'build_' || primary_cad_number
         ELSE 'obj_' || primary_cad_number END,
    CASE WHEN lower(linked_object_class) LIKE '%участок%' OR lower(linked_object_class) LIKE '%land%'
              OR lower(linked_object_class) LIKE '%zu%' OR lower(linked_object_class) LIKE '%ezp%'
              OR lower(linked_object_class) LIKE '%mku%' OR lower(linked_object_class) LIKE '%землепольз%'
         THEN 'land_' || linked_cad_number
         WHEN lower(linked_object_class) LIKE '%build%' OR lower(linked_object_class) LIKE '%окс%'
              OR lower(linked_object_class) LIKE '%oks%' OR lower(linked_object_class) LIKE '%зда%'
              OR lower(linked_object_class) LIKE '%строен%' OR lower(linked_object_class) LIKE '%помещ%'
              OR lower(linked_object_class) LIKE '%сооруж%'
         THEN 'build_' || linked_cad_number
         ELSE 'obj_' || linked_cad_number END,
    COALESCE(link_type, 'located_on'),
    NULL
FROM linked_objects

UNION ALL
-- right_holder: объект → субъект
SELECT
    CASE WHEN lower(r.object_class) LIKE '%участок%' OR lower(r.object_class) LIKE '%land%'
              OR lower(r.object_class) LIKE '%zu%' OR lower(r.object_class) LIKE '%ezp%'
              OR lower(r.object_class) LIKE '%mku%' OR lower(r.object_class) LIKE '%землепольз%'
         THEN 'land_' || r.object_key_value
         WHEN lower(r.object_class) LIKE '%build%' OR lower(r.object_class) LIKE '%окс%'
              OR lower(r.object_class) LIKE '%oks%' OR lower(r.object_class) LIKE '%зда%'
              OR lower(r.object_class) LIKE '%строен%' OR lower(r.object_class) LIKE '%помещ%'
              OR lower(r.object_class) LIKE '%сооруж%'
         THEN 'build_' || r.object_key_value
         ELSE 'obj_' || r.object_key_value END,
    'entity_' || COALESCE(h.inn, CAST(h.entity_id AS TEXT), h.subject_uuid),
    'right_holder',
    r.right_type
FROM rights r JOIN right_holders h ON h.right_id = r.right_id
WHERE COALESCE(h.inn, CAST(h.entity_id AS TEXT), h.subject_uuid) IS NOT NULL

UNION ALL
-- asset_of: техника → ОКС (build_<cad>)
SELECT 'asset_' || asset_id, 'build_' || cad_number, 'asset_of', account
FROM fixed_asset
WHERE cad_number IS NOT NULL AND cad_number <> ''

UNION ALL
-- owns: parent_entity → child_entity
SELECT
    'entity_' || COALESCE(pc.inn, CAST(oc.parent_entity_id AS TEXT)),
    'entity_' || COALESCE(cc.inn, CAST(oc.child_entity_id AS TEXT)),
    'owns',
    CAST(oc.share_pct AS TEXT)
FROM ownership_chain oc
LEFT JOIN entity_registry pc ON pc.entity_id = oc.parent_entity_id
LEFT JOIN entity_registry cc ON cc.entity_id = oc.child_entity_id
WHERE oc.is_active = 1

UNION ALL
-- director/managing_org/predecessor/successor
SELECT
    'entity_' || COALESCE(se.inn, CAST(er.source_entity_id AS TEXT)),
    'entity_' || COALESCE(te.inn, CAST(er.target_entity_id AS TEXT)),
    er.relation_type,
    er.post
FROM entity_relations er
LEFT JOIN entity_registry se ON se.entity_id = er.source_entity_id
LEFT JOIN entity_registry te ON te.entity_id = er.target_entity_id
WHERE er.is_active = 1;
