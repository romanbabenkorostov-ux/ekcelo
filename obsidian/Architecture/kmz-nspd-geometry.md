# SPEC: KMZ + геометрия из NSPD (ЗУ + ОКС в пределах)

Статус: в работе (контуры ЗУ — готово; геометрия ОКS — резолв по geomId, идёт
подбор рабочего эндпоинта). Модуль: `parser/egrn_parser/geo_nspd_browser.py`,
рендер — `geo_kmz.py`, CLI — `cli.py kmz`.

## Задача
KMZ с 3 ЗУ и объектами (ОКС) в их пределах: есть контур → рисуем контур, нет →
точка по спирали внутри ЗУ. Источник геометрии — **парсинг сайта NSPD** через
браузер (Playwright), т.к. голый HTTP/WFS блокируется анти-ботом (403).

## Открытия по API NSPD (через диагностику сетевых запросов)
1. **Геометрия ЗУ** — `GET /api/geoportal/v2/search/geoportal?query={КН}`
   (тот же эндпоинт, что дёргает строка поиска/лупа). Возвращает FeatureCollection,
   геометрия в **EPSG:3857** → репроекция в WGS84. Работает 3/3.
   - КН в `feature.properties.options.cad_num`; `feature.id`=geomId,
     `feature.properties.category`=categoryId.
2. **Темы поиска** — `GET /api/geoportal/v1/search-theme?pageCode=geoportal` →
   `[(id,name)]`: 1=Объекты недвижимости, 2=Кадастровое деление, 4=АТД,
   5=Зоны и территории, 7=Территориальные зоны, 15=Комплексы объектов.
   Перебор тем в `?thematicSearchId={id}&query=` — на случай, если объект в др. теме.
3. **Список ОКС в пределах ЗУ** —
   `GET /api/geoportal/v1/tab-group-data?tabClass=objectsList&categoryId={cat}&geomId={gid}`
   (cat/gid — от feature ЗУ). Возвращает таблицу КН ОКС (для 23:15:0000000:2267 — 22 шт).
4. **Карточка объекта** кодируется в URL карты как
   `selectedCard={geomId},{categoryId},{КН}`.
   - Здание: `1003499779,36369,23:15:0000000:3189` → **categoryId 36369 = здание**,
     map-layer 36048(ЗУ)/36049/36329.
   - Сооружение: `415708564,36383,90:25:020103:9298` → **categoryId 36383 = сооружение**,
     map-layer **36328**.
   - objectsList на деле — **плоский список КН без geomId**:
     `{"title":"Список объектов","object":[{"title":"Объект недвижимости: ",
     "value":["23:15:…", …]}]}`. Поэтому geomId берём НЕ из objectsList, а из
     `feature.id` ответа geoportal-search по КН ОКС.

## Проблема геометрии ОКС
Текстовый `search/geoportal?query={КН_ОКС}` для геометрии ОКС в `extract_features`
(strict) давал 0 — feature ОКС часто приходит **без geometry** (контур грузится
лениво по geomId). Решение:
1. `_oks_search` берёт feature ОКС даже без геометрии (`require_geometry=False`)
   → из него `feature.id`=geomId, `properties.category`=categoryId.
2. Если у feature есть геометрия — используем сразу.
3. Иначе геометрию грузим **по geomId/categoryId**: `_resolve_geom_by_id` перебирает
   кандидатные эндпоинты (`geoportal/v1|v2/geom/{gid}` и `/{cat}/{gid}`,
   `…?categoryId&geomId`, `…/card/{cat}/{gid}`, WFS featureID); первый с
   feature-геометрией = рабочий. `_probe_geom_by_id` печатает статусы для фиксации.

## Алгоритм (per ЗУ)
1. `goto map?query={КН}&active_layers=…`, закрыть модали.
2. Один раз: `search-theme` → theme_ids (печать).
3. Геометрия ЗУ: `_search_geoportal` (ретраи, перебор тем) → poly (3857→WGS84).
4. ОКС: `objectsList` → `oks_records` = `{cad, geomId, categoryId}`
   (card-тройка `geomId,cat,cad` в строках + per-object поля + `collect_cads`
   для полноты). geomId-проба (диагностика).
5. Геометрия каждого ОКС: `_resolve_geom_by_id` (по geomId) → иначе текст-поиск →
   иначе None. **Polygon → контур, Point → реальная точка, None → спираль.**

## Правила рендера (geo_kmz)
- ЗУ с геометрией → полигон (стиль `parcel`).
- Объект Polygon → контур (`objpoly`); Point → точка (`objpoint`).
- Объект без геометрии → точка по **спирали-филлотаксису** (золотой угол 137.5°,
  `rad=√((i+½)/n)`, `margin=0.45` — кучно у центра ЗУ; архимедова спираль с целым
  числом оборотов вырождалась в линию — исправлено).

## CLI
```
python -m egrn_parser kmz --parcels КН1,КН2,КН3 --db проект.sqlite \
  --out objects.kmz --nspd-headful
```
- `--nspd-headful` — видимый браузер (сам включает браузерный режим NSPD).
- `--nspd-manual` — человек в цикле: по каждому КН ждём Enter, пока пользователь
  жмёт лупу/листает вкладки (фолбэк к перехвату), event-loop не блокируется
  (`run_in_executor`).
- `--nspd-http` — лёгкий urllib (обычно 403).
- Источники строений (`--buildings`, умолч. `nspd,db,cads`), `--building-cads`.
- Печатает абсолютный путь KMZ: `✅ KMZ сохранён: <path>`.

## Открытые вопросы
- Зафиксировать рабочий geomId-эндпоинт геометрии ОКС (по результату пробы).
- Проверить, у всех ли ОКС есть контур в NSPD (часть «ранее учтённых» — без
  геометрии → корректно ложатся по спирали).
