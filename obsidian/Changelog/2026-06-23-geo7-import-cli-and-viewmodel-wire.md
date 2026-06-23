# 2026-06-23 — §7 KML-импортёр + wire-up в ViewModel.geo

## Задача (A+C после §7-baseline)
A) Превратить mock-импортёр KML→§7 в полноценный CLI с тестами.
C) Подключить §7 к `build_object_viewmodel` / `build_lot_viewmodel`, чтобы
бэкенд отдавал `ViewModel.geo.center` + `geometry` без участия фронта.

Полная цепочка: **KML файл → CLI → §7 в SQLite → REST → frontend** теперь
живёт в БД.

## Что сделано

### A — CLI импортёр (`parser/exporters/etp/import_kml_geo_cli.py`)
- Парсит KML и **KMZ** (распаковывает `doc.kml` из zip).
- Один Placemark → одна `geo_entity`:
  - `name` = description до «·», без HTML.
  - `source='kmz'`, `confidence=1.0`.
- Контур → `geo_entity_contour` (GeoJSON Polygon, координаты Yandex `lon,lat`).
- Точка → `geo_entity_point` (lat,lon в правильном порядке).
- Cad-извлечение:
  - 1-й `\d+:\d+:\d+:\d+` → `asset_geo_link` role=primary.
  - Остальные (parent в скобках) → role=reference.
  - Нет cad → geo создаётся **без линка** (для площадок/скважин).
- `valid_from`:
  - default — из имени файла `DD-MM-YYYY` (regex).
  - явно через `--valid-from YYYY-MM-DD`.
- Идемпотентность: skip при существующем (`asset_type`, `asset_id`, `role`,
  `valid_from`).
- `--dry-run` — нулевая запись, только подсчёт.

### A — тесты (`parser/tests/test_import_kml_geo_cli.py`, 13 шт.)
- `description_label` срезает HTML и хвост после «·».
- `extract_valid_from_from_filename` парсит `DD-MM-YYYY`.
- импорт: верный счёт geo/contour/point/primary/reference/unlinked.
- роли `primary` / `reference` ставятся правильно.
- точки сохраняются в `(lat, lon)` (инверсия Yandex `lon,lat` отработана).
- идемпотентность повтора.
- повтор с другой `valid_from` → не skip.
- dry-run → 0 записей.
- CLI smoke: запись в БД через main().
- CLI dry-run, missing-kml, no-date-in-filename → правильные коды возврата.
- KMZ-распаковка (`doc.kml` внутри zip).

### C — wire-up ViewModel (`backend/app/services/viewmodel.py`)
- Добавлен `_load_geo_from_section7(conn, asset_type, asset_id, as_of)`:
  - возвращает пустой `Geo()`, если §7 нет в БД;
  - возвращает пустой `Geo()`, если активу ничего не привязано;
  - иначе — `Geo(center=[lon, lat], geometry=GeoJSON)`.
- Конвенция проекта: `center=[lon, lat]` (MENTAL_CHECK_REPORT.md).
  `GeoSnapshot.point` хранит `(lat, lon)` — инвертируется при сборке Geo.
- `build_object_viewmodel`: `geo=...section7...` вместо stub `Geo()`.
- `build_lot_viewmodel`: то же для `asset_type='lot'`.
- `as_of` пробрасывается в bitemporal lookup.

### C — тесты (`backend/tests/test_viewmodel_geo7.py`, 6 шт.)
- §7 отсутствует → пустой Geo.
- §7 есть, но пуст → пустой Geo.
- §7 заполнен → `center=[lon,lat]` + GeoJSON.
- bitemporal: as_of до valid_from → пустой.
- bitemporal: as_of после → заполненный.
- lot → тоже работает.

## E2E тест (Олимп 15-06-2026)

Запуск `import_kml_geo_cli` на реальном KML (50 placemark):
- 50 `geo_entity`, 48 контуров, 2 точки;
- 22 primary линка, 1 reference (parent в скобках), 28 unlinked;
- `build_object_viewmodel(cad='23:15:0000000:2267', as_of='2026-06-15')`
  → `geo.geometry` Polygon с **85 точками** (поле Шардоне). ✓
- `as_of='2026-05-31'` → `geo` пуст. ✓

## Тесты
- backend: **166 passed**, 1 skipped (+19: 6 viewmodel-geo7).
- orch-web: **297 passed**.
- parser: новые 13 тестов CLI (плюс 33/33 smoke без регрессий).

## Не в scope (отложено)
- Centroid-fallback в `Geo.center`, если у geo_entity только полигон без
  точки. Сейчас `center=None`, фронт может посчитать сам (turf.js).
- Прод-runtime миграция в `parser/egrn_parser/db/migrations.py` — БД ещё
  не в проде.
- post 029-stream parser-team → adopt §7 в их C2 → снять §7-фильтр в
  `test_bridge_guard.py`.
- Centroid-cache как материализованное поле — когда понадобится.

## Канал доставки
zip-handoff.
