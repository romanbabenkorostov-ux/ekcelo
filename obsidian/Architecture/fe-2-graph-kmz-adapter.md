# FE-2 — интерактивный граф + kmz→ViewModel адаптер

> Второй frontend под-этап. (1) Интерактивный SVG-граф владения (замена
> текстового из FE-1). (2) `adapters/kmz.ts` — порт KMZ-парсера: ZIP-распаковка
> (fflate) + KML-парсинг (DOMParser) → ViewModel, идентичная api-форме (DoD
> SPEC_frontend). Офлайн-режим: drag-drop KMZ.

## Архитектура (дополнение к FE-1)

```
adapters/
├── api.ts          ← FE-1 (C4 REST)
└── kmz.ts          ← FE-2 (KMZ → ViewModel)
     parseKmzBytes(Uint8Array) → KmzDocument
     parseKmzFile(File)        → KmzDocument   (drag-drop)
     kmzToViewModel(doc, cad)  → ViewModel     (та же форма что api)
     kmzToGraph(doc)           → { nodes, edges }

ui/
├── graph.ts        ← FE-1 текстовый (оставлен как fallback)
└── graph-svg.ts    ← FE-2 интерактивный SVG (используется в main)
```

## kmz→ViewModel адаптер

### Формат KMZ (CONTRACT_KMZ 2.x — от `pirushin_sosn_rocha_08_build_kmz_v2.py`)

KMZ = ZIP с `doc.kml` + `images/*.jpg` + `graph.html` + `_data/documents.json`.

doc.kml: Placemarks сгруппированы в Folders по object_type. Каждый:
```xml
<Placemark>
  <name><![CDATA[cad · address]]></name>
  <description><![CDATA[Кадастровый номер: …; Адрес: …; Этажность: …]]></description>
  <ExtendedData>
    <Data name="object_type"><value>zu|oks|room|bu|eq|ben|photo</value></Data>
    <Data name="cad_number"><value>…</value></Data>
    <Data name="graph_node_id"><value>…</value></Data>   ← = node.id в C4
    <Data name="z_meters_top"><value>12.0</value></Data>
    <Data name="parent_cad"><value>…</value></Data>
  </ExtendedData>
  <Polygon|Point>…<coordinates>lon,lat,z …</coordinates></…>
</Placemark>
```

### Извлечение

- **ZIP**: `fflate.unzipSync` (8KB, без зависимостей).
- **KML**: нативный `DOMParser` (`application/xml`).
- **physical**: object_type (zu→land, oks→building, room→room), address +
  floors из description-полей.
- **geo** (ценность KMZ — api не отдаёт до C3.3): center (centroid polygon
  ИЛИ point), geometry (Polygon/Point GeoJSON-like), z_meters_top, extrude.
- **graph**: узлы из placemarks (id = graph_node_id), рёбра part_of
  (room→building через parent_cad) + belongs_to (eq→bu через bu_id).
- **media.photos**: placemarks object_type=photo для данного cad.

### graph_node_id = node.id (C1 = C4)

Ключевой инвариант SPEC: `graph_node_id` из KMZ (C1) совпадает с `node.id`
из backend graph (C4). Поэтому граф из обоих адаптеров матчится — клик на
узле работает одинаково.

## Интерактивный SVG-граф

`renderGraphSvg`:
- Радиальный layout по слоям: object-узлы в центре, right — кольцом,
  beneficiary — внешним кольцом. Детерминированный (без физики).
- Hover/focus подсвечивает инцидентные рёбра.
- Клик по узлу → `onNodeClick` (в main: навигация на object если id похож на cad).
- a11y: узлы `tabindex=0`, Enter/Space = клик, `<title>` с id.
- Без зависимостей — чистый SVG DOM.

## Офлайн-режим (main.ts)

- Панель режима с drag-drop зоной для `.kmz`.
- Загруженный KMZ держится в памяти (`offlineKmz`).
- При открытии объекта: если cad есть в загруженном KMZ → ViewModel из kmz
  (бейдж «источник: KMZ (офлайн)»), иначе из api (бейдж «источник: API»).
- **Один UI рендерит обе ViewModel** — DoD SPEC_frontend выполнен.

## Тесты

- **50 vitest всего** (29 FE-1 + 21 FE-2):
  - `kmz-adapter.test.ts` (14) — на **реальном** sample KMZ от парсера
    (`tests/fixtures/sample.kmz`): распаковка, геометрия zu/oks, z_meters_top,
    extrude, parent_cad, description-поля, kmzToViewModel (4 характеристики +
    geo + photos), kmzToGraph (узлы/рёбра, object_type→kind), cross-match.
  - `graph-svg.test.ts` (7) — SVG узлы/рёбра, data-id, onNodeClick, классы
    по kind, игнор висячих рёбер, a11y tabindex.
- **TypeScript strict**: `tsc --noEmit` — 0 ошибок.
- **ESLint**: 0 warnings (guard ui ⊀ adapters соблюдён — graph-svg в ui не
  импортирует adapters).
- Backend изолирован — 495 как раньше.

### Кросс-средовая совместимость парсера

KML-парсинг работает в браузере И в happy-dom (тесты), несмотря на quirks
happy-dom:
- CDATA парсится как comment-node (type 8) → `cdataText` собирает текст из
  text(3)/cdata(4)/comment(8).
- `.children` обрывается на namespaced `atom:author` → doc-level extract_date
  ищется глобально через `getElementsByTagName("Data")`.
- tagName в UPPERCASE → все сравнения case-insensitive.
- namespace-агностичный lookup через `getElementsByTagName` (не NS-вариант).

## Зависимости

- `fflate@^0.8` — runtime dependency (ZIP unzip). 8KB, tree-shakeable.

## Что НЕ в FE-2

### FE-3
- **Карта** — Google Earth embed (через KMZ) или Leaflet/MapLibre с
  tile-source. Рендер geo.geometry (Polygon) на карте.
- **3D extrude** — z_meters_top для зданий (KMZ несёт, но рендер карты — FE-3).
- **UI грантов** — таблица `GET /grants/me`, формы делегирования/шеринга (C6).
- **Multi-KMZ timeline** — переключение дат (sample есть multi-extract).

## Связи

- KMZ контракт: `docs/CONTRACT_KMZ.md` (формат doc.kml 2.x).
- Sample: `parser/scripts/dev/multi_extract_sample/*.kmz`.
- ViewModel: `core/viewmodel.ts` (FE-1), `contracts/api/viewmodel.schema.json`.
- Предшественник: `fe-1-ekcelo-site-scaffold.md`.
- Backend graph: `p0-viewmodel.md` (C2 graph endpoint, тот же graph_node_id).
