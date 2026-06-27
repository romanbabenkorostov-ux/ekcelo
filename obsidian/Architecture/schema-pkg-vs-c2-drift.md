# Ревизия: пакетная `db/schema.sql` ↔ C2 (`schema/egrn_current_schema.sql`)

> SPEC_parser item 3: «Сверить `db/schema.sql` пакета с C2 (§1–§5)». Дата: 2026-06-09.
> C2 = `schema/egrn_current_schema.sql` (источник истины, ADR-001/CLAUDE.md §1..§6).
> Пакетная = `parser/egrn_parser/db/schema.sql` (внутренняя БД CLI `egrn-parser` v1.10).

## Вывод (кратко)
Это **два разных модели данных**, а не мелкий дрейф. Пакетная схема (24 таблицы) —
детальная внутренняя модель парсера; C2 (8 таблиц) — компактный контракт обмена.
Прямая «сверка колонка-в-колонку» невозможна без модели-маппинга. Реконсиляция —
**отдельное архитектурное решение (ADR)**, затрагивающее контракт C2 с backend/viewer.

## Таблицы

| | Таблицы |
|---|---|
| **C2 (8)** | objects, rights, object_restrictions, entity_registry, extracts, lots, lot_items, object_etp_profile |
| **Пакет (24)** | building_objects, land_objects, rights, right_holders, ownership_chain, entity_registry, entity_relations, extracts, linked_objects, object_geometries, geometry_events, object_events, right_events, valuations, photos, accessories, contacts, business_units, company_groups, code_dictionary, monitoring_log, enrichment_log, schema_registry, system_meta |
| **Только в C2** | objects, object_restrictions, lots, lot_items, object_etp_profile |
| **Общие (имя)** | entity_registry, extracts, rights |

## Ключевые модельные расхождения
1. **Объект недвижимости.** C2 — единая `objects` (`object_type`: land/building/…).
   Пакет — раздельные `building_objects` + `land_objects`. → нужен маппинг
   `objects` ↔ (building_objects ∪ land_objects).
2. **§6 ЭТП-слой.** В C2: `object_etp_profile`/`lots`/`lot_items` (ADR-001, ручной
   слой). В пакете — отсутствуют (пакет — только §1–§5 ЕГРН + свои расширения).
3. **Общие таблицы — разные колонки:**
   - `entity_registry`: пакет +12 колонок (entity_id, graph_node_id, group_id,
     egrul_*, kpp, okved_main, reg_date, liquidation_date, legal_address, …);
     C2 — подмножество (6 общих). Расширение, не конфликт.
   - `extracts`: модели расходятся — C2 {id, document_type, parser_version,
     raw_json}; пакет {extract_id, content_hash, organ, recipient, total_*, …}.
   - `rights`: пакет — богатая модель (обременения/аренда/сервитут/преемственность,
     ~38 колонок); C2 — компактная {cad_number, registration_number,
     right_holder_inn, …}. Семантически близки, структурно различны.

## Рекомендация
- **C2 — канон обмена** (ADR-001). Пакетная схема — parser-internal (CLI пишет в
  свою БД; экспорт в C2 — через слой маппинга/экспортёров `exporters/`).
- Зафиксировать это явно: пакет НЕ обязан совпадать с C2 по таблицам; обязан уметь
  **экспортировать** §1–§5 в C2-форму (objects/rights/…). Эту границу описать в
  отдельном ADR «pkg-schema ↔ C2 export mapping».
- Не сливать схемы напрямую (риск для контракта C2 с backend/viewer); сверка
  выполнена и задокументирована здесь.

## Решено (2026-06-09) → ADR-007
Заказчик подтвердил: **C2 — канон**. Реализован **слой экспорта pkg → C2**
(`egrn_parser/schema_export.export_to_c2`, CLI `export-c2` / `bundle --export-c2`).
Правила перевода таблиц — `Decisions/ADR-007-pkg-schema-to-c2-export.md`.
Прямого слияния схем НЕ делаем (внутренняя схема свободна; C2 — через экспорт).
