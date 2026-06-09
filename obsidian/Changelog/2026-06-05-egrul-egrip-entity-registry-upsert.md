# 2026-06-05 — Запись subject ЕГРЮЛ/ЕГРИП в entity_registry (разблокировано)

## Суть
Блокер «враппер запись→БД» снят частично: таблица `entity_registry`
(`egrn_parser/db/schema.sql`) уже спроектирована под ЕГРЮЛ-обогащение
(`egrul_status`, `reg_date`, `okved_main`, `kpp`, `egrul_enriched_at`, `UNIQUE(inn)`).
Пишем туда `subject`. Связи (учредители/директора/преемники) — отдельный
граф-слой (`org_connections` / будущий `contracts/db`), их НЕ трогаем.

## Сделано
- **`egrul_egrip_db.py`**: `upsert_subject(conn, record)` / `upsert_records` —
  идемпотентный upsert по `inn` (`ON CONFLICT(inn) DO UPDATE`, `COALESCE`:
  непустое из выписки актуализирует, NULL не затирает). registry/kind →
  `entity_type` (`legal_entity`/`individual`), `ogrnip`→`ogrn`, статус (в т.ч.
  «прекращено: <способ>»), `okved_main` как JSON, `egrul_enriched_at=now`.
- **CLI** `egrul_egrip_pipeline --db file.sqlite` — пишет subject'ы в БД.
- **Тесты** `tests/test_egrul_egrip_db.py` (6): insert/идемпотентный update,
  COALESCE не затирает, обновление при наличии значения, ИП→individual,
  без ИНН→skip, статус-прекращение. Smoke против реальной DDL пакета — OK.
  Итого по ЕГРЮЛ/ЕГРИП — **30/30 зелёных**.

## Файлы под нож
- `parser/egrn_parser/parsers/egrul_egrip_db.py` (новый)
- `parser/egrn_parser/parsers/egrul_egrip_pipeline.py` (+`--db`)
- `parser/tests/test_egrul_egrip_db.py` (новый)

## Решения
- Пишем ТОЛЬКО идентификацию субъекта в существующую `entity_registry`
  (не спекулятивно — колонки под это есть). Связи остаются в нормализованной
  записи (dict) до появления граф-таблицы (`org_connections`/`contracts/db`).
- Уважаем существующую конвенцию upsert из `merge/upsert.py` (INN-ключ, COALESCE).

## Дальше
- Связи учредителей/руководителей → `org_connections` (граф-слой) — когда
  будет согласован `contracts/db/SCHEMA_SPEC.md` (граф = логический, ADR соседнего чата).
