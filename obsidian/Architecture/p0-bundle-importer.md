# P0.2 — Bundle importer (sub-stages A + B)

> Реализация `SPEC_backend.md §P0.2` — главного нового модуля бэкенда.
> Контракт C3 (`contracts/bundle/`). Этот документ — снимок современного состояния
> (после sub-stages A + B).

## Зачем

Bundle — каноническая единица обмена данными по объекту/лоту между локальным
парсером (Win10) и веб-бэкендом. Идемпотентна: повторная сборка/импорт даёт тот
же результат. Содержит `manifest.json + project.kmz + db.sqlite + json/ + raw/`.

Бэкенд принимает Bundle тремя путями:
1. **CLI** `ekcelo-import-bundle` — для локальных запусков (golden-path, batch).
2. **REST** `POST /bundles/import` — для веб-сценария (фронт/ekcelo-site).
3. **Сервис** `backend.app.services.bundle.import_bundle()` — для интеграции.

Все три используют **одно ядро** (`backend/app/services/bundle.py`) и одинаково
идемпотентны.

## Слои

```
┌─ CLI ─────────────────────────────────────────────────┐
│ lot_orchestrator_web/bundle_cli.py                     │
│ ekcelo-import-bundle --bundle <dir> --db <path>        │
│   [--dry-run] [--no-verify] [--json]                   │
└───────────┬───────────────────────────────────────────┘
            │
┌─ REST ────┼───────────────────────────────────────────┐
│ lot_orchestrator_web/main.py::import_bundle_endpoint   │
│ POST /bundles/import (multipart zip)                   │
│   form: target_db, verify_hashes, dry_run              │
└───────────┼───────────────────────────────────────────┘
            ▼
┌─ Service (ядро) ──────────────────────────────────────┐
│ backend/app/services/bundle.py                         │
│   Manifest / FileEntry / LotInfo  (Pydantic, C3)       │
│   load_manifest(bundle) → Manifest                     │
│   verify_files(bundle, manifest) → list[failure]       │
│   import_bundle(bundle, target_db, ...)→ ImportReport  │
└────────────────────────────────────────────────────────┘
```

## Поведение (общее ядро)

### Манифест-валидация

`Manifest.model_validate(raw)`:
- Обязательные: `bundle_version`, `contracts_version`, `kmz_contract_version`,
  `kind ∈ {"object","lot"}`, `objects[]` непустой/без дубликатов, `files[]`
  непустой, `generated_at` ISO datetime.
- `files[].sha256` — ровно 64 hex символа.
- Схема **открытая** (`extra="allow"`) — новые поля C3 не ломают.

### Verify files

`verify_files(bundle, manifest)` для каждой записи `files[]`:
- Файл существует → не «missing».
- sha256 совпадает с заявленным → не «sha256 mismatch».
- size совпадает → не «size mismatch».

Возвращает `list[str]` — пустой если всё чисто.

### Идемпотентный импорт

`import_bundle(bundle, target_db, *, verify_hashes=True, dry_run=False)` в одной
транзакции:

1. **objects**: для каждой строки источника — content-hash 7 полей. Нет в
   целевой → INSERT. Хеш совпал → SKIP-identical. Хеш отличается → UPDATE.
2. **entity_registry**: INSERT-OR-SKIP по `inn` (никогда не перезаписываем).
3. **rights**: INSERT-OR-SKIP по `(cad_number, right_type, right_holder_inn)`.
   FK-guard: если нет соответствующего `objects` → warning, пропуск.
4. **object_etp_profile** (если `manifest.etp_layer_present`): **ADR-001 §6** —
   `manual/osv` не трогаем; `nspd/exif/llm` заменяем целиком; нет записи → INSERT.

Результат — `ImportReport`:
- `objects_inserted/updated/skipped_identical`, `entities_inserted`,
  `rights_inserted`, `etp_profiles_inserted/skipped_authoritative`,
  `files_verified`, `files_failed[]`, `warnings[]`, `errors[]`.
- `is_noop` → `True` если ни одна целевая строка не изменилась (повтор Bundle).

Автосоздание минимальной EGRN-схемы + миграции 0001 если целевая БД пустая.

