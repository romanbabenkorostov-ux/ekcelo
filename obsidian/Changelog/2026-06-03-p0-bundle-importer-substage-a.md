# 2026-06-03 — P0.2 Bundle importer: sub-stage A (manifest + verify + DB import)

## Задача
Начать реализацию SPEC_backend.md §P0.2 «Импортёр Bundle — главный новый модуль». Контракт C3 (`contracts/bundle/`). По выбору пользователя — берём P0 контрактного пакета (а не auth-трек cycle 14).

Подэтап A — ядро (валидация + импорт БД), **без REST и CLI** (sub-stage B) и **без ViewModel-эндпоинтов** (sub-stage C).

## Артефакты

| Файл | LOC | Что |
|---|---|---|
| `backend/app/services/bundle.py` | 415 | Pydantic-схема `Manifest/FileEntry/LotInfo`; `load_manifest`, `verify_files`, `import_bundle` |
| `backend/tests/test_bundle.py` | 290 | 16 тестов |
| `obsidian/Architecture/p0-bundle-importer.md` | — | Снимок поведения подэтапа |

## Реализованное поведение

1. **Манифест-валидация** по C3 (Pydantic, схема открытая `extra="allow"`):
   - 7 обязательных полей.
   - `kind ∈ {"object","lot"}`, `objects[]` без дубликатов, `sha256` строго 64 hex.
2. **Verify files** — sha256 + size для каждой записи `files[]`; missing/mismatch попадают в отчёт.
3. **Идемпотентный импорт** `db.sqlite` источника в целевую БД в одной транзакции:
   - `objects`: content-hash 7 полей → INSERT/UPDATE/SKIP.
   - `entity_registry`: INSERT-OR-SKIP по `inn`.
   - `rights`: INSERT-OR-SKIP по `(cad, type, inn)`, FK-guard.
   - `object_etp_profile` (если `etp_layer_present`): manual/osv не трогаем (ADR-001 §6); неавторитетные перезаписываем.
4. **Автосоздание схемы**: если целевая БД новая — поднимаем минимальный EGRN-слой + миграцию 0001 (как в `init_db_cli`, тот же шаблон).
5. **dry-run** — открыть транзакцию и сразу `rollback()`; отчёт с числами остаётся, БД пустая.

## Тесты (16/16, regression: 190/190)

- 5 schema-тестов (валидные/невалидные манифесты).
- 3 integrity-теста (clean / tampered / missing файл).
- 8 import-тестов: happy path, **идемпотентный повторный прогон = no-op**, обновление изменившегося объекта, dry-run rollback, hash-mismatch блокирует импорт, missing db.sqlite → ошибка, **ETP authoritative (manual/osv) не перезаписывается**.

## Не сделано в этом подэтапе (плановое разделение)

Будет в sub-stage B:
- REST `POST /bundles/import` (multipart zip) + JSON-ответ.
- Console script `ekcelo-import-bundle`.
- Регистрация KMZ в локальном хранилище (под `GET /bundles/{id}/download`).

Будет в sub-stage C:
- ViewModel endpoints: `GET /catalog`, `/objects/{cad}`, `/lots/{lot_id}`, `/objects/{cad}/graph`.

## Связи
- `contracts/bundle/BUNDLE_SPEC.md`, `contracts/bundle/bundle.schema.json`
- `docs/specs/SPEC_backend.md` §P0.2
- `obsidian/Architecture/p0-bundle-importer.md` (снимок состояния)
- ADR-001 (§6 ЭТП-слой — manual/osv приоритет)
- `parser/egrn_parser/merge/upsert.py` — концептуальный референс UPSERT-стратегий
