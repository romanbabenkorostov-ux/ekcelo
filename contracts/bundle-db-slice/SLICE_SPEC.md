# C2 — DB interchange contract

> Машиночитаемый контракт interchange-схемы Bundle (`db.sqlite` внутри Bundle).
> Источник правды DDL — `schema/egrn_current_schema.sql`. Контракт — его
> JSON-зеркало (`contracts/db/schema.json`). Реализация валидатора + sync-guard
> — `backend/app/services/db_contract.py`.

## Зачем

Bundle переносит данные между parser (Win10) и backend (web). `db.sqlite`
внутри Bundle — упрощённая §1..§6 модель (8 таблиц), не богатая исходная
модель parser'а (`parser/egrn_parser/db/schema.sql`, 23 таблицы). Parser
down-проецирует свою модель в эту interchange-форму при экспорте.

C2 фиксирует interchange-схему машиночитаемо чтобы:
1. **Parser** знал, какие таблицы/колонки эмитить.
2. **Backend** валидировал входящий Bundle до импорта.
3. **CI** ловил дрейф между `schema/egrn_current_schema.sql` и контрактом.

## ADR-001 §6 — restorable=true/false

| Секция | Таблицы | restorable | Смысл |
|---|---|---|---|
| §1 | objects | true | слепок ЕГРН |
| §2 | entity_registry | true | слепок ЕГРН |
| §3 | rights | true | слепок ЕГРН |
| §4 | extracts | true | слепок ЕГРН |
| §5 | object_restrictions | true | слепок ЕГРН |
| §6 | object_etp_profile, lots, lot_items | **false** | не-ЕГРН ЭТП-слой |

`restorable=true` означает: данные восстанавливаются из выписок ЕГРН. При
пересоздании БД эти таблицы будут переимпортированы.

`restorable=false` означает: данные приходят из других источников (ОСВ
экономиста, EXIF фото, NSPD, LLM, ручная правка). При пересоздании БД эти
таблицы НЕ восстанавливаются. Имеют `source` ∈ {osv, exif, manual, nspd, llm}
и `confidence` ∈ [0, 1]. ADR-001 §6 запрещает перезаписывать `manual`/`osv`
записи при импорте.

## Контракт (`contracts/db/schema.json`)

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ekcelo.ru/contracts/db/schema.json",
  "contract_version": "1.0.0",
  "ddl_source": "schema/egrn_current_schema.sql",
  "sections": { "1": "...", "...": "..." },
  "tables": {
    "<table_name>": {
      "section": "1..6",
      "restorable": true | false,
      "primary_key": ["col"],
      "foreign_keys": [
        { "columns": ["cad_number"], "references": "objects(cad_number)" }
      ],
      "columns": {
        "<col_name>": {
          "type": "TEXT | INTEGER | REAL",
          "nullable": true | false,
          "pk": true,                    // опц.
          "autoincrement": true,         // опц.
          "default": "...",              // опц.
          "check_in": ["a", "b"],        // опц.
          "check_range": [0.0, 1.0],     // опц.
          "note": "..."                  // опц.
        }
      }
    }
  }
}
```

8 таблиц: `objects`, `entity_registry`, `rights`, `extracts`,
`object_restrictions`, `object_etp_profile`, `lots`, `lot_items`.

## API (`backend.app.services.db_contract`)

### `load_contract() → dict`
Читает и парсит `contracts/db/schema.json`.

### `contract_tables() → dict`
Шорткат `load_contract()["tables"]`.

### `validate_db(db_path, *, contract=None, require_section6=False) → list[str]`
Проверяет, что sqlite-БД соответствует контракту. Возвращает список
нарушений (пусто = соответствует).

- Все таблицы §1..§5 контракта обязаны существовать с required-колонками.
- Таблицы §6 (`restorable=false`) проверяются только если `require_section6`
  ИЛИ если они физически присутствуют в БД (тогда — на корректность колонок).
  ADR-001: §6 может отсутствовать в чистом ЕГРН-слепке.
- Тип сверяется по SQLite affinity (TEXT/INTEGER/REAL).
- **Лишние колонки в БД НЕ являются нарушением** — схема расширяема вперёд
  (parser может эмитить дополнительные поля для будущих версий контракта).

### `check_contract_matches_ddl(*, contract=None, ddl_text=None) → list[str]`
Сверяет таблицы/колонки контракта с `schema/egrn_current_schema.sql`.
Возвращает список расхождений (пусто = в синхроне). Используется CI-guard'ом
(тест `test_contract_in_sync_with_real_ddl`), который **обязательно зелёный**
после каждого изменения schema.sql или контракта.

Парсер DDL — lightweight regex (не полный SQL-движок); достаточно для guard'а
«контракт не отстал от schema.sql». Игнорирует `-- комментарии` и
table-level constraints (`PRIMARY KEY (a, b)`).

## Workflow для разработчика

### При изменении DDL (schema/egrn_current_schema.sql)
1. Применить изменение в `schema/egrn_current_schema.sql`.
2. Зеркально обновить `contracts/db/schema.json`.
3. `pytest backend/tests/test_db_contract.py::test_contract_in_sync_with_real_ddl`.
4. Если sync-guard зелёный → коммит. Если нет — `check_contract_matches_ddl()`
   выдаст конкретный список расхождений.

### При создании Bundle (parser-side)
1. Down-project богатую parser-модель в §1..§6.
2. Опц.: `validate_db(bundle_db_path)` — early-fail до отправки Bundle.

### При импорте Bundle (backend-side)
1. `import_bundle` уже валидирует `manifest.json` через C3-схему.
2. (Будущее, P0.1.2) `validate_db` распакованного `db.sqlite` до запуска
   `import_bundle` — отсечь невалидные Bundle на ранней стадии.

## Что НЕ в этом подэтапе

Будет в **P0.1.2**:
- Интеграция `validate_db` в `import_bundle` (или в endpoint) — отказ
  принимать Bundle с не-схемным db.sqlite (статус 422 + список нарушений).
- CLI-guard `ekcelo-validate-bundle-db <path>` — для локальной проверки парсер-команды.

Будет в **P0.1.3** (опц.):
- Кодогенерация Python-моделей из контракта (Pydantic/dataclass) — чтобы
  `import_bundle` использовал типизированный доступ вместо `row["..."]`.

Будет в **P0.1.4** (опц.):
- Сопоставление богатой parser-схемы и interchange-схемы:
  машиночитаемая мапа `parser.land_objects + building_objects → backend.objects`.
  Полезно для parser-команды, чтобы down-projection не дрейфовал.

## Связи

- DDL источник: `schema/egrn_current_schema.sql`.
- ADR: `obsidian/Decisions/` (ADR-001 §6 restorable=false).
- Bundle-импорт: `backend/app/services/bundle.py` (читает эти таблицы).
- Контракт пакет: `contracts/PACKAGE.md` (C1..C6 governance).
- Спека: `docs/specs/SPEC_backend.md` §P0.1.
