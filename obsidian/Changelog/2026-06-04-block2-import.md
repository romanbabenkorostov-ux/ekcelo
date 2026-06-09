# 2026-06-04 — Импорт Block-2 БД парсера → C2 + узел accessory

## Суть
Следующий пункт плана: стадия импорта реальной Block-2 БД парсера
(`egrn_parser/db/schema.sql`) в каноническую C2-схему. Маппинг — по PARSER_VOCAB_MAP §5.

## Сделано
- `contracts/db/import_block2.py` — импортёр (читает Block-2 сырым sqlite3, пишет ORM):
  - `land_objects`/`building_objects` → `objects`(§1) + `entities`(§7);
  - `accessories` → `entities(kind='accessory')` + `geometries(POINT)` + ребро `CONTAINS`;
  - `object_geometries` → `geometries` (WKT, crs→srid);
  - `entity_registry`+`right_holders` → `subjects`(§10) + `entity_registry`(§2 compat) + `subject_kpp`;
  - `rights` → `relations[legal]` (OWNS/LEASES/MORTGAGED_BY/RESTRICTED_BY) + `legal_relation`
    + `assertions`/`evidences` (источник EGRN, weight 1.0);
  - `ownership_chain` → `relations[legal/corporate CONTROLS]` (share_pct в meta).
- `contracts/db/models.py` — **+1 строка**: `EntityKind.accessory` (PARSER_VOCAB_MAP §6).
- `contracts/db/migrations/versions/0003_accessory_kind.py` — добавление значения
  enum: PG `ALTER TYPE ... ADD VALUE`, SQLite no-op (kind хранится как VARCHAR).
- `contracts/db/tests/test_import_block2.py` — замок (synthetic Block-2 → проверка состава).

## Проверено (SQLite)
- `upgrade head` 0001→0003 зелёным; импорт synthetic Block-2 →
  3 objects; entities {land1, building1, room1, accessory1, beneficiary_legal2};
  рёбра {OWNS1, LEASES1, CONTAINS1, CONTROLS1}; confidence {1.0 (ЕГРН), 0.4 (checko→LLM)};
  2 geometries (polygon + point). `pytest` — 1 passed.

## Порядок выкладки
A → B → C → **D (этот)**. `models.py` здесь — версия дата-инженера + 1 строка
(`accessory`); перезаписывает деплой из архива A. Запуск теста: из корня репо
`PYTHONPATH=. pytest contracts/db/tests/test_import_block2.py`.

## v1 НЕ импортит (TODO)
`company_groups`, `business_units`, `valuations`, `object_events` — следующий слайс.

## Дальше
Единый граф-эмиттер: свести graph_json v1.1 и v14 к одному выходу поверх `relations`
(убрать дубль словарей узлов/рёбер).
