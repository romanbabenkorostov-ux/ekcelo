# ADR-007: Экспорт внутренней БД парсера → C2 (контракт обмена)

**Статус:** Accepted · **Дата:** 2026-06-09 · **Решение заказчика:** C2 — главный
формат для бэкенда; роль бэкенд-команды и согласование правил перевода поручены
parser-стороне (с пояснениями здесь); добро на слой экспорта дано.
**Связанные:** ADR-001 (БД = слепок ЕГРН + ЭТП), `schema-pkg-vs-c2-drift.md`.

## Контекст
Две схемы (см. ревизию `Architecture/schema-pkg-vs-c2-drift.md`):
- **pkg** (`parser/egrn_parser/db/schema.sql`, 24 табл.) — внутренняя рабочая БД CLI:
  богатая модель (building_objects/land_objects раздельно, детальные rights и т.д.).
- **C2** (`schema/egrn_current_schema.sql`, 8 табл.) — компактный **контракт обмена**
  с бэкендом/вьюером.

Bundle (C3) обязан содержать `db.sqlite` в **C2-формате**. Прямое слияние схем
отклонено (риск для контракта). Решение — **слой экспорта** pkg → C2.

## Решение
`egrn_parser/schema_export.export_to_c2(src, out)` создаёт чистую C2-БД и переносит
§1–§5 по правилам перевода ниже; §6 (ЭТП) копирует как есть (C2-нативный). Устойчив
к отсутствию исходных таблиц/колонок. CLI: `egrn-parser export-c2 --db --out` и флаг
`egrn-parser bundle --export-c2` (пакует C2-БД).

## Правила перевода (как меняются таблицы) — «контракт бэкенда»

### §1 `objects` ← `building_objects` ∪ `land_objects`
Две раздельные таблицы pkg сводятся в единую `objects` контракта.
| C2.objects | ← pkg |
|---|---|
| cad_number | cad_number |
| object_type | building_objects.object_type / 'land' для land_objects |
| address | address |
| area | area |
| category | land_objects.land_category (для зданий — NULL) |
| permitted_use | permitted_uses |
| purpose | building_objects.purpose (для земли — NULL) |
| floors | building_objects.floors_above_ground (иначе floors_total) |

### §2 `entity_registry` (PK = `inn`)
pkg.entity_registry (PK entity_id) → C2 (PK inn). **Строки без ИНН пропускаются**
(в C2 ключ — ИНН). name_full обязателен → берётся name_full|name_short|'н/д'.
Поля entity_id/graph_node_id/egrul_*/kpp/legal_address и т.п. в C2 не переносятся
(остаются во внутренней БД).

### §3 `rights` ← `rights[right_category='right']` (+ `right_holders.inn`)
| C2.rights | ← pkg |
|---|---|
| cad_number | rights.object_key_value (object_key_type='cad_number') |
| right_type | rights.right_type (иначе right_category) |
| right_holder_inn | right_holders.inn (первый по holder_id) |
| share_numerator/denominator | те же |
| registration_number | rights.right_number |
| registration_date | rights.right_date |
| source_extract_id | NULL (в pkg — текстовый source_extract_number) |

### §5 `object_restrictions` ← `rights[right_category∈{encumbrance,restriction}]`
Обременения/ограничения из богатой pkg.rights выносятся в отдельную C2-таблицу:
| C2.object_restrictions | ← pkg.rights |
|---|---|
| cad_number | object_key_value |
| restrict_type | right_type |
| description | right_type / right_type_code |
| registry_number | right_number |
| valid_from | valid_from / right_date |
| valid_to | valid_until / right_end_date |
| basis_doc | basis |

### §4 `extracts`
| C2.extracts | ← pkg.extracts |
|---|---|
| extract_number | extract_number |
| cad_number | cad_number |
| extract_date | extract_date |
| document_type | extract_template / object_class |
| raw_json | NULL (pkg хранит content_hash, не сырой JSON) |
| parser_version | schema_id |

### §6 `object_etp_profile` / `lots` / `lot_items`
Копируются **как есть** — это C2-нативные таблицы (их пишут etp_merge/lot_assembler).

## Потери/допущения (явно)
- Внутренние расширения pkg (graph_node_id, lifecycle_*, transformation_*, valuations,
  geometry_events, photos, business_units, company_groups и т.д.) в C2 **не уходят** —
  они parser-internal. C2 несёт ровно то, что нужно бэкенду по контракту.
- `rights.source_extract_id` и `extracts.raw_json` в pkg отсутствуют → NULL.
- entity без ИНН не попадают в C2 (ключ — ИНН).
Эти допущения согласованы parser-стороной в роли бэкенд-команды; при возражениях
реальной команды бэкенда — правим маппинг здесь.

## Последствия
- ✅ Bundle может нести C2-совместимую БД (`bundle --export-c2`).
- ✅ Внутренняя схема парсера свободна меняться, не ломая контракт C2.
- ⚠️ Маппинг — односторонний (pkg→C2); обратного импорта C2→pkg нет (не нужен).
- ⚠️ При расширении C2 (новые поля контракта) — дополнять правила здесь.

## Реализация / тесты
- `egrn_parser/schema_export.py`; `tests/test_schema_export.py` (7 тестов: слияние
  objects, ИНН-ключ, rights↔restrictions, копия §6, FK-целостность, graceful, CLI).
- CLI: `export-c2`, `bundle --export-c2`.
