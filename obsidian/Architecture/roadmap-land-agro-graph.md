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
- **E. Агро-агрегаты** (`0008_agro_aggregates.sql` + `agro_reports.py`): вьюхи
  урожай по сортам/полям, сроки+кислотность/сахар, пестицидная нагрузка, техсхема
  лота. Код/вьюхи готовы и протестированы на синтетике (нужны реальные данные A).
- Тесты: `test_land_*`, `test_graph_edges_and_agro_link`, `test_agro_reports` → 52 passed.

- **A. Парсер техкарты виноградника — ✅** (`agro_techcard.py`): xlsx-смета →
  `agro_parcel`/`agro_crop_cycle(perennial)`/`agro_event`; **виноград-гейт** (другие
  культуры пропускаются, структура переиспользуема); СЗР → `treatment.active_substances`;
  ingest с профиль-валидацией. Образец `fixtures/agro/vineyard_techcard_sample.xlsx`
  (54 операции, 12 пестицидов/8 удобрений). Профиль `operation` добавлен в D.
- **J. Перечень виноградных насаждений (залог) — ✅** (`vineyard_perechen.py`):
  текст «Многолетние насаждения… Предмет залога N» → `agro_parcel`(фед.реестр/кусты/
  подвой в attrs, `land_cad`=КН ЗУ) + `agro_crop_cycle(perennial, сорт, год высадки)`;
  `source='perechen'` (миграция 0005). Ценообразующие признаки насаждения привязаны
  к контуру ЗУ (ADR-006 §J). Образец `fixtures/agro/vineyard_perechen_sample.txt`.
- **Оценочная вьюха винограда — ✅** (`0009_vineyard_valuation.sql` +
  `agro_reports.vineyard_valuation`): контур ЗУ (площадь/центроид) × насаждение
  (сорт/возраст/кусты/фед.реестр) × уход (операции/обработки).
- **Накопленная погода — ✅** (`weather_open_meteo.py`, Open-Meteo Archive, без
  ключа): за день t/осадки/радиация/ветер/порывы → GDD(база 10)/Σ с года посадки по
  геоточке контура. fetch/parse разделены; parse+accumulate тестируются офлайн.
- **Погода в БД + в оценке — ✅** (`0010_weather_accumulated.sql`,
  `store_accumulated`): снимок на насаждение; `v_vineyard_valuation` дополнен
  `accum_gdd`/`accum_precip_mm`/`accum_radiation_mj`. Пайп готов офлайн.
- Тесты: всё агро+земля+погода → **72 passed**.

## ⏳ В плане (не сделано — внешние зависимости)

- **Урожай по сборам** (нет карт): harvest variety/volume_kg/acidity → наполнят
  `v_agro_harvest_*` и достроят оценку «качество/количество».
- **Сетевой прогон погоды** (доступ позже): `accumulated_since_planting` →
  `store_accumulated` наполнит `weather_accumulated` реальными числами; вьюха уже готова.
- **Почва/агротех-нормы** (нет источника): тип почвы/характеристики — нужны
  NSPD/почвенные карты.
- **H (viewer)**: интеграция `v_graph_edges`/`v_vineyard_valuation` в просмотрщик
  (кросс-команда; parser-контракт готов).
- **Другие культуры:** структура парсера переиспользуема (виноград-гейт снимается
  точечно под нужную культуру), но работы специфичны — по запросу.

### P2 — кросс-команда (граф-слой / просмотрщик)
- **H (viewer-часть).** Интеграция `v_graph_edges` в просмотрщик/`contracts/db`:
  кросс-матч `graph_node_id == node.id`, рендер рёбер. Parser-контракт готов —
  нужен консьюмер на стороне граф-слоя.

## Порядок (рекомендация)
Весь parser-слой (земля/граф/агро + парсер техкарты винограда) закрыт. Осталось:
1. **Карты со сборами** (harvest по сортам) — наполнят агро-агрегаты урожая;
   текущий образец — смета закладки/ухода (план).
2. **H (viewer)** — по готовности команды граф-слоя (parser-контракт готов).
3. **Другие культуры** — по запросу (структура парсера переиспользуема).
