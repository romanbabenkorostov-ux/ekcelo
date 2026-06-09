# Параллельные парсеры команды parser (карта модулей)

> Документ-инвентарь: четыре группы модулей, поставленные параллельно с ЭТП-экспортёром (zip `5abdef30-parser4.zip` от 2026-05-30). Локальное расположение у разработчиков: `E:\Code\ekcelo\code\parser\<dir>`.

## TL;DR

| Модуль | Что | Статус | Интеграция с ekcelo |
|---|---|---|---|
| **`egrn_parser`** | Каноническая v1.10 — packaging + docs | в репо `parser/egrn_parser/` | используется напрямую |
| **`parsing_nspd`** | NSPD-парсеры (8 скриптов, парс свидетельств, пометок, merge JSON) | НЕ в репо | dev-стенд, в репо едут только нужные (`01_parsing_nspd_v8.py` уже здесь) |
| **`pirushin_sosn_rocha`** | OS-данные → realty + KMZ контракт + переписка teams | частично в репо (`parser/scripts/`) | используется |
| **`parser_checko_ru`** | Клиент checko.ru + dadata.ru + НПД ФНС, SQLite-кэш | **новый, не в репо** | план: ADR-002, отложенная интеграция в orchestrator |
| **`egrul_egrip_parser`** | Парсер ФНС-XML выписок ЕГРЮЛ (4.08) / ЕГРИП (4.07) → нормализ. запись (субъект+связи) | ✅ **в репо** `parser/egrn_parser/parsers/egrul_egrip_parser.py` | ADR-004, источник §6 legal-слоя; запись в БД ждёт `contracts/db` |

## 0. `egrul_egrip_parser` — ФНС-XML ЕГРЮЛ/ЕГРИП (ADR-004, выполнено 2026-06-05)

Официальный источник данных о субъектах (юрлица/ИП) — параллельно checko/dadata
(ADR-002, отложен) и PDF. Отдельный домен от Росреестр-ЕГРН (`xml_parser.py`).

- **Автоопределение** по корню `Файл`: реестр из `@ТипИнф` (`ЕГРЮЛ_*`/`ЕГРИП_*`),
  версия из `@ВерсФорм`. `SUPPORTED_FORMATS={(ЕГРЮЛ,4.08),(ЕГРИП,4.07)}`,
  неизвестная версия → `ValueError`.
- **XSD по реестрам** (как `xsd/upd`): `parser/schema/xsd/{egrul,egrip}/` —
  оригиналы cp1251 + `NOTES.md`, свежайшая редакция по сортировке имени;
  валидация через lxml (опц.).
- **Нормализованная запись** (одна на `Документ`, единая для всех источников):
  `{subject, directors, managing_orgs, founders, predecessors, successors, source}`.
- **Тесты:** `parser/tests/test_egrul_egrip_parser.py` (9/9) + cp1251-фикстуры
  `parser/tests/fixtures/fns/` (без ПД).
- **Не сделано (по плану):** адаптеры checko/dadata-JSON и PDF → та же запись;
  враппер «запись → БД-слой subjects/relations» (ждёт `contracts/db/SCHEMA_SPEC.md`).

## 1. `egrn_parser` — packaging delta v1.10

В zip три новых файла:
- `egrn_parser/MIGRATION.md` (106L) — миграция со старых `pirushin_sosn_rocha_*` → CLI `egrn-parser`.
- `egrn_parser/README.md` (113L) — каноническая дока v1.10 (PDF / XML / OSV / DOCX / XLSX, граф v1.1).
- `egrn_parser/pyproject.toml` — install через `pip install -e .`, optional `[api]`.

Все `.py` идентичны (CRLF-only). Принять — bring docs+pyproject в репо отдельным PR при следующей синхронизации `parser/egrn_parser/`.

## 2. `parsing_nspd` — NSPD-стенд

В репо уже есть `parser/scripts/01_parsing_nspd_v8.py` (идентичен). Остальные 7 — dev-стенд других итераций:

| Файл | Назначение | В репо? |
|---|---|---|
| `011_merge_nspd_jsons_spasti_apsrsennoe_01.py` | Спасение abandoned JSON'ов после прерванного парсинга | нет |
| `012_extract_related_for_next_batch_kogda_v7_idet_na_krug2.py` | Экстракция связанных КН для следующей пачки | нет |
| `022_parsing_pomech_kadastren_v4.py` | Парсер «пометок кадастра» | нет |
| `02_parsing_svidetelstva_nedvig_2000x.py` | Парсер старых (2000-х) свидетельств о недвижимости | нет |
| `03_enrich_v15.py` | Enricher (репо имеет v17 — НОВЕЕ) | нет |
| `04_nspd_graph_v11.py` | NSPD-граф (репо имеет v14 — НОВЕЕ) | нет |
| `parsing_nspd_gemini_2026-05-12_v4+.py` | Gemini-вариант парсера v22.4 (Playwright) | нет |

**Политика:** скрипты-стенды живут у разработчиков, в `main` приходят только canonical-версии. Не тянем 7 файлов в репо без явного запроса.

## 3. `pirushin_sosn_rocha` — KMZ-контракт и переписка

### Новые скрипты (нет в `parser/scripts/`)

