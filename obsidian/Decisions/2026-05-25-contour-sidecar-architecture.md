# ADR — Sidecar `_data/contours.json` как источник истины для геометрии объектов

- **Date:** 2026-05-25
- **Status:** proposed
- **Authors:** parser-team
- **Related:** parser/scripts/01_parsing_nspd_v8.py (v8.5); 07_init_project_v2 (GOLDEN_PATH); CORRESPONDENCE 022/023

## Context

После v8.x `01_parsing_nspd_v8.py` извлекает `info["Контур"]` (5-уровневый fallback). Остальные 6 скриптов pipeline (`03_enrich`, `04_nspd_graph`, `052_make_structure`, `08_build_kmz`, `06_photo_report`, `viewer/index.html`) контуры **не используют**. Цели:

1. **Идемпотентное обогащение** объектов недвижимости контурами между запусками парсера (без потерь точных WFS-результатов из-за повторного запуска с худшим источником).
2. **Графовое представление** — узлы ЗУ/ОКС в Cytoscape с упрощёнными силуэтами вместо unified square/diamond.
3. **Стандартизированный layout** в `project_root/_data/` для будущего `*_make_reports_*`.

## Decision

### 1. Source of truth — `_data/contours.json`

Единый sidecar в проекте, рядом с `structure.json` / `documents.json` / `graph_node_index.json`. Содержит **полный** GeoJSON + локальные метры + метаданные источника. Создаётся 07_init_project как пустой, наполняется `01b_ingest_contours.py`.

### 2. Schema v1.0

```json
{
  "schema_version": "1.0",
  "ingested_at": "2026-05-25T17:54:27Z",
  "objects": {
    "23:50:0301004:25": {
      "источник": "wfs|pkk|ol_state|screenshot_cv|manual",
      "тип": "Polygon|MultiPolygon",
      "полигонов": 1,
      "колец_всего": 1,
      "площадь_заявленная_кв_м": 57000.0,
      "площадь_вычисленная_кв_м": 57841.72,
      "коэф_коррекции_масштаба": 1.0,
      "центроид": {"lon": 33.5, "lat": 44.4} | {"px_x": 635.2, "px_y": 412.7},
      "geojson": { "type": "Polygon", "coordinates": [...] } | null,
      "полигоны": [
        { "outer": [{"dx": 1.234, "dy": -5.678}, ...], "holes": [[...], ...] }
      ],
      "локальные_метры": [[...], ...],
      "scale_bar_px": 65,
      "scale_bar_m": 10,
      "м_на_пиксель": 0.1538,
      "алгоритм_версия": "v8.5",
      "_ingested_at": "2026-05-25T17:54:27Z",
      "_source_file": "session_export_20260525_175350.json"
    }
  }
}
```

### 3. Приоритет источников (для merge при повторном ingest)

```
manual         > 1000   ←  ручная правка через viewer (зарезервировано)
wfs            >  800   ←  WFS API НСПД, чистый WGS84
pkk            >  700   ←  PKK Rosreestr API
ol_state       >  500   ←  OpenLayers map state (редко срабатывает)
screenshot_cv  >  300   ←  CV-fallback, локальные метры (без WGS84)
network_capture можно отдельно: 600 (зависит от endpoint'a)
```

**Правило:** при ingest для cn новой записи:
- если `cn` отсутствует → добавляем;
- если новый priority > старый → обновляем;
- если priority равны и новая `алгоритм_версия` старше или равна → обновляем (свежесть);
- иначе сохраняем существующее, пишем skipped в ingest log.

Это гарантирует, что повторный запуск парсера с худшим источником (например, при отсутствии интернета у NSPD WFS, остался только screenshot_cv) **не затрёт** ранее накопленный wfs-результат.

### 4. Summary в downstream (structure.json, enriched.json)

Reference-only, без дублирования geojson:

```json
{
  "cadastre_objects": {
    "23:50:0301004:25": {
      ...,
      "_contour": {
        "имеется": true,
        "источник": "wfs",
        "тип": "Polygon",
        "площадь_кв_м": 57841.72,
        "центроид": {"lon": 33.5, "lat": 44.4}
      }
    }
  }
}
```

Downstream-скриптам **достаточно summary** для логики «есть/нет контур, какого качества». Полный geojson читается из `contours.json` только в финальных рендерах (04 → graph node shape, 08 → KML Polygon).

### 5. Cytoscape node shape

Для каждого ЗУ/ОКС/сооружения с `_contour.имеется == true`:

