# 2026-06-09 — KMZ: выбор «объектов внутри ЗУ» (а/в/г) + геометрия из NSPD (2в)

Решения заказчика: «объект внутри ЗУ» — выбираемо, умолчание а+в+г; при отсутствии
контура ЗУ — тянуть из NSPD (2в).

## `geo_kmz.collect_from_db` — режимы выбора
`modes` (умолч. `linked,agro,geo`; алиасы а/в/г):
- **linked (а)** — `linked_objects`(located_on) + `building_objects.parent_cad`;
- **agro (в)** — §6-объекты: `agro_parcel` с `land_cad`=ЗУ (насаждения/точки оценки);
- **geo (г)** — объекты с геометрией, чей центроид внутри полигона ЗУ (point-in-ring).
`geometry_fetcher` (2в): если контур ЗУ/объекта не в БД — берётся из NSPD и кэшируется
в `land_contours` (source='nspd').

## `geo_nspd.py` — геометрия по КН из ПКК (HTTP, без Playwright)
- `fetch_geometry(cad, layer=1|5)` — ПКК `api/features/{layer}/{cad}` → GeoJSON WGS84
  (репроекция EPSG:3857→WGS84). Слой 1 — ЗУ, 5 — ОКС/здания.
- Разделение fetch/parse: `parse_pkk_feature`/`_merc_to_wgs` — чистые, тестируются
  офлайн. Сеть закрыта → fetch=None → объект уходит в спираль.

## CLI
`egrn-parser kmz --parcels "КН,КН,КН" --db <бд> --out objects.kmz [--objects linked,agro,geo] [--nspd]`.

## Вывод KMZ по 3 КН задачи
`objects_3_parcels.kmz` — 3 ЗУ (23:15:0000000:2267, 23:15:0303000:1562,
23:15:0303000:1130): контуры строений где есть, остальные — точками по спирали
внутри границ (3 контура + 8 спиральных точек). Геометрия **представительная**
(сеть к NSPD в среде закрыта); реальная — на машине заказчика командой `--nspd`.

## Тесты
- `test_geo_kmz.py` (+2): режимы а/в/г, NSPD-fetch-fallback+кэш.
- `test_geo_nspd.py` (+4): репроекция 3857→WGS84, парс Polygon/MultiPolygon, пусто.
- Всего geo → **12 passed**.

## Файлы
- `parser/egrn_parser/geo_kmz.py` (режимы+fetcher), `geo_nspd.py` (новый),
  `cli.py` (kmz --objects/--nspd), `tests/test_geo_kmz.py`, `tests/test_geo_nspd.py` (новый)
