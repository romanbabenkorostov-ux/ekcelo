# P0.3 — Bundle storage + download (sub-stage C3.1)

> Реализация `SPEC_backend.md §P0.3` C3.1 — sidecar-хранилище импортированных
> Bundle'ов для реверс-выдачи. Контракт C4: `contracts/api/openapi.yaml`
> path `/bundles/{id}/download`. Этот документ — снимок состояния после C3.1.

## Зачем

После идемпотентного импорта Bundle (`POST /bundles/import`) бэкенд должен
уметь отдать его обратно — как для фронта (KMZ для Google Earth), так и для
других бэкендов (полный реверс-экспорт Bundle). C3.1 закрывает **сохранение**
+ **выдачу KMZ/манифеста**; C3.2 добавит реверс-экспорт `fmt={zip,db,json}`.

## Слои

```
┌─ REST ─────────────────────────────────────────────────────┐
│ lot_orchestrator_web/main.py                                │
│   POST /bundles/import                                      │
│     теперь возвращает bundle_id + сохраняет KMZ (если       │
│     bundles_dir сконфигурирован).                           │
│   GET /bundles/{bundle_id}/download?fmt=kmz|manifest        │
│     kmz       → FileResponse сохранённого project.kmz       │
│     manifest  → JSONResponse сохранённого манифеста         │
│     db|json|zip → 501 (C3.2)                                │
│     неизвестный → 422                                       │
└───────────┬────────────────────────────────────────────────┘
            │
┌─ Service (sidecar) ────────────────────────────────────────┐
│ backend/app/services/bundle_storage.py                      │
│   compute_bundle_id(manifest) → sha256 hex                  │
│   ensure_bundles_schema(conn)                               │
│   store_bundle(target_db, bundles_dir, bundle_path, manifest)│
│   get_bundle(target_db, bundles_dir, bundle_id) → Record    │
└───────────┬────────────────────────────────────────────────┘
            ▼
        target_db.bundles (миграция 0002)
        <bundles_dir>/<bundle_id>.kmz
```

## Поведение

### bundle_id

- Детерминирован: sha256 от `manifest.model_dump_json(exclude_none=True)` в
  каноничной форме (`sort_keys=True`, `separators=(',',':')`, без пробелов).
- 64-символьный hex-string. Стабилен между запусками.
- Идемпотентность: повтор `POST /bundles/import` того же манифеста →
  тот же bundle_id → нет дубликата строки в таблице, KMZ не перезаписывается.

### Sidecar схема (миграция 0002)

