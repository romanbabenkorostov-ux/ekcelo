# SPEC — Команда parser (локальные парсеры + golden path)

> Консистентность с двумя другими командами — через пакет `contracts/`
> (Consistency Target v1.0). Этот spec — для команды локальных парсеров Win10.
> **Кода в этой итерации не пишем — только дедупликация версий, манифесты и схемы.**

## Роль и контрактная поверхность

Локальные ETL-инструменты (разработчик/тестировщик/экономист) производят
канонический **Bundle** по объекту и лоту. Эмитит: **C1** (KMZ), **C2** (DB §1–§6),
**C3** (Bundle), наполняет §6 для **C5** (Lot).

## Текущее состояние

- golden path 00→13 работает, но размазан по 4 папкам с дублями и дрейфом версий;
- `egrn_parser` — уже пакет (CLI: parse/enrich/merge/export/migrate/folders);
- `parser_checko_ru` — standalone, отложен (ADR-002);
- шов к вьюеру = только KMZ (C1, 2.12.0).

## Целевое состояние

Один канонический golden path с зафиксированными версиями, эмитящий **Bundle vN**
(deterministic, idempotent). Dev-стенды остаются у разработчиков.

## Рабочие треки

### P0
1. **Дедуп и канонизация версий.** Канон: enrich **v17**, nspd_graph **v15**,
   build_kmz **v2_5** (несёт `graph_node_id`/2.11.0), init_project **v4**,
   make_structure **v2_2**. Удалить из main-кандидатов v14/v15-enrich, v11/v14-graph,
   v2_4-kmz. Обновить `obsidian/Architecture/parallel-parsers-map.md`.
2. **Манифест golden path.** `parser/GOLDEN_PATH.md` (надстройка над
   `docs/GOLDEN_PATH_economist_v3.md`): шаги 00→13, для каждого — вход/выход/
   идемпотентность и какие части Bundle наполняет. Промежуточные JSON помечены
   `parser-internal` (вне C1, см. `CONTRACT_KMZ.md` §2).

### P1
3. **egrn_parser как ядро. ✅ (в основном).** packaging-delta готов: `pyproject.toml`
   (`egrn-parser = egrn_parser.cli:main`, v1.10), CLI на 9 команд
   (parse/export/migrate/dict-load/validate/enrich/monitor/serve/folders),
   `MIGRATION.md` (маппинг legacy-скриптов → CLI). Legacy `01_parsing_OS…`/
   `05_parse_egrn_folder…` — **уже отсутствуют** (мигрированы). Остаётся: сверка
   `db/schema.sql` пакета с C2 (§1–§5) при ближайшей синхронизации.
4. **Эмиттер Bundle (главный новый артефакт).** Стадия после 08 собирает каталог
   по `contracts/bundle/BUNDLE_SPEC.md`: `project.kmz` (08), `db.sqlite` (§1–§6),
   `json/{structure,enriched,objects/*}`, `manifest.json` (версии contracts +
   content-хеши + extract_date + состав лота). Опц. `raw/`. Хеши —
   `egrn_parser/merge/content_hash.py`. **Manifest-ядро — ✅** (`bundle_manifest.py`):
   `sha256_file`/`file_entry` + `build_manifest`(C3, allowed-keys) + `validate_manifest`
   (required/semver/sha256/lot-блок). Сборку каталога (kmz/db/json) делает golden-path.
5. **ЭТП-слой §6. ✅** (`etp_merge.py`): единый **gap-fill merge** в
   `object_etp_profile` — приоритет `manual>osv>nspd>exif>llm` (источник ≥ ROW —
   перезаписывает, ниже — заполняет пустоты; глубокий merge по 6 JSON-колонкам,
   идемпотентно). Стратегии `priority`/`gapfill` + `append_keys` (аддитивные списки)
   покрывают семантику nspd/checko/exif/osv. `etp_layer_present` → флаг для manifest
   (ADR-001). Консолидация существующих ETL на эту точку — план
   `obsidian/Architecture/etp-merge-consolidation.md` (рефактор там, где исполнимы
   ETL-тесты: нужен pymorphy3). `lots`/`lot_items` — см. item 6.

