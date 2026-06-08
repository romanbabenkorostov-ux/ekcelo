# P0.3 — Bundle reverse-export (sub-stage C3.2)

> Реализация `SPEC_backend.md §P0.3` C3.2 — обратная сторона импорта: реэкспорт
> Bundle (или части) из ekcelo.sqlite §1..§6 + сохранённого KMZ. Завершает
> `GET /bundles/{id}/download?fmt=` (db/json/zip поверх kmz/manifest из C3.1).

## Зачем

После того как C3.1 научился хранить Bundle, C3.2 даёт **реверс**: собрать
Bundle обратно из текущего состояния БД. Это нужно для:
- передачи актуализированного среза другому бэкенду/команде;
- round-trip-проверки целостности (export → import = no-op);
- выдачи нормализованных ViewModel объектов лота (fmt=json).

## Слои

```
┌─ REST ─────────────────────────────────────────────────────┐
│ lot_orchestrator_web/main.py                                │
│   GET /bundles/{bundle_id}/download?fmt=                    │
│     kmz       → FileResponse (C3.1)                         │
│     manifest  → JSONResponse (C3.1)                         │
│     db        → Response application/vnd.sqlite3 (C3.2)     │
│     json      → JSONResponse {bundle_id, objects[]} (C3.2)  │
│     zip       → Response application/zip (C3.2)             │
│     иначе     → 422 ; BundleExportError → 409               │
└───────────┬────────────────────────────────────────────────┘
            │
┌─ Service (export) ─────────────────────────────────────────┐
│ backend/app/services/bundle_export.py                       │
│   export_bundle_db(target_db, record)   → bytes (sqlite)    │
│   export_bundle_json(target_db, record) → dict              │
│   export_bundle_zip(target_db, record)  → bytes (zip)       │
└───────────┬────────────────────────────────────────────────┘
            ▼
        target_db (§1..§6)  +  BundleRecord (C3.1 sidecar)
```

## Поведение

### fmt=db — sqlite-срез

Из `manifest.objects[]` (список cad) собирается новая sqlite-БД с §1..§6:
- `objects` — строки по cad из манифеста. Если хоть один cad отсутствует в
  целевой БД → `BundleExportError` (→ 409).
- `rights` — права этих объектов; собираются ИНН правообладателей.
- `entity_registry` — только эти ИНН (чужие правообладатели НЕ попадают).
- `extracts`, `object_restrictions`, `object_etp_profile` — по тем же cad.

Срез детерминирован по порядку (ORDER BY), но НЕ байт-идентичен исходному
db.sqlite (sqlite-rowid/служебные страницы отличаются) — это by design.

### fmt=json — ViewModel объектов

`{bundle_id, kind, primary_cad_number, objects: [ViewModel...]}`. Каждый
объект — через `build_object_viewmodel` (C1). Если объект исчез из БД →
`BundleExportError` (409).

### fmt=zip — полный Bundle

`manifest.json + db.sqlite + project.kmz` (KMZ только если сохранён в C3.1).
Манифест берётся из `record.manifest_json`, но его `files[]` ПЕРЕЗАПИСЫВАЕТСЯ
свежими sha256/bytes реально упакованных файлов. KMZ-секция добавляется
только при наличии файла.

### Round-trip контракт (SPEC §P0.3)

```
export(zip) → распаковать → import_bundle(verify_hashes=True) → is_noop == True
```

Идемпотентность держится НЕ на байт-идентичности (sqlite-срез отличается от
оригинала побайтно), а на том, что повторный import не меняет ни одной целевой
строки: content-hash объектов совпадает, INSERT-OR-SKIP прав/сущностей не
находит новых. Проверяется тестом
`test_export_zip_round_trip_import_is_noop` (service) и
`test_download_zip_round_trips_to_noop` (endpoint, через HTTP).

## Коды ответов

| Ситуация | Код |
|---|---|
| Успех (db/json/zip) | `200` |
| Неизвестный fmt | `422` |
| bundle_id не найден | `404` |
| Объект манифеста исчез из БД / пустой objects[] (`BundleExportError`) | `409` |
| `bundles_dir`/`ekcelo_db` не сконфигурирован | `503` |

## Что НЕ в этом подэтапе

- **C3.3** — materialization `geo` (центр/геометрия из KMZ в `objects.geo_*`).
  Зависит от parser-team. До неё `geo` в fmt=json остаётся stub.
- **C4 (отдельный трек)** — S3-выгрузка (signed URL 302) вместо потока файла.
- Срез `lots`/`lot_items` для kind=lot bundle — текущий экспорт кладёт только
  §1..§5 + §6-ЭТП объектов. Lot-уровневые таблицы реэкспортируются по членам
  (objects[]), сама запись лота — кандидат на C3.3+ при необходимости.

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `backend/app/services/bundle_export.py` | ~290 | export_bundle_db/json/zip |
| `backend/tests/test_bundle_export.py` | ~250 | 12 service-тестов (вкл. round-trip) |
| `lot_orchestrator_web/main.py` | ~+45 | download-эндпоинт: db/json/zip ветки |
| `lot_orchestrator_web/tests/test_bundle_export_endpoint.py` | ~210 | 6 endpoint-тестов |
| `lot_orchestrator_web/tests/test_bundle_storage_endpoint.py` | ~±5 | обновлён тест fmt=db (501→200) |

**Тесты:** 18 export (12 + 6); полный suite в sandbox **286 pass**
(191 baseline + 28 C1 + 24 C2 + 25 C3.1 + 18 C3.2).

Покрытие:
- export_db: валидный sqlite, исключение чужих объектов/ИНН, related-строки
  (rights/extracts/restrictions/etp), ошибка на missing object, ошибка на
  пустой objects[].
- export_json: ViewModel'и, характеристики, ошибка на missing.
- export_zip: manifest+db, KMZ при наличии, свежие хеши манифеста, round-trip
  import = no-op.
- endpoint: db (sqlite content-type + срез), json, zip (3 файла + KMZ
  content), zip round-trip через HTTP, 422 bogus, 404 unknown.

## Связи

- Контракт: `contracts/api/openapi.yaml::/bundles/{id}/download`
  (302 в спеке для S3; локально — поток файла, «или поток файла»).
- Спека: `docs/specs/SPEC_backend.md` §P0.3 (round-trip требование).
- Предшественники: `p0-bundle-storage.md` (C3.1), `p0-bundle-importer.md`
  (import — обратная сторона round-trip), `p0-viewmodel.md` (C1 для fmt=json).
