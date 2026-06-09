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
3. **egrn_parser как ядро.** Принять packaging-delta (`MIGRATION.md`/`README.md`/
   `pyproject.toml`); legacy `01_parsing_OS…`, `05_parse_egrn_folder…` →
   депрекейт в пользу CLI `egrn-parser`. Сверить `db/schema.sql` пакета с **C2** (§1–§5).
4. **Эмиттер Bundle (главный новый артефакт).** Стадия после 08 собирает каталог
   по `contracts/bundle/BUNDLE_SPEC.md`: `project.kmz` (08), `db.sqlite` (§1–§6),
   `json/{structure,enriched,objects/*}`, `manifest.json` (версии contracts +
   content-хеши + extract_date + состав лота). Опц. `raw/`. Хеши —
   `egrn_parser/merge/content_hash.py`.
5. **ЭТП-слой §6.** `object_etp_profile`/`lots`/`lot_items` с `source`+`confidence`;
   gap-fill merge (osv/manual > nspd/exif/llm/checko). §6 при пересоздании БД не
   восстанавливается (ADR-001) → в manifest помечается отдельно.

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
11. **ЗУ/ЕЗП/МКУ — многоконтурность (ADR-005, proposed).** Детектор
    `land_layout.detect_land_layout` (ЗУ/ЕЗП/МКУ по маркеру/дочерним КН/числу
    контуров) — ✅ сделано. Дальше: `land_layout_type` в land_objects,
    `land_contours`, связи `linked_objects` (`ezp_child`/`mku_contour`/`reorg_*`).
12. **Агро-слой §6 (ADR-006, proposed).** `fixed_asset` из ОСВ (счета 01.x, ОКС
    01.08) — ✅ сделано (`osv_assets.py`, миграция 0003). `agro_parcel`/`agro_event`
    (события+JSON, датирование F, словарь H) — спроектировано; парсер техкарты —
    **заглушка** `agro_techcard.py` + ТЗ `fixtures/agro/TZ_techcard.md` (ждёт образец).
    Агрегаты: урожай по сортам/датам/полям, пест. нагрузка, техсхема лота.

### P2–P3
6. **Lot-сборщик (под C5).** Отбор по include/exclude + as-of → `lots`/`lot_items`
   + `manifest.lot` (детерминированный `members[]`).
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