1. Загрузить `contours.json[cn].полигоны[0].outer` (массив `{dx, dy}` в локальных метрах).
2. Если `>32` вершин → Douglas-Peucker simplify с увеличением tolerance до тех пор пока ≤32. Если MultiPolygon → берём polygon с наибольшей outer-площадью.
3. Нормализовать в bbox `[-1, +1]` (для Cytoscape `shape-polygon-points`).
4. Cytoscape style:
   ```js
   { selector: 'node[has_contour]', style: {
       shape: 'polygon',
       'shape-polygon-points': '0.5 -1 1 0 0.5 1 -0.5 1 -1 0 -0.5 -1',  // из шага 3
       'background-color': '<по типу>',
       'border-width': 1,
   }}
   ```
5. Если контура нет → fallback на текущие shapes (square/diamond/dot).

### 6. KMZ Polygon

Для каждого объекта в `08_build_kmz_v2_3`:

1. Читать `contours.json[cn]`.
2. Если `источник ∈ {wfs, pkk, ol_state}` (WGS84) → emit `<Polygon><outerBoundaryIs><LinearRing><coordinates>lon,lat,0 lon,lat,0 ...</coordinates>` + holes через `<innerBoundaryIs>`. MultiPolygon → `<MultiGeometry><Polygon>×N</Polygon></MultiGeometry>`.
3. Если `источник == screenshot_cv` (без WGS84) → существующий Point-placemark (центроид через NSPD search или адресный геокодинг) + `<ExtendedData>` с **полными локальными метрами + площадью + scale_bar метаданными**, для последующей ручной привязки в viewer.

### 7. Идемпотентность

Только `_data/contours.json` имеет «append/upgrade-only» семантику. Остальные artifact'ы (structure.json, enriched.json, graph.html, project.kmz) пересоздаются каждый запуск детерминированно из контуров + входных данных.

## Pipeline (итоговый)

```
07_init_project_v2.1   → _data/{contours.json: пустой скелет, structure.json: пустой}
01_parsing_nspd_v8.5   → session_export_*.json + per-object JSON c info["Контур"]
01b_ingest_contours    → _data/contours.json (idempotent upgrade-merge)
052_make_structure_v2_3 → _data/structure.json (cadastre_objects[cn]._contour summary)
03_enrich_v18          → enriched.json (с флагом _contour)
04_nspd_graph_v15      → html/graph.html (Cytoscape polygon shapes ЗУ/ОКС)
08_build_kmz_v2_3      → kmz-kml/project.kmz (KML Polygon/Point+ExtendedData)
06_photo_report_v3+    → DOCX (без изменений — контуры не нужны)
viewer/index.html       → graph node polygon shapes (отложено, viewer-team занят)
```

## Consequences

**+ Преимущества:**
- Один файл `contours.json` — легко версионировать, легко diff'ать, легко удалять/перезагружать.
- Downstream-скрипты не дублируют тяжёлый geojson.
- Идемпотентность гарантирует что хорошие WFS-результаты не теряются между прогонами.
- Cytoscape polygon shape работает на ≤32 вершин — все ЗУ/здания подходят после simplify.
- KMZ KML Polygon — стандарт OGC, открывается в Google Earth, QGIS, любой GIS-софт.

**− Компромиссы:**
- Дополнительный шаг (01b) между парсингом и structure-building.
- 052/03 теперь зависят от `contours.json` (если его нет — fallback на нет-контура, ОК).
- 08 KMZ файлы будут больше из-за полигонов (минорно, KML текстовый и сжимается).

**Откат:**
- Удалить `_data/contours.json` → 052/03/04/08 фолбэк на нет-контурное поведение.
- Старые версии v2_2/v14/v17/v2_2 сохранены рядом — переключение тривиально.

## Implementation steps

1. **Step 1 (этот ADR):** `01b_ingest_contours.py` + unit-tests + ADR + Changelog. (~ 1 PR)
2. **Step 2:** patch `07_init_project_v2` → docstring + создание пустого `contours.json`.
3. **Step 3:** `052_make_structure_v2_3` (новый файл) — читает contours.json, эмитит summary.
4. **Step 4:** `03_enrich_v18` (новый файл) — то же.
5. **Step 5:** `04_nspd_graph_v15` (новый файл) — Cytoscape polygon shapes.
6. **Step 6:** `08_build_kmz_v2_3` (новый файл) — KML Polygon + ExtendedData.

Каждый шаг — отдельный коммит с боевым прогоном перед следующим.
