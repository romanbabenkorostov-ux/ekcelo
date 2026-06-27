# 2026-06-09 — Слой экспорта pkg → C2 (ADR-007) + CLI export-c2 / bundle --export-c2

Решение заказчика: C2 — канон; parser-сторона берёт роль бэкенд-команды по правилам
перевода (с пояснениями); добро на слой экспорта.

## Реализовано
- **`egrn_parser/schema_export.export_to_c2(src, out)`** — внутренняя БД парсера →
  C2-формат (`schema/egrn_current_schema.sql`):
  - `objects` ← `building_objects` ∪ `land_objects` (единая таблица, object_type);
  - `entity_registry` ← pkg (PK inn; строки без ИНН пропускаются);
  - `rights` ← `rights[right_category='right']` + `right_holders.inn`;
  - `object_restrictions` ← `rights[encumbrance|restriction]`;
  - `extracts` ← `extracts`;
  - §6 (`object_etp_profile`/`lots`/`lot_items`) — копия как есть (C2-нативные).
  - Устойчив к отсутствию таблиц/колонок; FK-целостность результата проверена.
- **CLI:** `egrn-parser export-c2 --db --out` (11-я команда) + флаг
  `egrn-parser bundle --export-c2` — Bundle несёт C2-совместимую `db.sqlite`.

## ADR-007 (правила перевода = «контракт бэкенда»)
`obsidian/Decisions/ADR-007-pkg-schema-to-c2-export.md` — поколоночный маппинг
§1–§5, явные потери/допущения (parser-internal расширения в C2 не уходят; entity
без ИНН пропускаются; raw_json/source_extract_id → NULL). drift-док и golden-path
README обновлены (ADR-007 закрывает вопрос pkg↔C2).

## Тесты
- `tests/test_schema_export.py` (+7): слияние objects, ИНН-ключ, rights↔restrictions,
  копия §6, FK-целостность, graceful-без-таблиц, CLI export-c2.
- Smoke: `bundle --export-c2` пакует C2-БД (все 8 C2-таблиц). 13 passed (с bundle).

## Файлы
- `parser/egrn_parser/schema_export.py` (новый)
- `parser/egrn_parser/cli.py` (+cmd_export_c2, +export-c2 subparser, +bundle --export-c2)
- `parser/tests/test_schema_export.py` (новый)
- `obsidian/Decisions/ADR-007-pkg-schema-to-c2-export.md` (новый)
- `obsidian/Architecture/schema-pkg-vs-c2-drift.md`, `obsidian/Golden-Path-Economist/README.md`,
  `docs/specs/SPEC_parser.md` (обновлены)
