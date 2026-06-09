# Roadmap: земля / агро / граф-слой (план остатка)

> Сводный план **не сделанного** по трекам ADR-005 (земля) и ADR-006 (агро).
> Обновляется по мере закрытия пунктов. Дата: 2026-06-09.

## ✅ Сделано (для контекста)
- **Земля (ADR-005):** детектор ЗУ/ЕЗП/МКУ; извлечение ЕЗП из выписки; миграция
  `0004_land_contours`; МКУ-контуры из геометрии (`split_geometry_contours`,
  `upsert_geometry_contours`, ЕЗП не понижается); ingest-мост
  (`land_ingest.py` + CLI `01c_contours_to_db.py`); площадь/центроид контуров
  (`polygon_area_centroid`); рёбра/узлы графа (`0006_land_graph_edges.sql`,
  `land_db.land_graph_edges`).
- **Агро (ADR-006):** `fixed_asset` из ОСВ (`0003`, `osv_assets.py`); миграция
  агро-слоя `0005` (agro_parcel/agro_crop_cycle/agro_event/agro_attribute_dict);
  JSON-профили событий + валидатор (`agro_event_profiles.py`).
- Тесты: `test_land_*` → 36 passed.

## ✅ Сделано (продолжение)
- **F. Все рёбра графа** (`graph_edges.py` + миграция `0007_graph_edges_union.sql`):
  `located_on`, `right_holder`, `asset_of`, `owns`, `director`/…, контуры. Единый
  `v_graph_edges` / `all_graph_edges` (Python-аналог, устойчив к отсутствию таблиц).
- **G. Связь агро↔земля/кадастр** (`agro_link.py`): `link_parcel_to_land`,
  `assets_pending_cadastre` (01.08), `register_asset_cadastre` (→ ребро `asset_of`).
- **H (parser-часть).** Контракт `v_graph_edges` + node-id конвенции готовы.
- Тесты: `test_land_*`, `test_graph_edges_and_agro_link` → 46 passed.

## ⏳ В плане (не сделано)

### P0 — критический путь (заблокирован образцом)
- **A. Парсер техкарты** (`agro_techcard.py`) → `agro_parcel` + `agro_crop_cycle`
  (озимая plan→fact) + `agro_event`.
  - **Блокер:** нужен 1 обезличенный образец техкарты/ОСВ-поля в `fixtures/agro/`.
  - Объём: парсер Excel/таблицы → строки + golden-тест; на ingest событий —
    прогон через `validate_event_attrs` (D готов).

### P1 — после A (нужны данные)
- **E. Вьюхи-агрегаты агро:** урожай по сортам/сезонам/полям (Σ `harvest.volume_kg`);
  пестицидная нагрузка (разворот `active_substances[]` → Σ `rate`); техсхема лота;
  сроки сбора + кислотность/сахар.
- **Wire-валидация событий:** `validate_event_attrs` в ingest техкарты.

### P2 — кросс-команда (граф-слой / просмотрщик)
- **H (viewer-часть).** Интеграция `v_graph_edges` в просмотрщик/`contracts/db`:
  кросс-матч `graph_node_id == node.id`, рендер рёбер. Parser-контракт готов —
  нужен консьюмер на стороне граф-слоя.

## Порядок (рекомендация)
1. **A** — как только появится образец техкарты (критический путь §6, всё прочее
   разблокированное в земле/графе уже закрыто).
2. **E** + wire-валидация — сразу после A.
3. **H (viewer)** — по готовности команды граф-слоя (parser-контракт готов).
