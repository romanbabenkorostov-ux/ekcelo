# 2026-06-23 — §7 Geo entities (bitemporal, M:N)

## Задача
Ввести в БД сущность «геосущность» (точка/контур), к которой M:N привязываются
активы и которая меняется во времени. ЕГРН-слоя не касается — отдельный
не-ЕГРН §7 (по аналогии с §6 ADR-001).

## Решения (фиксируются в ADR-002)
- M:N привязка через `asset_geo_link` (свойственная история через valid_from/to).
- Bitemporal: `valid_from + valid_to + recorded_at` на всех 3 таблицах истории.
- GeoJSON Geometry в TEXT (без SpatiaLite; прямо в ViewModel.geo).
- `restorable=false` (как §6); валидатор C2 учитывает §7 как опциональный.

## Что сделано
- ✨ `schema/migrations/0003_geo_entities.sql` — 4 таблицы + индексы + CHECK
  (lat/lon range, valid_to > valid_from, confidence [0..1]) + UNIQUE на
  asset_geo_link.
- ✏️ `schema/egrn_current_schema.sql` — §7 mirror.
- ✏️ `parser/exporters/etp/init_db_cli.py` — применяет 0003 после 0001.
- ✨ `backend/app/services/geo.py` — `register_geo`/`add_contour`/`add_point`/
  `link_asset` + bitemporal `geo_for_asset(as_of=...)` + shortcut
  `primary_geo_for_asset` + dataclass `GeoSnapshot`.
- ✏️ `contracts/bundle-db-slice/schema.json` — +4 таблицы (section="7",
  restorable=false).
- ✏️ `backend/app/services/db_contract.py` — §7 как опциональный слой.
- ✏️ `backend/app/services/db_models.py` — перегенерён (codegen).
- ✏️ `backend/tests/test_db_contract.py` — обновлён список таблиц + новый
  тест `test_contract_marks_section7_not_restorable`.
- ✨ `backend/tests/test_geo.py` — 19 тестов (запись, bitemporal lookup,
  M:N, инварианты, FK CASCADE/RESTRICT).
- ✨ `obsidian/Database/geo-entities-7.md` — ER + workflow + inv'ы.
- ✨ `obsidian/Decisions/ADR-002-geo-entities.md` — rationale + альтернативы.

## Тесты
- **backend 147 passed** (+19 geo +1 §7-contract-test +корректировка
  test_load_contract).
- **lot_orchestrator_web 297 passed** (regression чистая).
- **parser smoke 33/33**.

## Что НЕ сделано (намеренно вне scope)
- Парсер KMZ→DB: не пишет в §7 пока. Подключение — отдельной задачей (нужен
  feature flag импортёра).
- `build_object_viewmodel` не читает из §7 пока (без записи нечего читать).
- Прод-runtime миграция в `parser/egrn_parser/db/migrations.py` — БД не в
  проде, добавится при первом проде.
- Spatial-индексы / WKT — когда понадобится.

## Канал доставки
zip-handoff.
