# PR-предложение: граф-узлы и рёбра для субъектов, земель и контуров

> Для соседнего чата / PR в `contracts/db`. Граф = **логический** (вьюхи поверх
> табличной модели, как graph.html), отдельный движок не вводим (см. Changelog
> 2026-06-04). Ниже — какие УЖЕ существующие/новые таблицы становятся узлами/
> рёбрами графа. Реализация parser-частью сделана; нужен контракт граф-слоя.

## Узлы (nodes)

| Узел | Таблица | id (graph_node_id) |
|---|---|---|
| Субъект (ЮЛ/ИП/ФЛ) | `entity_registry` | `entity_<inn|id>` |
| Группа компаний | `company_groups` | `group_<id>` |
| Земельный участок (ЗУ/ЕЗП/МКУ) | `land_objects` | `land_<cad>` |
| **Контур** (ЕЗП-дочерний / МКУ-контур) | `land_contours` (нов., 0004) | `contour_<parent>_<no>` |
| ОКС/здание | `building_objects` | `build_<cad>` |
| **Основное средство / техника** | `fixed_asset` (нов., 0003) | `asset_<id>` |

## Рёбра (edges)

| Ребро | Таблица | from → to | тип |
|---|---|---|---|
| Владение | `ownership_chain` | parent_entity → child_entity | `owns` (share_pct) |
| Руководитель | `entity_relations` | субъект → ФЛ | `director` (post) |
| Управляющая орг. | `entity_relations` | субъект → ЮЛ | `managing_org` |
| Реорганизация | `entity_relations` | субъект → ЮЛ | `predecessor`/`successor` |
| ЕЗП: дочерний КН | `land_contours` | `land_<parent>` → `contour_<…>` | `ezp_child` (contour_cad заполнен) |
| МКУ: контур | `land_contours` | `land_<parent>` → `contour_<…>` | `mku_contour` (contour_cad NULL) |
| Объекты на участке | `linked_objects` | land → build | `located_on` |
| Право на объект | `rights` → `entity_registry` | land/build → субъект | `right_holder` |
| Техника на объекте | `fixed_asset.cad_number` | asset → build/land | `asset_of` (если ОКС) |

## Что добавить в `contracts/db` (предложение PR)
1. Зафиксировать `graph_node_id`-конвенции для `land_contours` и `fixed_asset`.
2. Описать вьюхи рёбер: `v_graph_edges` UNION ALL по таблицам выше с колонкой
   `edge_type`. Кросс-матч с C1/C4 (`graph_node_id` == `node.id`).
3. Тип ребра `ezp_child` vs `mku_contour` различать по `contour_cad IS NULL`.
4. ОКС на счёте `01.08` (`fixed_asset.on_cadastre=0`) — узел-кандидат «без КН»;
   при постановке на учёт `cad_number` заполняется → перелинковка на `build_<cad>`.

## Уже реализовано parser-частью (готово к графу)
- `entity_registry` + `ownership_chain` + `entity_relations` (ЕГРЮЛ/ЕГРИП ingest).
- `land_contours` + `land_layout_type` (ЕЗП/МКУ, миграция 0004; запись `land_db`).
- **Рёбра/узлы контуров — ✅** (миграция `0006_land_graph_edges.sql`): вьюхи
  `v_land_graph_edges` (`ezp_child`/`mku_contour` по `contour_cad IS NULL`) и
  `v_land_graph_nodes` (`graph_node_id`=`contour_<parent>_<no>` + площадь/центроид).
  Программный аналог — `land_db.land_graph_edges(conn)`.
- **Площадь/центроид контуров — ✅**: считаются из геометрии
  (`land_layout.polygon_area_centroid`, локальная проекция), пишутся в
  `land_contours.area_sqm/centroid_lon/centroid_lat`.
- `fixed_asset` (ОСВ, миграция 0003).
Все записи идемпотентны; источники помечены (`source`).
