# P0.1 — DB-контракт C2 (sub-stages P0.1.1 + P0.1.2)

> Реализация `SPEC_backend.md §P0.1` — машиночитаемый DB-контракт interchange-
> схемы Bundle + валидация при импорте. После закрытия основного тела P0.3
> (C1+C2+C3.1+C3.2), P0.1 — следующий приоритетный трек по SPEC_backend.
> Не блокирует parser-team.

## Зачем

Контракт **схемы внутри Bundle** жил неявно (в `schema/egrn_current_schema.sql`
и исходниках `bundle.py`). P0.1 формализует его машиночитаемо +
охраняет от дрейфа + опционально валидирует входящий Bundle до импорта.

## Почему НЕ блокирует parser-team

Контракт **read-only** для parser'а: фиксирует то, что parser УЖЕ эмитит
(round-trip C3.2 зелёный). Это формализация существующего поведения. Parser-team
ничего не меняет. Когда захотят валидировать свой экспорт — запускают
`ekcelo-validate-bundle-db` (P0.1.2 CLI).

## Архитектура

```
┌─ DDL источник правды ─────────────────────────────────────┐
│ schema/egrn_current_schema.sql  (8 таблиц §1..§6)         │
└───────────┬───────────────────────────────────────────────┘
            │ зеркалируется в JSON
            ▼
┌─ Машиночитаемый контракт ─────────────────────────────────┐
│ contracts/db/schema.json + DB_SPEC.md                      │
└───────────┬───────────────────────────────────────────────┘
            │
┌─ Backend service + интеграция ─────────────────────────────┐
│ backend/app/services/db_contract.py                        │
│   load_contract() / validate_db() / check_contract_matches_ddl()
│                                                            │
│ backend/app/services/bundle.py  (P0.1.2)                   │
│   import_bundle(..., validate_schema=False)                │
│     → ImportReport.schema_violations                       │
│                                                            │
│ lot_orchestrator_web/main.py  (P0.1.2)                     │
│   POST /bundles/import  form: validate_schema (default F)  │
│     нарушения → 422 + schema_violations[]                  │
│                                                            │
│ lot_orchestrator_web/validate_bundle_db_cli.py  (P0.1.2)   │
│   ekcelo-validate-bundle-db <bundle|db> [--require-section6][--json]
└────────────────────────────────────────────────────────────┘
```

## Поведение — P0.1.1 (контракт + валидатор)

### `load_contract` / `contract_tables`
Парсит JSON-контракт. 8 таблиц с `section` (1..6) и `restorable` (true для
§1..§5, false для §6 — ADR-001).

### `validate_db(db, *, require_section6=False)`
- §1..§5 таблиц **обязательны** с required-колонками.
- §6 опционально (ADR-001: ЭТП-слой не восстановим из выписок); если §6
  присутствует — её колонки проверяются. `require_section6=True` — строгий режим.
- Тип по SQLite affinity (TEXT/INTEGER/REAL/NUMERIC взаимозаменяемы).
- **Лишние колонки в БД НЕ являются нарушением** — схема расширяема вперёд.

### `check_contract_matches_ddl()`
CI sync-guard: контракт ↔ реальная `schema/egrn_current_schema.sql`.
Lightweight regex-парсер DDL (strip `-- comments`, фильтр table-level
constraints). Тест `test_contract_in_sync_with_real_ddl` падает при дрейфе.

## Поведение — P0.1.2 (валидация при импорте)

### `import_bundle(..., validate_schema=False)`
- При `validate_schema=True` — `validate_db(source_db)` ДО мутации target_db.
- Нарушения → `report.schema_violations` + `report.errors`; импорт прерывается
  **до** любой записи в целевую БД.
- **Default False** — не ломает минимальные тест-фикстуры; реальные Bundle от
  парсера — полная схема, для них имеет смысл True.

### `POST /bundles/import` form-param `validate_schema` (default false)
- При `true` и нарушениях → `422` с `schema_violations[]` в payload.
- Payload всегда содержит `schema_violations` (пустой если ок/выключено).

### CLI `ekcelo-validate-bundle-db <path>`
Standalone-валидатор для парсер-команды (проверка ДО отправки Bundle).
- Принимает каталог Bundle (ищет `db.sqlite`) или прямой `*.sqlite`.
- `--require-section6`, `--json`.
- Exit: `0` ок, `2` input-ошибка (нет db.sqlite), `3` нарушения контракта.

## Что НЕ в этом подэтапе

Будет в **P0.1.3** (опц.):
- Кодогенерация Pydantic/dataclass моделей из `contracts/db/schema.json`.

Будет в **P0.1.4** (опц.):
- Машиночитаемая мапа богатой parser-схемы (`parser/egrn_parser/db/schema.sql`,
  23 таблицы) → interchange-схемы (8 таблиц). Для parser-team.

## Файлы и тесты

| Файл | LOC | Назначение | Подэтап |
|---|---|---|---|
| `contracts/db/schema.json` | ~150 | машиночитаемый контракт | P0.1.1 |
| `contracts/db/DB_SPEC.md` | ~140 | человекочитаемая спека | P0.1.1 |
| `backend/app/services/db_contract.py` | ~200 | load + validate_db + sync-guard | P0.1.1 |
| `backend/tests/test_db_contract.py` | ~225 | 13 тестов | P0.1.1 |
| `backend/app/services/bundle.py` | +~20 | `validate_schema` param + schema_violations | P0.1.2 |
| `backend/tests/test_bundle_validate_schema.py` | ~140 | 4 теста | P0.1.2 |
| `lot_orchestrator_web/validate_bundle_db_cli.py` | ~100 | CLI ekcelo-validate-bundle-db | P0.1.2 |
| `lot_orchestrator_web/tests/test_validate_bundle_db_cli.py` | ~130 | 7 тестов | P0.1.2 |
| `lot_orchestrator_web/main.py` | +~5 | `validate_schema` form-param + 422 | P0.1.2 |
| `lot_orchestrator_web/tests/test_validate_schema_endpoint.py` | ~150 | 3 теста | P0.1.2 |
| `pyproject.toml` | +2 | `ekcelo-validate-bundle-db` script | P0.1.2 |

**Тесты:** 13 (P0.1.1) + 14 (P0.1.2) = 27; полный suite в sandbox **313 pass**.

Покрытие P0.1.2:
- import_bundle: validate_schema off импортирует минимальную БД (backward-compat),
  on проходит полную БД, on блокирует минимальную (violations + 0 inserted),
  on не трогает target при нарушении.
- CLI: valid→0, invalid→3, resolve db в каталоге Bundle, missing path→2,
  пустой каталог→2, --json, --require-section6.
- endpoint: без validate принимает минимальную, validate+full→200,
  validate+minimal→422 с schema_violations + 0 inserted.

## Связи

- DDL источник: `schema/egrn_current_schema.sql`.
- Контракт-пакет: `contracts/PACKAGE.md` (governance C1..C6).
- ADR-001 §6 (CLAUDE.md §3): restorable=false для ЭТП-слоя.
- Bundle-импорт: `backend/app/services/bundle.py`.
- Спека: `docs/specs/SPEC_backend.md` §P0.1.
- Предшественники: `p0-bundle-importer.md`, `p0-viewmodel.md`,
  `p0-bundle-storage.md`, `p0-bundle-export.md`.
