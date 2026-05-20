# 2026-05-19 — S5: overlay графа + кнопка 🕸 маркер→узел (viewer)

**Что:** реализована viewer-сторона S5 — мост `маркер ↔ узел графа`.
Контракт KMZ 2.10.2 → 2.11.0 (MINOR, аддитивно, обратносовместимо).

## PR-цепочка (в `main`)
- **PR #16** `shared/contract-kmz-2.11.0` — контракт 2.11.0 (parser):
  `<ExtendedData>/graph_node_id` (opaque), protocol pre-selection
  (postMessage `ekcelo.graph.select` + `#node=<id>`-hash), meta
  `ekcelo-graph-protocol`, `kml_schema_version 2.0→2.1`, §6-регекс
  `graph_node_id` `^[A-Za-z0-9_:/-]{1,256}$`. viewer COMMENT-аппрув
  (006).
- **PR #17** `parser/graph-node-id-emit` — `04`/`07`/`08` эмитят
  `graph_node_id`, sidecar `graph_node_index.json`, EXIF
  UserComment.graph_node_id (parser-internal, информативно по §5).
  25 + 17 тестов зелёные.
- **PR #18** `viewer/graph-preselect-overlay` — viewer (домен §7.1):
  - DOM `#graph-overlay` (flex-колонка: верхняя панель `#graph-overlay-bar`
    с кнопкой `✕ закрыть` НАД iframe — структурно без z-index/композит-гонок),
    `<iframe sandbox="allow-scripts">` + srcdoc `_kmzGraphHtml`.
  - JS `_openGraphFor(nodeId)` → postMessage; `_closeGraphOverlay()` →
    `srcdoc='about:blank'` (выгрузка vis-network). ESC + ✕ + focus-на-×
    через `requestAnimationFrame`.
  - Helper `_graphNodeIdOf(m)` — exhaustive multi-path: `m.graphNodeId` →
    `m.pmRef.ext.graph_node_id` → `m.ext.graph_node_id` → fallback по
    `kmlLayers[m.layerIdx].parsedData.placemarks[m.innerIdx].ext` (Source-2)
    → fallback по `cadNum` (Source-1 `matched`). Client-side §6-валидатор.
  - `_gatherMarkers` несёт `graphNodeId` в record (резолв из `matched.ext`
    / `pm.ext`) — устраняет таймингово-структурную асимметрию card↔list.
  - Кнопка 🕸 в `_renderObjectCard` (шапка карточки) и `renderMarksList`
    (видимая пилюля с бордером, `accent2`-цветом, vertical-center).
    Гейт = `graph_node_id` (контракт-инвариант: id ⇒ graph.html в KMZ;
    `_openGraphFor` guard'ит `_kmzGraphHtml`). `photoPin_*`/`cad_exp_*`
    не показывают 🕸 — by design.

## Инварианты соблюдены
- Прод `pro` поведение байт-в-байт прежнее (S4 регрессия не нарушена);
  S5 — аддитив. KMZ 2.10.x → viewer 2.11.x: 🕸 не показывается (отсутствует
  `graph_node_id`). KMZ 2.11.x → viewer 2.10.x: `graph_node_id`
  игнорируется. CSS-шов (`439–468`) и `v2961.html` не тронуты.
- `node --check` инлайн-скрипта чист.
- mini-fixture парсера (`parser/scripts/dev/make_mini_fixture.py`, PR #19):
  9 `graph_node_id`, 0 несоответствий §6-регексу; graph.html-stub имеет
  meta+listener+hash; владелец пройден браузер-smoke (КН/БУ/EQ/БЕН → 🕸 →
  overlay → узел подсвечен зелёным; ✕/Esc закрывают).

## Переписка
`docs/CORRESPONDENCE/005`, `006`, `007` (нумерованный append-only журнал).

## Out of scope (после S5)
- multi-level Z (helper по этажам) — wire-MAJOR, отдельный spec-PR-first
  цикл, отложено.
- viewer-cleanup корня: `worker.js`/`worker_good_work2026-04-26.js`/
  `logic_index_html.md` — обещанный мелкий PR.
- ОКС-карточка: «фотографии в карточке» — отдельная UI-задача (правило
  скрытия требует уточнения владельца).
- mini-fixture стимул: `cad_eq_*` без геометрии — данные парсера, не viewer.
