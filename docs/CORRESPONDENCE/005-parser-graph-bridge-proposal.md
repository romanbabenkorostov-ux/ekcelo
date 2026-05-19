# 005 — S5: мост маркер→узел графа (`graph_node_id` + protocol pre-selection)

- **From:** parser
- **To:** viewer
- **Date:** 2026-05-19
- **Re:** S4 закрыт (main `8dd9f80`, PR #11); `CONTRACT_KMZ §10` 2.10.2; цикл S5
- **Status:** open — запрос COMMENT-аппрува на §5/§6 контракта 2.11.0

## Контекст

S1→S4 закрыты. Контракт на 2.10.2, оба пайплайна синхронизованы, `graph.html`
лежит в KMZ и рендерится viewer'ом в `<iframe sandbox="allow-scripts">` как
вкладка «🕸 Граф» (`viewer/index.html:1238`, `:6034`). Сейчас связь между
маркером на карте и узлом графа существует только визуально — пользователь не
может из инфо-карточки маркера «провалиться в права». Аналогично для левой
панели (`renderMarksList`, `:6331`).

Предлагаем добавить мост: в `<ExtendedData>` каждого «правового» Placemark'а
эмитим `graph_node_id` (opaque-string, точно равный `id` узла в `graph.html`);
viewer открывает overlay-iframe графа и передаёт nodeId через `postMessage`,
граф выделяет узел и центрирует viewport.

## Что меняется в контракте — bump 2.10.2 → **2.11.0** (MINOR)

Аддитивно, обратно-совместимо. Старый viewer (2.10.x) игнорирует новое поле,
старый парсер (2.10.x) генерит KMZ без поля — оба сценария работают.

### §5 — 4 новых пункта (полный текст в PR `shared/contract-kmz-2.11.0`)

1. `<ExtendedData>/graph_node_id` (string, опционально) — для всех Placemark
   из `cad_{zu,oks,room,str,ons,bu,eq,ben}_*` + `photoPin_*`. Значение —
   opaque для viewer'а. Для `photoPin_*` = кад.№ родителя. Для `cad_exp_*` —
   зарезервировано (сейчас не эмитим).
2. `graph.html` поддерживает pre-selection через `postMessage` (тип
   `ekcelo.graph.select`, поле `nodeId`) **и** `location.hash = '#node=<id>'`.
3. `graph.html` несёт `<meta name="ekcelo-graph-protocol" content="1">` в `<head>`.
4. `kml_schema_version` в `<Document>` поднимается `2.0 → 2.1` (MINOR wire-bump).

### §6 — 5 новых чек-боксов

Cross-match инвариант (каждый `graph_node_id` ⇒ существует узел в графе),
наличие meta-тега, наличие listener'ов, `kml_schema_version=2.1`.

## Протокол виёр

Viewer-side snippet (для `_renderObjectCard` + новый `#graph-overlay`):

```js
window._openGraphFor = function(nodeId){
  if(!nodeId || !_kmzGraphHtml) return;
  const ov = document.getElementById('graph-overlay');
  const fr = document.getElementById('graph-overlay-frame');
  fr.onload = () => {
    try { fr.contentWindow.postMessage({type:'ekcelo.graph.select', nodeId}, '*'); } catch(e){}
  };
  fr.srcdoc = _kmzGraphHtml;
  ov.classList.add('open');
};
```

Граф-side snippet (вставляется парсером в `04_nspd_graph_v14.py:render_html()`):

```js
(function(){
  var pending = null, ready = false;
  function apply(id){
    if(!id) return;
    if(!ready){ pending = id; return; }
    try{ network.selectNodes([id]); network.focus(id, {scale:1.2, animation:true}); }catch(e){}
  }
  try{
    var m = (location.hash || '').match(/(?:^#|&)node=([^&]+)/);
    if(m) pending = decodeURIComponent(m[1]);
  }catch(e){}
  window.addEventListener('message', function(ev){
    var d = ev && ev.data; if(!d || d.type !== 'ekcelo.graph.select') return;
    apply(String(d.nodeId || ''));
  });
  network.once('stabilizationIterationsDone', function(){
    ready = true; if(pending){ var p = pending; pending = null; apply(p); }
  });
})();
```

## Реализация в трёх PR

| PR | Зона | Содержание |
|---|---|---|
| PR-A `shared/contract-kmz-2.11.0` | spec (joint) | этот пост + правки §5/§6/§10 контракта |
| PR-B `parser/graph-node-id-emit` | parser | `04_nspd_graph`: IIFE-listener + meta + sidecar `graph_node_index.json`; `07_init_project_v1`: `graph_node_id` в EXIF UserComment JPG-документов и фото; `08_build_kmz_v2`: `graph_node_id` в 5 классах ExtendedData; mini-fixture + 14 тестов (cross-match KMZ↔sidecar, EXIF-резолв 07, idempotency) |
| PR-C `viewer/graph-preselect-overlay` | viewer | DOM `#graph-overlay`, JS `_openGraphFor`/`_closeGraphOverlay`, кнопка 🕸 в `_renderObjectCard` + `renderMarksList`, ESC-handler |

Порядок мержа: A first (joint COMMENT-аппрув обеих команд), затем B и C
параллельно (рекомендуем C после B для ручного теста на свежей mini-fixture).

## Дополнение: 07_init_project и EXIF-привязка документов/фото

`pirushin_sosn_rocha_07_init_project_v1.py` (PDF→JPG постранично + сортировка
`Не_распределено/`) в S5 расширен: каждый JPG-документ и каждое JPG-фото несёт
`graph_node_id` в EXIF `UserComment` (JSON-payload). Резолв через тот же
sidecar `_data/graph_node_index.json`, что и 08:

- документ ЕГРН/Свидетельства/Техпаспорт/Техплан → `graph_node_id = cn` (КН-узел);
- ЕГРЮЛ/ЕГРИП → `graph_node_id = legal::inn::<inn>` (или `legal::ogrn::<ogrn>`);
- фото к КН → `graph_node_id = cn`.

Это **parser-internal** поле (не часть wire-формата KMZ — см. §5 информативный
пункт). Wire-инвариант от него не зависит, viewer не обязан читать EXIF JPG.
Но открывает дорогу к UX-сценарию «клик на документ в lightbox → переход на
узел графа» без расширения схемы KMZ.

Тесты `parser/tests/test_graph_node_id.py` покрывают:
`resolve_doc_graph_node_id` (приоритет cad → inn → ogrn, fallback formula),
`load_graph_index` 07 (читает sidecar / graceful empty без файла).

## Что **не** в этой итерации (S6+)

Зафиксировано в плане S5 → секция «Out of scope»:
- **Многоуровневые помещения** (`cad_room_*` на нескольких этажах с Z-привязкой
  ОС к высоте пола конкретного уровня) — требует multi-Placemark на один
  cad_number с разными Z-плоскостями; wire-bump 2.12.0+.
- **Парсеры-ingesters** (ОСВ, ЕГРЮЛ, ЕГРИП) — `enriched.json` уже несёт
  результаты, явное размещение скриптов и тестов вне `parser/scripts/` отложено.
- **Инкрементальная идемпотентность pipeline** при добавлении новых артефактов.

## Запрос аппрува

Прошу viewer COMMENT-review на §5/§6 формулировки в PR `shared/contract-kmz-2.11.0`.
В частности:
1. Подойдёт ли `postMessage` с `{type:'ekcelo.graph.select', nodeId}` —
   или нужна другая семантика (например, `targetOrigin` ограничение)?
2. CSS-класс `#graph-overlay` (z-index — за viewer-team, не wire-инвариант;
   первичная оценка ≈ 9600, выше шапки/меню/yandex-dialog 9500, ниже
   load-progress 9999 и lightbox 10000+; см. ответ viewer-team в посте 006) —
   не конфликтует ли с существующими overlay в viewer'е?
3. Размер opaque-`graph_node_id` (string ≤ 256 chars, ASCII + `:`/`_`/`-`/`/`) —
   ок ли как ограничение или надо явно прописать в §6?
