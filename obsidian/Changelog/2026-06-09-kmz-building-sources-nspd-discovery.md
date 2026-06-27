# 2026-06-09 — KMZ: выбор источника строений (умолч. 2→1→3) + NSPD-обнаружение ОКС

Решение заказчика: давать пользователю выбор источника строений, **умолчание 2,1,3**
(NSPD-обнаружение в границах ЗУ → из БД → список КН).

## `geo_nspd.py` — обнаружение ОКС в границах ЗУ (NSPD-WFS)
- `discover_buildings(parcel_polygon)` — WFS BBOX-запрос по габариту ЗУ к слоям ОКС
  (NSPD `api/aeggis/v3/{id}/wfs`, id из v8: 36329/36328/36049) + точный фильтр
  **centroid-in-polygon** (ОКС вне границы участка отбрасываются). GeoJSON в EPSG:4326
  (репроекция не нужна).
- `fetch_geometry`/`fetch_feature` (ПКК) + `parse_wfs_features`/`_geojson_to_kmz_geom` —
  чистые, тестируются офлайн. Сеть закрыта → пусто → объект уходит в спираль.

## `geo_kmz.collect_from_db` — селектор источника строений
`building_sources` (умолч. `("nspd","db","cads")` = порядок 2→1→3):
- **nspd (2)** — `building_discovery(poly)` (обнаружение ОКС в границах ЗУ);
- **db (1)** — из БД по `modes` (linked/agro/geo);
- **cads (3)** — `extra_building_cads` (геометрия по КН из NSPD/БД).
Дедуп по КН; объекты без геометрии → точки по спирали.

## CLI
`egrn-parser kmz --parcels … --db … --out … [--objects linked,agro,geo]
[--buildings nspd,db,cads] [--building-cads "КН,КН"] [--nspd]`.
Обнаружение (источник 2) активно при `--nspd` (нужна сеть).

## Тесты
- `test_geo_nspd.py` (+2): парс WFS-features, `discover_buildings` фильтрует ОКС вне ЗУ.
- `test_geo_kmz.py` (+1): источники nspd+db+cads комбинируются. **15 passed** (geo).

## ⚠ Проверка на сети заказчика
NSPD-WFS BBOX-запрос реализован по рабочему паттерну v8, но **в среде сеть к NSPD
закрыта** — реальное обнаружение проверяется на машине заказчика
(`python -m egrn_parser kmz … --nspd`). Если структура ответа NSPD отличается —
поправлю `parse_wfs_features`/`_wfs_get` по факту.

## Файлы
- `parser/egrn_parser/geo_nspd.py` (WFS discovery), `geo_kmz.py` (building_sources),
  `cli.py` (--buildings/--building-cads), `tests/test_geo_nspd.py`, `tests/test_geo_kmz.py`
