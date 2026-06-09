# 2026-06-09 — F/G/H: все рёбра графа, связь агро↔земля, единый v_graph_edges

## F. Рёбра граф-слоя (`graph_edges.py`)
Эмиттеры (устойчивы к отсутствию таблиц, узлы по конвенции node-id):
- `located_on_edges` (linked_objects: объект→объект);
- `right_holder_edges` (rights+right_holders → entity);
- `asset_of_edges` (fixed_asset.cad_number → build_<cad>);
- `ownership_edges` (ownership_chain → owns), `relation_edges` (entity_relations);
- `contour_edges` (делегирует land_db.land_graph_edges);
- `all_graph_edges` — единый список.
Хелперы `object_node_id` (land/build/obj по классу) и `entity_node_id`.

## G. Связь агро↔земля/кадастр (`agro_link.py`)
- `link_parcel_to_land` — мягкая привязка agro_parcel → land_cad/contour_no (§E);
- `assets_pending_cadastre` — ОКС 01.08 (`on_cadastre=0`) кандидаты на учёт;
- `register_asset_cadastre` — оформление: cad_number + on_cadastre=1 → появляется
  ребро `asset_of` на `build_<cad>`.

## H. Единый контракт рёбер (`0007_graph_edges_union.sql`)
- Вьюха `v_graph_edges` — UNION ALL по всем источникам (контуры/located_on/
  right_holder/asset_of/owns/relations) с колонкой `edge_type` + `info`.
- Сверено с `all_graph_edges` (тест: одинаковое число рёбер и набор типов).
- Parser-часть H готова; viewer-интеграция — кросс-команда (P2).

## Тесты
- `tests/test_graph_edges_and_agro_link.py` (+10): located_on/right_holder/asset_of/
  owns/director, graceful-без-таблиц, node-id mapping, жизненный цикл ОКС 01.08→КН,
  сверка вьюхи 0007 с эмиттером.
- `pytest tests/test_land_* tests/test_graph_edges_and_agro_link` → **46 passed**.

## Docs
- GRAPH_SCHEMA — рёбра/связь/контракт отмечены ✅; node-id конвенции зафиксированы.
- roadmap — F/G/H закрыты; остаётся A (техкарта, блокер) → E → H(viewer).

## Файлы
- `parser/egrn_parser/parsers/graph_edges.py` (новый)
- `parser/egrn_parser/parsers/agro_link.py` (новый)
- `parser/tests/test_graph_edges_and_agro_link.py` (новый)
- `schema/migrations/0007_graph_edges_union.sql` (новый)
- `docs/specs/GRAPH_SCHEMA_land_and_entities.md`
- `obsidian/Architecture/roadmap-land-agro-graph.md`
