# 2026-06-03 — P0.2 Bundle importer: sub-stage B (REST + CLI)

## Задача
Продолжить `SPEC_backend.md §P0.2`. Sub-stage A дал ядро (валидация + impl);
B оборачивает его в REST endpoint и CLI — два официальных канала приёма Bundle.

## Артефакты

| Файл | LOC | Что |
|---|---|---|
| `lot_orchestrator_web/bundle_cli.py` | ~120 | CLI `ekcelo-import-bundle` (тонкая обёртка, без логики) |
| `lot_orchestrator_web/tests/test_bundle_cli.py` | ~110 | 7 CLI-тестов |
| `lot_orchestrator_web/main.py` | +75 LOC | `POST /bundles/import` (multipart) + хелпер `_find_bundle_root` |
| `lot_orchestrator_web/tests/test_bundle_endpoint.py` | ~200 | 8 endpoint-тестов |
| `pyproject.toml` | +2 LOC | `ekcelo-import-bundle = "lot_orchestrator_web.bundle_cli:main"` |
| `obsidian/Architecture/p0-bundle-importer.md` | переписан | Снимок объединённого состояния A+B (CLI/REST/Service слои) |
| `obsidian/Architecture/roadmap-2026-06.md` | sub-stage B ✅ | |

## CLI: `ekcelo-import-bundle`

```bash
ekcelo-import-bundle --bundle ./my-bundle --db ./ekcelo.sqlite
ekcelo-import-bundle --bundle ./my-bundle --db ./ekcelo.sqlite --dry-run
ekcelo-import-bundle --bundle ./my-bundle --db ./ekcelo.sqlite --no-verify
ekcelo-import-bundle --bundle ./my-bundle --db ./ekcelo.sqlite --json
```

Exit codes: `0` успех/no-op, `2` input ошибка, `3` integrity, `4` импорт.
Регистрация — `pyproject.toml::[project.scripts]`.

## REST: `POST /bundles/import`

Multipart form:
- `bundle_zip` (file): zip Bundle.
- `target_db` (str): путь к sqlite на сервере.
- `verify_hashes` (bool, default true), `dry_run` (bool, default false).

Возвращает JSON-отчёт. `200` успех/noop, `400` bad zip / non-zip / нет manifest,
`422` integrity failures.

Поддержка двух форм архива: файлы в корне ИЛИ в одном подкаталоге.

## Что НЕ в этом подэтапе

- **Регистрация KMZ** для будущего `/bundles/{id}/download` — отложена до C
  (потребует sidecar-таблицы `bundles(id, kmz_path, manifest_json, …)`).
- **ViewModel endpoints** (`/catalog`, `/objects/{cad}`, `/lots/{lot_id}`) —
  это sub-stage C (= P0.3).

## Тесты (15/15, suite: 205/205 pass; smoke 33/33)

**CLI (7):** happy, noop, dry-run, no-verify, hash-mismatch=3, missing
bundle=2, json output.

**Endpoint (8):** happy, subdir-форма архива, идемпотентность через
повторный POST, dry-run, bad zip → 400, non-zip filename → 400, zip без
manifest → 400, tampered file → 422.

## Дальше

**Sub-stage C** (= P0.3 ViewModel REST):
- `GET /catalog` — список объектов (краткая ViewModel).
- `GET /objects/{cad}` — полная ViewModel (4 характеристики).
- `GET /lots/{lot_id}` — ViewModel лота.
- `GET /objects/{cad}/graph` — граф связей.
- `GET /bundles/{id}/download?fmt=` — экспорт обратно в Bundle (+ KMZ-регистрация).

Контракт ответа — `contracts/api/viewmodel.schema.json` (4 секции: physical /
ownership / geo / temporal).

## Связи
- `contracts/api/openapi.yaml::/bundles/import`
- `contracts/bundle/BUNDLE_SPEC.md`
- `docs/specs/SPEC_backend.md` §P0.2
- `obsidian/Architecture/p0-bundle-importer.md` (объединённый снимок A+B)