| Файл | Назначение |
|---|---|
| `pirushin_sosn_rocha_01_parsing_OS_to_enrich_realty_v4.py` | OS-данные → enrich realty (фаза до 02) |
| `pirushin_sosn_rocha_02_make_cadastre_folders.py` | Создание папок кадастра |
| `pirushin_sosn_rocha_03_merge_cadastre_file_to_folders_v3.py` | Merge файлов в папки кадастра |
| `pirushin_sosn_rocha_04_compare_path_and_file_cadastr_v2.py` | Сверка путь↔файл кадастра |
| `pirushin_sosn_rocha_05_parse_egrn_folder_to_xlsx_v1.py` | Папка ЕГРН → XLSX |

Это шаги 01-05 golden path до ETP-экспортёра. Большая часть функционала уже мигрирована в `parser/egrn_parser/` (см. `egrn_parser/MIGRATION.md`).

### Markdown-документы

- **`CONTRACT_KMZ_2_11_0.md`** (247L) — ратифицирован PR #1, мерж 2026-05-18. Дуальная мажоритарность parser/viewer. Контрактная поверхность — KMZ-архив (doc.kml + images/ + docs/ + graph.html). Уже есть в репо как `shared/contract-kmz-2.11.0`.
- **`spec_make_format_kmz_2026-05-18_07-30.md`** (518L) — план расширения KML-контракта v2.9.62 → v2.10.0 + рефакторинг `08_build_kmz_v1` → `v2`. Принят как `shared/contract-kmz-2.12.0`.
- **`CORRESPONDENCE_to_parser_team_about_v17_chain.md`** (305L) — письмо parser-team C → B о согласовании 07/08/052 + enrich v17.
- **`REPLY_to_parser_team_A_on_post_011.md`** (89L) — ответ team B на post #011 (canonical wins для `enriched.json`).

Эти MD — часть существующего governance (CONTRACT_KMZ + CORRESPONDENCE). Не требуют новых записей — они уже отражены в соответствующих shared/* ветках.

## 4. `parser_checko_ru` — НОВЫЙ модуль (1.5K+ строк кода)

**Самая значимая часть zip'а.** Полностью отсутствует в `main`.

### Файлы

| Файл | Размер | Назначение |
|---|---|---|
| `parser_checko_ru8.py` | 1945L | Клиент checko.ru API + НПД-статус ФНС (statusnpd.nalog.ru), SQLite-кэш `innogrn.db` |
| `parser_dadata_ru.py` | 500L | Клиент dadata.ru: suggest_party, resolve_licensors, обогащение лицензиаров |
| `schema_innogrn.sql` | 272L | DDL `innogrn.db`: vendors, subjects (с branches via `is_branch`), founders, OKVED, special_regime |
| `schema_nma.sql` | 193L | DDL `nma.db`: trademarks, patents (FIPS), связь через ИНН (TEXT) |
| `INTEGRATION.md` | 1216L | Гайд интеграции в FastAPI + Alembic + Postgres |
| `README.md` | 122L | Quickstart |

### Ключевые возможности (из INTEGRATION.md §1)

- Валидация ИНН/ОГРН/ОГРНИП с контрольными соотношениями.
- Идемпотентная запись `ON CONFLICT DO UPDATE`.
- Стабы аффилированных лиц (`is_fully_parsed=FALSE` — кандидаты для очереди).
- Приоритет типов: `entrepreneur > person` при апгрейде записи.
- Вендорная метка (`id_vendor FK → vendors`) — источник данных всегда известен.
- `special_regime` как строка (`"УСН"`, `"УСН, ПСН"` или `NULL`).
- Multi-vendor pipeline: checko + dadata + место под другие вендоры.

### Сценарий использования в ekcelo

`parser_checko_ru` обогащает данные об организациях по ИНН/ОГРН. В ekcelo это пересекается с:

1. **`entity_registry`** в `parser/egrn_parser/db/schema.sql` — `inn`, `name_full`, `name_short`, `ogrn`, `entity_type`. checko-кэш мог бы быть источником истины для этих полей.
2. **`object_etp_profile.legal_extra`** (`special_restrictions`, `use_type_permitted`) — checko даёт ОКВЭДы, организационно-правовую форму, статус (действует/ликвидирован/в стадии банкротства).
3. **Orchestrator SSOT (`enrich_*.json`)** — план в `orchestrator_spec.md` §6: `EgrnLayer` контейнер `tables: dict[str, Any]`. checko может пополнять `entity_registry` запись перед сборкой SSOT.

См. `Decisions/ADR-002-parser-checko-integration-policy.md` для решения о сроках интеграции.

## Дальнейшие шаги

1. **Принять `egrn_parser` packaging delta** (MIGRATION.md, README.md, pyproject.toml) — отдельным PR при ближайшей синхронизации.
2. **Orchestrator MVP** — учитывает возможность checko-обогащения в `EgrnLayer.tables.entity_registry`, но pull-парсер не вызывает (deferred, см. ADR-002).
3. **NSPD-стенд** оставить у разработчиков; в `main` каноничные `01_parsing_nspd_v8.py` + `03_enrich_v17.py` + `04_nspd_graph_v14.py`.
4. **Pirushin-скрипты 01-05** мигрированы в `parser/egrn_parser/` CLI — отдельные scripts не нужны.
