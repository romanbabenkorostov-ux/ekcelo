# P0.1 — DB-контракт C2 (sub-stage P0.1.1)

> Реализация `SPEC_backend.md §P0.1` — машиночитаемый DB-контракт interchange-
> схемы Bundle. После закрытия основного тела P0.3 (C1+C2+C3.1+C3.2 ViewModel +
> Bundle storage + reverse-export), P0.1 — следующий приоритетный трек по
> SPEC_backend (выше Auth-трека 14-16). Не блокирует parser-team и не требует
> их кооперации (см. §«Зачем» ниже).

## Зачем именно сейчас

После C3.2 round-trip Bundle round-trip работает: parser эмитит Bundle →
backend импортирует → backend реэкспортирует → импорт = no-op. Но контракт
**схемы внутри Bundle** живёт неявно (в `schema/egrn_current_schema.sql` и в
исходниках `bundle.py`). Это значит:

- Parser может сломать формат, и backend не отловит до запуска impor;
- CI не охраняет соответствие двух источников (schema.sql ↔ контракт).

P0.1.1 закрывает обе проблемы машиночитаемым контрактом + sync-guard'ом.

## Почему НЕ блокирует parser-team

Контракт **read-only** для parser'а: он фиксирует то, что parser УЖЕ эмитит
(потому что round-trip C3.2 зелёный). Это формализация существующего поведения,
не новое требование. Parser-team не должен ничего менять. Если они захотят
позже валидировать свой down-projection — могут читать `contracts/db/schema.json`.

## Архитектура

```
┌─ DDL источник правды ─────────────────────────────────────┐
│ schema/egrn_current_schema.sql  (8 таблиц §1..§6)         │
└───────────┬───────────────────────────────────────────────┘
            │ зеркалируется в JSON
            ▼
┌─ Машиночитаемый контракт ─────────────────────────────────┐
│ contracts/db/schema.json                                   │
│   { contract_version, ddl_source, sections,                │
│     tables: {<t>: {section, restorable, primary_key,       │
│                    foreign_keys, columns}} }               │
│ contracts/db/DB_SPEC.md  (человекочитаемый снимок)        │
└───────────┬───────────────────────────────────────────────┘
            │
┌─ Backend service ──────────────────────────────────────────┐
│ backend/app/services/db_contract.py                        │
│   load_contract()                       → dict             │
│   validate_db(db_path)                  → list[str]        │
│   check_contract_matches_ddl()          → list[str]        │
└────────────────────────────────────────────────────────────┘
```

## Поведение

### `load_contract` / `contract_tables`
Парсит JSON-контракт. 8 таблиц, помеченных `section` (1..6) и `restorable`
(true для §1..§5, false для §6 — соответствует ADR-001).

### `validate_db(db, *, require_section6=False)`
Проверяет соответствие sqlite-БД контракту:
- §1..§5 таблиц **обязательны** с required-колонками.
- §6 опционально (ADR-001: ЭТП-слой не восстановим из выписок); если
  таблица §6 присутствует — её колонки проверяются.
- Тип колонки сверяется по SQLite affinity (TEXT/INTEGER/REAL/NUMERIC взаимозаменяемы).
- **Лишние колонки в БД НЕ являются нарушением** — схема расширяема вперёд.

Возвращает список нарушений (пусто = соответствует).

### `check_contract_matches_ddl()`
CI sync-guard: сверяет таблицы и колонки контракта с реальной
`schema/egrn_current_schema.sql`. Lightweight regex-парсер DDL —
не полный SQL-движок, но достаточен для гарда «контракт не отстал».

Игнорирует `-- комментарии` (strip перед парсингом) и table-level
constraints (`PRIMARY KEY (a, b)`).

Тест `test_contract_in_sync_with_real_ddl` падает если кто-то изменил
schema.sql, но забыл обновить контракт.

## Что НЕ в этом подэтапе

Будет в **P0.1.2**:
- Интеграция `validate_db` в `import_bundle` или endpoint `/bundles/import`
  — early-fail на невалидном db.sqlite (422 + список нарушений).
- CLI `ekcelo-validate-bundle-db <path>` для локального дев-цикла парсера.

Будет в **P0.1.3** (опц.):
- Кодогенерация Pydantic/dataclass моделей из контракта.

Будет в **P0.1.4** (опц.):
- Машиночитаемая мапа parser-rich-schema → backend-interchange-schema.

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `contracts/db/schema.json` | ~150 | машиночитаемый контракт |
| `contracts/db/DB_SPEC.md` | ~140 | человекочитаемая спека |
| `backend/app/services/db_contract.py` | ~200 | load + validate_db + sync-guard |
| `backend/tests/test_db_contract.py` | ~225 | 13 тестов |

**Тесты:** 13 в P0.1.1; полный suite в sandbox **299 pass**
(baseline 191 + 28 C1 + 24 C2 + 25 C3.1 + 18 C3.2 + 13 P0.1.1).

Покрытие:
- load_contract: 8 таблиц, restorable=false для §6, contract_version + ddl_source.
- validate_db: full passes, egrn-only passes без §6, fails если require_section6
  на egrn-only, detects missing table, missing column, extra columns allowed.
- sync-guard: контракт ↔ реальная schema.sql зелёный, detects extra contract
  table, detects missing contract column, игнорирует table-level constraints.

## Связи

- DDL источник: `schema/egrn_current_schema.sql`.
- Контракт-пакет: `contracts/PACKAGE.md` (governance C1..C6).
- ADR-001 §6 (CLAUDE.md §3): restorable=false для ЭТП-слоя.
- Bundle-импорт: `backend/app/services/bundle.py` (читает таблицы по контракту).
- Спека: `docs/specs/SPEC_backend.md` §P0.1.
- Предшественники: `obsidian/Architecture/p0-bundle-importer.md`,
  `p0-viewmodel.md`, `p0-bundle-storage.md`, `p0-bundle-export.md`.
