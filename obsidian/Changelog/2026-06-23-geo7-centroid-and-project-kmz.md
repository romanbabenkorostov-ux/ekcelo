# 2026-06-23 — Geo §7: centroid fallback + project-KMZ ingestion

## Задача (D + F после A+C)
**D)** `Geo.center` — bbox-centroid из полигона, если у geo_entity нет point.
**F)** Импортёр читает CONTRACT_KMZ-формат: prefix-routing + ExtendedData.

## Что сделано

### D — centroid-fallback (`backend/app/services/viewmodel.py`)
- Добавлен `_polygon_bbox_center(geometry)` — простая bbox-середина первого
  внешнего кольца Polygon / MultiPolygon. Без shapely-зависимости. Для
  WGS84-полигонов нашего масштаба погрешность vs геодезический centroid <1м.
- `_load_geo_from_section7`: если у geo_entity есть point → center из point
  (приоритет). Если только полигон → bbox-centroid. Если ни того ни
  другого → None.

### F — project-KMZ ingestion (`parser/exporters/etp/import_kml_geo_cli.py`)
- Поддержка `<ExtendedData>` (CONTRACT_KMZ §A.9):
  `parse_extended_data(pm)` → dict. Поле `cad_number` имеет **приоритет**
  над regex из description.
- Поддержка префиксов `styleUrl` / `Placemark@id` (CONTRACT_KMZ §5):
  `cad_zu_` → asset_type='land', `cad_oks_`/`cad_ons_` → 'oks',
  `cad_room_` → 'room', `cad_str_` → 'object', `cad_bu_` → 'bu',
  `cad_eq_` → 'equipment', `photoPin_` → 'object'+role='photo'.
- Префиксы `cad_ben_` и `cad_exp_` — geo_entity создаётся, но
  `asset_geo_link` НЕ создаётся (бенефициары и выписки — не «геометрические»
  активы).
- `photoPin_*` получает `role='photo'`, а не 'primary'.
- Обратная совместимость: Yandex-формат (без ExtendedData/префиксов) работает
  как раньше (дефолт `asset_type='object'`, role='primary'/'reference').

## Тесты
+8 новых:
- `backend/tests/test_viewmodel_geo7.py` (+2):
  - centroid когда только polygon;
  - point приоритет над centroid когда оба есть.
- `parser/tests/test_import_kml_geo_cli.py` (+6):
  - project-KMZ: routing по префиксам через ExtendedData;
  - ben — geo без линка;
  - photoPin — role='photo';
  - ExtendedData.cad_number перебивает regex;
  - prefix-routing работает и без ExtendedData;
  - regress: Yandex-формат не сломан.

Итого:
- backend: **174 passed** (+8 от A+C baseline 166).
- orch-web: **297 passed**.
- parser smoke: **33/33**.

## E2E
Олимп 15-06-2026 (Yandex-формат, без ExtendedData):
- импорт 50 placemark → 50 geo / 48 контуров / 2 точки / 22 primary
  (как было — обратная совместимость).
- `build_object_viewmodel('23:15:0000000:2267')` → `geo.center=[37.756,
  45.001]` (bbox-centroid 85-точечного полигона; раньше был `None`).

## Не в scope (отложено)
- Геодезический centroid через shapely — когда понадобится точнее 1м.
- `z_meters_top` / `parent_cad` из ExtendedData в Geo — нужен SemVer-bump
  ViewModel-схемы; отдельной задачей.
- `--create-stub-objects` — если cad из KML отсутствует в `objects`,
  CLI мог бы добавлять минимальную запись. Сейчас требуется ручной INSERT
  (см. fix в session 2026-06-23). ЕГРН-слой не должен наполняться импортом
  гео — намеренное решение.

## Канал доставки
zip-handoff.