```sql
CREATE TABLE bundles (
  bundle_id            TEXT PRIMARY KEY,         -- sha256 hex
  bundle_version       TEXT NOT NULL,
  contracts_version    TEXT NOT NULL,
  kmz_contract_version TEXT NOT NULL,
  kind                 TEXT NOT NULL,             -- object | lot
  primary_cad_number   TEXT,
  manifest_json        TEXT NOT NULL,             -- канонический JSON
  kmz_path             TEXT,                      -- имя файла внутри bundles_dir
  kmz_sha256           TEXT,
  kmz_bytes            INTEGER,
  imported_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Миграция применяется автоматически при первом обращении к storage
(`ensure_bundles_schema`, аналогично 0001 в `bundle.py`).

### POST /bundles/import — расширение

После успешного импорта (НЕ dry_run, нет errors/files_failed), если
`bundles_dir` сконфигурирован и `report.manifest is not None`:
1. Вычислить `bundle_id = compute_bundle_id(manifest)`.
2. Скопировать `<bundle_root>/project.kmz` → `<bundles_dir>/<bundle_id>.kmz`
   (если файл уже есть — не перекопирует).
3. INSERT в `bundles` (если такой `bundle_id` ещё не записан).

`bundle_id` возвращается в payload (`null` если storage выключен или
`dry_run`/ошибки).

### GET /bundles/{bundle_id}/download

| `fmt` | Поведение |
|---|---|
| отсутствует/`kmz` | `200` FileResponse, `application/vnd.google-earth.kmz`. `404` если запись не найдена или KMZ-файл пропал с диска. |
| `manifest` | `200` JSONResponse — каноничный манифест. `404` если запись не найдена. |
| `db` \| `json` \| `zip` | `501` — пометка «будет в C3.2». |
| другой | `422`. |

`503` если `bundles_dir` не сконфигурирован.

`target_db` берётся из `ekcelo_db` (env `EKCELO_DB` или `create_app(ekcelo_db=)`).
Если он не сконфигурирован — `503` (не от storage, а от вышестоящего helper'а).

## Конфигурация

- `create_app(ekcelo_db=..., bundles_dir=...)` — явно (тесты).
- ИЛИ env: `EKCELO_DB=...`, `EKCELO_BUNDLES_DIR=...`.
- Если `bundles_dir` не задан — импорт работает, но `bundle_id=null`,
  KMZ не сохраняется, download отдаёт 503.

## Что НЕ в этом подэтапе

Будет в **C3.2**:
- Реверс-экспорт `fmt=zip` — собрать обратно `manifest.json + db.sqlite +
  project.kmz` с round-trip-стабильным sha256 (regenerate из БД §1..§6 +
  ЭТП §6 + сохранённого KMZ).
- `fmt=db` — отдать срез БД для objects из манифеста.
- `fmt=json` — нормализованные ViewModel/CatalogCard объектов из bundle.

Будет в **C3.3** (зависит от parser-команды):
- Materialization `geo` — центр/геометрия из KMZ в `objects.geo_*` или
  sidecar-таблицу `object_geometry`. Требует KMZ-parser → DB пайплайна,
  который пишет parser-team.

Будет в **C4** (отдельный трек):
- S3-выгрузка вместо локальной ФС (signed URL response 302).

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `schema/migrations/0002_bundles.sql` | ~25 | DDL sidecar-таблицы |
| `backend/app/services/bundle_storage.py` | ~230 | compute_bundle_id, ensure_schema, store_bundle, get_bundle |
| `backend/tests/test_bundle_storage.py` | ~210 | 14 service-тестов |
| `lot_orchestrator_web/main.py` | +95 | `bundles_dir` param + import-extension + `+GET /bundles/{id}/download` |
| `lot_orchestrator_web/tests/test_bundle_storage_endpoint.py` | ~230 | 11 endpoint-тестов |

**Тесты:** 25 storage (14 + 11); полный suite в sandbox **268 pass**
(191 baseline + 28 C1 + 24 C2 + 25 C3.1).

Покрытие:
- compute_bundle_id: детерминированность, разные манифесты → разные id, 64-hex.
- ensure_bundles_schema: создаёт таблицу, идемпотентна.
- store_bundle: возвращает id, persists row, копирует KMZ, идемпотентность,
  создаёт bundles_dir, обрабатывает отсутствие KMZ.
- get_bundle: возвращает record, None для unknown/no-table/no-db, kmz_path=None
  если файл потерян.
- endpoint /bundles/import: bundle_id в payload, KMZ записан, dry_run не
  сохраняет, без bundles_dir → bundle_id=null.
- endpoint /bundles/{id}/download: kmz file, default fmt=kmz, manifest JSON,
  404 unknown, 422 bogus fmt, 501 для db/json/zip, 503 без bundles_dir.

## Связи

- Контракт: `contracts/api/openapi.yaml::/bundles/{id}/download` (302 в спеке
  для S3; локально отдаём поток файла — соответствует «или поток файла»).
- Спека: `docs/specs/SPEC_backend.md` §P0.2 + §P0.3.
- Предшественник: `obsidian/Architecture/p0-bundle-importer.md` (импортёр).
- Соседний снимок: `obsidian/Architecture/p0-viewmodel.md` (C1+C2 ViewModel).
- Миграция: `schema/migrations/0002_bundles.sql`.