`dry_run=True` → транзакция rollback'нута; отчёт остаётся, БД пустая.

## CLI: `ekcelo-import-bundle`

```bash
ekcelo-import-bundle --bundle ./my-bundle/ --db ./ekcelo.sqlite
ekcelo-import-bundle --bundle ./my-bundle/ --db ./ekcelo.sqlite --dry-run
ekcelo-import-bundle --bundle ./my-bundle/ --db ./ekcelo.sqlite --no-verify
ekcelo-import-bundle --bundle ./my-bundle/ --db ./ekcelo.sqlite --json
```

**Exit codes:** `0` успех (включая no-op), `2` input (нет каталога/манифеста),
`3` integrity (sha256/size), `4` ошибка импорта.

Регистрация: `pyproject.toml::[project.scripts]::ekcelo-import-bundle`.

## REST: `POST /bundles/import`

Multipart upload:
- `bundle_zip` (file, required): zip-архив Bundle (manifest.json + db.sqlite
  + project.kmz). Поддерживает 2 формы — файлы в корне или в одном подкаталоге.
- `target_db` (form str, required): путь к ekcelo.sqlite на сервере.
- `verify_hashes` (form bool, default true): sha256/size проверка.
- `dry_run` (form bool, default false): транзакция rollback.

**Ответы:**
- `200` — успех (включая no-op повтор Bundle).
- `400` — bad zip / non-zip / нет manifest.json в архиве.
- `422` — integrity failures (sha256/size mismatch). Body содержит `files_failed[]`.

Body = JSON отчёт (поля `ImportReport`).

## Что НЕ в этом подэтапе (плановое разделение)

Будет в **sub-stage C** (= P0.3):
- `GET /catalog` — список всех объектов в БД (ViewModel summary).
- `GET /objects/{cad}` — ViewModel объекта (4 характеристики: physical /
  ownership / geo / temporal).
- `GET /lots/{lot_id}` — ViewModel лота.
- `GET /objects/{cad}/graph` — граф связей.
- `GET /bundles/{id}/download?fmt=` — реверс-экспорт Bundle.

Регистрация KMZ в локальном хранилище (`bundles/<id>.kmz`) для `/download` —
тоже в C. Пока импорт принимает Bundle и обрабатывает БД, но KMZ не сохраняет
для последующей выдачи.

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `backend/app/services/bundle.py` | ~415 | Pydantic + load/verify/import (sub-stage A) |
| `backend/tests/test_bundle.py` | ~290 | 16 service-тестов |
| `lot_orchestrator_web/bundle_cli.py` | ~120 | CLI `ekcelo-import-bundle` (sub-stage B) |
| `lot_orchestrator_web/tests/test_bundle_cli.py` | ~110 | 7 CLI-тестов |
| `lot_orchestrator_web/main.py` | +75 | `POST /bundles/import` + `_find_bundle_root` |
| `lot_orchestrator_web/tests/test_bundle_endpoint.py` | ~200 | 8 endpoint-тестов |
| `pyproject.toml` | +2 | `ekcelo-import-bundle` console script |

**Тесты:** 31 bundle-тестов (16+7+8); полный suite **205/205 pass; smoke 33/33**.

Покрытие:
- Service: schema validation, integrity (clean/tampered/missing), happy path,
  no-op повтор, update изменившегося, dry-run rollback, hash-mismatch блокирует,
  missing db.sqlite → ошибка, ETP authoritative не перезаписывается.
- CLI: happy path, noop, dry-run, --no-verify, hash mismatch=3,
  missing bundle=2, --json.
- Endpoint: happy path, subdir-форма архива, идемпотентность, dry-run, bad
  zip → 400, non-zip filename → 400, нет manifest → 400, tampered → 422.

## Связи

- Контракт: `contracts/bundle/BUNDLE_SPEC.md`, `bundle.schema.json`.
- Спека: `docs/specs/SPEC_backend.md` §P0.2.
- ADR-001: ЭТП-слой §6 — manual/osv приоритет.
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md`.
- Reuse: `parser/egrn_parser/merge/upsert.py` (концептуальный референс
  UPSERT-стратегий).