### P1+ — приём данных о субъектах (ЕГРЮЛ/ЕГРИП, мультиисточник) — ADR-004
8. **ФНС-XML парсер (✅ сделано 2026-06-05).** `egrn_parser/parsers/egrul_egrip_parser.py`:
   автоопределение реестра/версии (`Файл/@ТипИнф`,`@ВерсФорм`), XSD по реестрам
   (`parser/schema/xsd/{egrul,egrip}/`, версионирование newest-by-sort), lxml-валидация.
   Выход — **нормализованная запись** `{subject, directors, managing_orgs, founders,
   predecessors, successors, source}` (одна на `Документ`).
9. **Адаптеры остальных источников → та же запись (✅ сделано 2026-06-05).**
   `egrul_egrip_pdf.py` (PDF-выписки, проверен на 3 реальных) и
   `egrul_egrip_sources.py` (checko/dadata JSON-мапперы + `fetch_by_inn` по ключу
   из `parser/.env`). Общий `egrul_egrip_normalized.empty_record`/`merge_records`.
   Downstream не знает про источник; приоритет `source` как в §6.
10. **Враппер «запись → БД» ✅ сделано** (`egrul_egrip_db.py`):
    - `subject` → `entity_registry` (idempotent upsert по INN, COALESCE,
      `egrul_status`/`reg_date`/`okved_main`/`kpp`/`egrul_enriched_at`);
    - **учредители → граф `ownership_chain`** (учредитель=parent, субъект=child,
      доля=`share_pct`, idempotent по UNIQUE; авто-создание на свежей БД, мягкий
      skip на корневой схеме без `entity_id`);
    - **директора/управляющие/реорг → `entity_relations`** (✅ сделано: новая
      таблица, `upsert_relations`, отдельно от ownership_chain).
    - CLI `egrul_egrip_pipeline --db`. PDF: единственный акционер + иностранный
      учредитель (страна/иностр.рег.№) — ✅.

### P1++ — земли и агро-слой (proposed)
11. **ЗУ/ЕЗП/МКУ — многоконтурность (ADR-005).** ✅ сделано: детектор
    `land_layout.detect_land_layout`; извлечение ЕЗП из Росреестр-выписки
    (`parse_land_extract`: главный КН + дочерние КН, проверено на реальном ЕЗП
    `23:15:0804000:51`); миграция `0004_land_contours.sql` (`land_layout_type` +
    `land_contours`); запись `land_db.upsert_land_extract` (ЕЗП-дети → контуры).
    **МКУ-контуры из геометрии — ✅**: `split_geometry_contours` (MultiPolygon →
    Polygon/контур, `contour_cad=NULL`) + `land_db.upsert_geometry_contours`
    (классификация ЗУ/МКУ по числу полигонов, идемпотентно). **ЕЗП не понижается
    геометрией** (MultiPolygon ЕЗП ≠ МКУ). **Ingest подключён — ✅**:
    `land_ingest.py` + CLI `01c_contours_to_db.py` (sidecar `_data/contours.json`
    от 01b → `land_contours`; текст выписки → ЕЗП). Сверено с офлайн-ядром
    NSPD-парсера v8 (`_geojson_to_local_meters`). **Рёбра графа — ✅**: вьюхи
    `v_land_graph_edges`/`v_land_graph_nodes` (миграция `0006_land_graph_edges.sql`)
    + `land_db.land_graph_edges` (`ezp_child`/`mku_contour`). **Площадь/центроид
    контуров — ✅** (`polygon_area_centroid`, пишутся в `land_contours`). Дальше:
    граф-рендер в просмотрщике (см. `docs/specs/GRAPH_SCHEMA_land_and_entities.md`).
