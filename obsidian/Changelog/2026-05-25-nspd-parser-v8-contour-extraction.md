# 2026-05-25 — parser: NSPD v8 — извлечение контура объекта (гибрид WFS → OL → CV)

**Что:** В standalone-инструмент `parser/scripts/01_parsing_nspd_v8.py` добавлен новый шаг — извлечение векторного контура объекта (полигон/мультиполигон) после парсинга карточки. Гибрид-подход: WFS-API (primary) → DOM/OpenLayers-state (secondary) → screenshot+CV (last-resort fallback).

## Ключевая находка

В `viewer/index.html` уже есть готовая формула WFS-запроса к НСПД (`_tryNSPD`, lines 8333-8356): `https://nspd.gov.ru/api/aeggis/v3/{layer_id}/wfs?REQUEST=GetFeature&TYPENAMES=ms:layer_{layer_id}&CQL_FILTER=cad_num='...'&outputFormat=application/json&SRSNAME=EPSG:4326`. Layer IDs: ЗУ `[36048]`, ОКС `[36329, 36328, 36049]`; поля КН перебираются: `cad_num | KAD_NUM | CAD_NUM | kadnum`. Это даёт чистый GeoJSON Polygon/MultiPolygon в WGS84 напрямую от НСПД без image processing.

## Архитектура (3-уровневый fallback)

### 1) PRIMARY — WFS API (`_fetch_geom_via_wfs`)

`page.evaluate()` с fetch'ем из контекста страницы (корректный Referer, cookies). Перебирает ZU-layers → OKS-layers; XML FILTER → CQL FILTER; 4 варианта имени поля КН. Возвращает GeoJSON в WGS84. Не требует ни screenshot, ни CV, ни scale-bar.

### 2) SECONDARY — OpenLayers map state (`_fetch_geom_via_ol_state`)

Ищет в `window.*` объект с методами `getLayers()` + `getView()` (ol.Map duck-typing). Берёт feature с наибольшим bbox-area из vector-слоёв. Если проекция EPSG:3857 — реprojection в WGS84 (`_reproject_3857_to_wgs84`). NSPD обычно не expose'ит map, но попытка дешёвая (1 evaluate).

### 3) LAST-RESORT — Screenshot + CV (`_extract_contours_from_image`)

Если выше оба не дали результат и установлены `numpy`/`opencv-python`/`Pillow`:
- Скриншот `.ol-viewport canvas` через `page.screenshot(clip=...)`.
- HSV-фильтр фиолетового (`H 130-165, S 60-255, V 80-255`).
- `MORPH_CLOSE` → `findContours(RETR_CCOMP)` — внешние контуры + дырки.
- `approxPolyDP` (epsilon=1.5px) — упрощение до «характерных поворотных точек».
- Scale: `.scale-inner` (DOM) → `(width_px, meters)` — пересчёт пикселей в метры.
- **Коррекция масштаба**: `scale_corrected = scale_raw * sqrt(parsed_area / computed_area)` (per Q-session).
- PNG-превью с подсветкой маски + контурами + центроидом → base64 для отладки.

## Выходная структура `info["Контур"]`

```python
{
  "источник": "wfs" | "ol_state" | "screenshot_cv",
  "тип": "Polygon" | "MultiPolygon",
  "кол-во_колец": int,
  "площадь_заявленная_кв_м": float | None,
  "площадь_вычисленная_кв_м": float,
  "коэф_коррекции_масштаба": float | None,
  "центроид": {"lon": float, "lat": float} | {"px_x": float, "px_y": float},
  "geojson": {...} | None,           # WGS84, если есть georeference
  "локальные_метры": [               # массив колец; первое — внешний контур,
    [{"dx": 1.234, "dy": -5.678}, ...], #   следующие — дырки или доп. полигоны
    ...
  ],
  "scale_bar_px": int | None,
  "scale_bar_m": float | None,
  "м_на_пиксель": float | None,
  "превью_png_b64": str | None,
  "алгоритм_версия": "v8.0"
}
```

Удовлетворяет 4 запрошенным форматам (мультивывод):
- ✅ Локальные метры от центроида (основное по ТЗ) — `локальные_метры[][]` с точностью 0.001 м.
- ✅ GeoJSON WGS84 — для импорта в KMZ без ручного сопоставления.
- ✅ PNG-thumbnail base64 — для верификации в viewer/lightbox.
- ✅ Debug-metadata (scale_bar, м/пиксель, коэф_коррекции).

## Поведение для «Без координат границ»

Парсер v7 уже выставляет `info["Без координат границ"] = True` для объектов без полигона. В `extract_contour()` это — ранний `return None` с info-сообщением «объект без координат границ — пропуск». В `info` поле `Контур` не появляется.

## Конвертация WGS84 → локальные метры

`_lonlat_to_local_meters(lon, lat, lon0, lat0)` — equirectangular от центроида: `dx = (lon - lon0) * 111320 * cos(lat0_rad)`, `dy = (lat - lat0) * 110540`. Точность ±0.1% для объектов до 10 км — избыточна для зданий/ЗУ. Кривизной земли пренебрегаем (per ТЗ).

Центроид — формула планарного полигона на координатах WGS84 (`_ring_centroid_wgs84`), считается по внешнему кольцу первого полигона MultiPolygon.

## Площадь и коррекция

`_ring_area_sqm_local` — Shoelace formula на локальных метрах. Для MultiPolygon: outer ring (+) + holes (−). При наличии `parsed_area` (из `info["Площадь, кв.м"]` и др. ключей AREA_KEYS):
- WFS/OL-state: `коэф_коррекции = parsed/computed` (информативный, не применяется — WFS точен).
- CV-fallback: `scale * sqrt(parsed/computed)` — применяется (compensates pixel quantization + scale-bar parsing error).

## Зависимости

- **Базовые (как v7):** `playwright`.
- **CV-fallback (опционально):** `numpy`, `opencv-python`, `Pillow`. При отсутствии — fallback пропускается с warning, primary/secondary продолжают работать.

## Тестируемость

Не запускали реально — требует браузерной сессии + российского IP для WFS НСПД. Логика unit-тестируема:
- `_lonlat_to_local_meters` — проверяется на известных парах.
- `_ring_centroid_wgs84` — тест на квадрат/треугольник.
- `_ring_area_sqm_local` — тест на квадрат 100×100 → 10000 м².
- `_geojson_to_local_meters` — фикстура GeoJSON Polygon → проверка локальных метров + площади.
- `_reproject_3857_to_wgs84` — точка (4465954.7, 5755474.76) ≈ Тихорецк.

## Файлы

- `parser/scripts/01_parsing_nspd_v8.py` (новый, +1428 строк, AST parses OK).
- Этот changelog.

## Что не вошло (отложено)

- **Unit-tests** для `_lonlat_to_local_meters` / `_ring_*` / `_geojson_to_local_meters` — желательно создать `parser/tests/test_nspd_contour.py` с фикстурами (квадрат, L-shape, MultiPolygon с дыркой) перед production-использованием.
- **Конвертация локальных метров → WGS84 после ручного смещения** — это второй скрипт, согласно ТЗ («не в этом скрипте»). Контракт ввода: `центроид_новый = {lon, lat}` (после ручной привязки в viewer) + `локальные_метры` → выход: GeoJSON в WGS84.
- **Интеграция в `pirushin_sosn_rocha_08_build_kmz_v2.py`** — пока v8 — standalone-инструмент, контуры пишутся в session JSON. Импорт контуров в KMZ — отдельный шаг pipeline.

**Ветка:** `parser/nspd-contour-v8`.