12. **Агро-слой §6 (ADR-006).** `fixed_asset` из ОСВ (счета 01.x, ОКС 01.08) —
    ✅ (`osv_assets.py`, миграция 0003). **Миграция `0005_agro_layer.sql` — ✅
    написана** (ADR-006 §A/C/H/I): `agro_parcel` (поле-снимок), `agro_crop_cycle`
    (цикл sow→harvest, `season_year`=год уборки, `cycle_kind winter|spring|perennial`,
    план/факт строками `crop_status`+датировка §F), `agro_event` (события+JSON,
    `cycle_id`/`asset_id`), `agro_attribute_dict` (словарь+стартовые 5 строк).
    **JSON-профили `agro_event.attrs` + валидатор — ✅** (`agro_event_profiles.py`:
    harvest/treatment/observation/phenology/sowing/operation; `validate_event_attrs`).
    **Парсер техкарты — ✅ (виноградники)** (`agro_techcard.py`): xlsx-смета →
    `agro_parcel`/`agro_crop_cycle(perennial)`/`agro_event`; листы смета/СЗР/
    плодоносящие; **виноград-гейт** (другие культуры пропускаются, структура
    переиспользуема); СЗР → `treatment.active_substances`; ingest валидирует attrs.
    Проверено на реальном образце (`fixtures/agro/vineyard_techcard_sample.xlsx`:
    54 операции, 12 пестицидов/8 удобрений). **Перечень насаждений (залог) — ✅
    (виноградники)** (`vineyard_perechen.py`): текстовые блоки «Многолетние
    насаждения… Предмет залога N» → `agro_parcel`(фед.реестр/кусты/подвой в attrs,
    `land_cad`=КН ЗУ) + `agro_crop_cycle(perennial, сорт-привой, год высадки)`,
    `source='perechen'`; ценообразующие признаки насаждения привязаны к контуру ЗУ
    (ADR-006 §J). **Агро-агрегаты — ✅**
    (`0008_agro_aggregates.sql` + `agro_reports.py`): урожай по сортам/полям, сроки+
    кислотность/сахар, пест. нагрузка, техсхема лота. **Оценочная вьюха винограда —
    ✅** (`0009_vineyard_valuation.sql` + `agro_reports.vineyard_valuation`): контур
    ЗУ (площадь/центроид) × насаждение (сорт/возраст/кусты) × уход (операции/
    обработки). **Накопленная погода — ✅** (`weather_open_meteo.py`, Open-Meteo
    Archive, без ключа): за день t/осадки/радиация/ветер/порывы → GDD(база 10)/Σ с
    года посадки по геоточке контура (fetch/parse разделены; parse тестируется
    офлайн). **Погода в БД и оценке — ✅** (`0010_weather_accumulated.sql`,
    `weather_open_meteo.store_accumulated`): снимок накопленных условий на насаждение;
    `v_vineyard_valuation` дополнен `accum_gdd`/`accum_precip_mm`/`accum_radiation_mj`
    (последний снимок). Сетевой прогон — позже (наполнит реальными числами).
    Граф-рёбра/связь землёй — §11.

### P2–P3
6. **Lot-сборщик (под C5). ✅** (`lot_assembler.py`): отбор по include/exclude
   (cads/globs/types) + as-of → `lots`/`lot_items` (роль по object_type) +
   `manifest.lot` (детерминированный `members[]`, сортировка по КН, идемпотентно).
7. **checko/nspd (отложено, ADR-002).** Standalone; интеграция — адаптер
   `etl_checko.py` → §6 `legal_extra` (`source='checko'`). В Bundle — только через §6.
   Прим.: ФНС-XML (трек 8, ADR-004) — официальный источник тех же данных без secrets.

## Точки стыковки

| Эмитит | Кому | Через |
|--------|------|-------|
| C1 KMZ | frontend (локаль/GE Pro) | `project.kmz` |
| C2 DB §1–§6 | backend | `db.sqlite` |
| C3 Bundle | backend | каталог + manifest |

## Definition of Done

golden path даёт детерминированный Bundle vN; round-trip export→export
идемпотентен; smoke-тест в `parser/tests/` валидирует `manifest` по
`bundle.schema.json` и сверяет хеши.
