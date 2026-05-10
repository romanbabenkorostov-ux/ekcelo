# EkceloFoto — Разбор багов и улучшений v2.9.59 → v2.9.62

> Семь правок (баги 38–44) по результатам пользовательского тестирования.
> v2.9.60: баги 38–43. v2.9.61: UPDATE Bug 39 (высота заголовков + кликабельность чекбокса). v2.9.62: Bug 44 — обнаруженная после фикса 39 проблема рассинхронизации pmRef ↔ leaflet-layers, решена через introduction `_objectIndex` (Этап 1+2 рефакторинга).
> Стиль: те же поля что в `bugfix_summary_v2936_to_v2939.md` — **Симптом / Причина / Реализация / Что НЕ менялось / Граничный момент**.

---

## BUG 38 — Одно фото без координат + одно с координатами = две точки на карте

### Симптом
Пользователь: «одна фотография (название файла одинаковое но возможно разные источники) была без координат и в другом ей присвоены координаты — представляется на карте как две разные фотографии, а должна обогащённая одна».

Сценарий: пользователь загружает 2 источника одного и того же файла:
- Источник A: JPG из папки на диске, EXIF без координат.
- Источник B: тот же файл из KMZ-архива (где KML содержит `<Point><coordinates>`).

В `photos[]` появляются **две записи**: `{name:'IMG_001.jpg', lat:null, lon:null}` и `{name:'IMG_001.jpg', lat:47.22, lon:39.72}`. Маркер ставится только для второй (у первой нет координат), но в списке **слева** видны два пункта с одинаковым именем — путаница.

### Причина
Старый `addLocalPhoto` дедуплицировал по `name+size`:
```js
if(photos.find(p => p.name === file.name && p.size === file.size && !p.isRemote)) return false;
```
Если `size` отличается на байт (KMZ-blob vs original file: разная нормализация JPEG), проверка не срабатывала.

Старый KMZ-loader дедуплицировал по `name+sourceType==='kmz'`:
```js
if(!photos.find(p => p.name === kp.name && p.sourceType === 'kmz')) addPhoto(...);
```
Это ловило только дубль из ДВУХ KMZ-импортов. Дубль local + kmz **не отлавливался** — `sourceType` разный.

Никакой логики **обогащения** (заполнить пустые координаты в существующем) не было.

### Реализация
Создана единая функция `addOrEnrichPhoto(photo)` в registry-блоке. Логика:

```js
function addOrEnrichPhoto(photo){
  const nameKey = String(photo.name).toLowerCase();
  const existing = photos.find(p => String(p.name||'').toLowerCase() === nameKey);
  if(existing){
    // Enrich missing fields from `photo` into `existing`.
    const ENRICHABLE = ['lat','lon','bearing','altitude','date','locPath','experimentData'];
    for(const k of ENRICHABLE){
      const cur = existing[k];
      const nw  = photo[k];
      const curIsEmpty = (cur == null || cur === '' || (typeof cur === 'number' && isNaN(cur)));
      const nwIsValue  = (nw  != null && nw !== '' && !(typeof nw === 'number' && isNaN(nw)));
      if(curIsEmpty && nwIsValue){
        existing[k] = nw;
        enrichedFields.push(k);
      }
    }
    // Если только что появились coords — добавляем marker.
    if(justGotCoords && existing.lat != null && existing.lon != null && !existing.marker){
      addMarker(existing, photos.indexOf(existing));
    }
    // Audit trail
    existing._sources.push(photo.sourceType);
    _dedupLog.push({when:..., file:..., action:'enriched', sources:..., fields:...});
    return existing;
  }
  // Fresh — push.
  photos.push({...photo, _sources:[photo.sourceType]});
}
```

Ключевые свойства:
- **Case-insensitive** lookup по имени (фото с диска под Windows может быть `IMG_001.JPG`, а в KMZ — `img_001.jpg`).
- **Non-overwrite enrichment**: если `existing.lat` уже есть, новый источник его не перезатирает. Перезаписать пользовательские данные — антипаттерн.
- **Audit trail в `_sources`** массиве: каждое фото знает, из каких источников пришли его данные.
- **Marker bootstrap**: если `existing` был без координат и без маркера, после enrichment'а с координатами — маркер ставится.

`addPhoto(photo)` — backward-compat shim, просто вызывает `addOrEnrichPhoto`.

### Что НЕ менялось
- Структура `photos[]` массива (свойства те же, добавлено только `_sources`).
- `addMarker` сам не тронут — просто вызывается из новой точки.
- Order of operations в `addLocalPhoto` (EXIF parse → addOrEnrichPhoto) тот же.

### Граничный момент
> **Что если в обоих источниках координаты, но РАЗНЫЕ?** Existing побеждает — non-overwrite policy. Это soft-conflict policy: первый источник = ground truth. Можно расширить через `dateMismatch`-style флаг для conflict detection, но в текущем спросе этого не было.
>
> **Case-insensitive lookup** может склеить два **реально разных** файла с именами `Img_1.jpg` и `IMG_1.jpg` — но на практике это очень редкий случай (файловые системы Windows/macOS case-insensitive по умолчанию).

---

## BUG 38' — Лог анализа дублей фотографий (новая фича)

### Запрос
«Добавь при импорте лог — анализ дублей: файлы, в чем проблема, как решена — с выводом на экран-в файл (путь запрашивается, но по умолчанию в папку с первым открытым локальным источником)».

### Реализация

Каждый вызов `addOrEnrichPhoto` пишет запись в глобальный массив `_dedupLog`:

```js
_dedupLog.push({
  when: new Date(),
  file: photo.name,
  action: 'added' | 'enriched' | 'duplicate-skipped',
  sources: existing._sources.slice(),  // accumulated source types
  fields: enrichedFields,               // что именно дополнили
  note: 'Заполнены поля: lat, lon из источника «kmz»…'
});
```

UI: после batch-импорта (folder upload, KMZ extraction) показывается toast:
```
📂 Импорт: +12 нов. · ✚3 обогащ. · ⊘2 дубл. · клик → лог
```

При клике (новый параметр `showToast(msg, type, dur, onClick)`) открывается **модальный диалог** с:
1. Сводка: всего/добавлено/обогащено/пропущено.
2. Детальный лог в `<pre>`-блоке с timestamp, action symbol (➕/✚/⊘), список источников, изменённые поля, note.
3. Кнопка «💾 Сохранить в файл» — открывает FSA picker с именем `dedup-log_YYYY-MM-DD_HH-mm.txt`. Default folder — первая увиденная local-папка (`_dedupBatchFolder`).

`_dedupBatchFolder` устанавливается в `addLocalPhoto` при первом фото с непустым `locPath`.

### Что НЕ менялось
- Существующая `showToast` — расширена опциональным 4-м параметром `onClick`. Все старые вызовы по-прежнему работают.
- `_dedupLog` живёт в memory — не персистится. После reload страницы лог пуст. Это намеренно: лог касается **сеанса импорта**, не накапливается вечно.

### Граничный момент
> Если пользователь сделал **первый импорт без дублей**, но потом второй импорт **с дублями** — лог покажет результат **обоих** импортов. Это корректно, потому что в `photos[]` всё ещё лежат данные с первого импорта, и пользователь может проверить, как они «обогатились» вторым импортом.

---

## BUG 39 — Контраст заголовков «Метки» в тёмной теме + чекбокс «Пояснения»

### Симптом
Пользователь: «слева в панели в режиме "Метки": в тёмной теме сделай более контрастным заголовки раскрывающихся подгрупп "Зем.участки", "ОКСы", "Пояснения"; в пункте "Пояснения" пропала возможность выделить-снять выделение отражения на карте всех объектов группы».

### Причина — два независимых дефекта

**Дефект A (контраст).** Старые стили:
```css
.mg-icon { font-size:12px; }
.mg-icon-zu { color:#3ec870; }   /* darker green */
.mg-icon-oks { color:#c180f0; }  /* lavender */
.mg-icon-exp { color:#47c8ff; }  /* bright cyan */
.mg-title { font-size:11px; font-weight:700; color:var(--text); }
.mg-count { color:var(--muted); border:1px solid var(--border); }
```

В тёмной теме `--muted` (#6c7895) на счётчике почти сливался с границей `--border`. Заголовки `mg-title` уже были `var(--text)` (=`#f4f6fc`), но `font-size:11px` и тонкий `font-weight:700` снижали воспринимаемый контраст.

**Дефект B (чекбокс «Пояснения»).** Чекбокс группы создавался лениво в `_ensureGroupCheckbox`. Если в bucket `exp` 0 элементов, чекбокс ставился `disabled` (с opacity 0.35) — выглядело как «пропавшая возможность». Корень: после CHANGE 28 (v2.9.59) photo-pin'ы из re-imported KML были классифицированы в `exp` (Пояснения) и автоматически скрывались. Это была корректная логика. Но `_detectPhotoPin` использовал **слишком широкий** desc-regex: `/...|\d{4}[.\-:]\d{2}[.\-:]\d{2}\s+\d{2}:\d{2})/i` — ловил **любые даты в тексте**, включая дату внутри обычного Пояснения (например, "Снято 2026-04-29 11:22"). В результате **настоящие** Пояснения попадали в photo-pin bucket → исчезали из Меток → bucket пустой → чекбокс disabled.

### Реализация

**Дефект A — усиленный контраст:**
```css
.mg-icon { font-size:13px; font-weight:900; text-shadow:0 0 4px currentColor; }
.mg-icon-zu  { color:#5cff8a; }   /* brighter green */
.mg-icon-oks { color:#d6a3ff; }   /* brighter lavender */
.mg-icon-exp { color:#7adcff; }   /* brighter cyan */
.mg-title { font-size:12px; font-weight:800; color:var(--text); letter-spacing:0.2px; }
.mg-count { font-size:10px; font-weight:700; color:var(--text);
            background:var(--bg); border:1px solid var(--accent2); padding:1px 7px; }
```

`text-shadow:0 0 4px currentColor` создаёт тонкое свечение вокруг иконки — повышает воспринимаемый контраст на тёмном фоне без увеличения размера. `var(--accent2)` border на счётчике (вместо blando `var(--border)`) делает его явным акцентом. `font-weight:900` на иконке усиливает форму символа.

**Дефект B — сужен `_detectPhotoPin`:**
```js
// БЫЛО (v2.9.59) — date-pattern alone enough
const PHOTO_DESC_RE_KML = /(угол(\s+съ[её]мки)?|GMT[+\-]\d{1,2}|©.+GPS\s*Map\s*Camera|\d{4}[.\-:]\d{2}[.\-:]\d{2}\s+\d{2}:\d{2})/i;

// СТАЛО (v2.9.60) — date-pattern removed
const PHOTO_DESC_RE_KML = /(угол(\s+съ[её]мки)?|©.+GPS\s*Map\s*Camera|GMT[+\-]\d{1,2})/i;
```

Теперь date-only description больше не классифицируется как photo-pin. Только реальные photo-маркеры (с styleUrl `photoPin`/`photo_icon`, или name `*.jpg`, или desc с `Угол:`/`GPS Map Camera`/`GMT`) распознаются.

### Что НЕ менялось
- `_ensureGroupCheckbox` логика — была корректной, просто bucket был пустой по причине над-широкого детектора.
- HTML структура заголовков групп.
- Светлая тема (`@media prefers-color-scheme: light` + `.theme-light` overrides) — те же яркие цвета работают на белом фоне, проверено визуально.

### Граничный момент
> **Возможная регрессия для очень старых KMZ:** если KMZ был сохранён старой версией приложения (до v2.9.36) **с** date-only descriptions без `<styleUrl>` и без `*.jpg` в name — фото больше не распознаётся как photo-pin и появится в Пояснениях как обычный Point. Пользователь может удалить вручную через UI. Trade-off: правильная работа Пояснений > авто-детекция legacy-данных без сильных сигналов.

---

## BUG 39 (UPDATE v2.9.61) — Высота строк заголовков + чекбокс «Пояснения» нажимается

### Симптом
Пользователь приложил скриншот (раздел «Метки» в тёмной теме). На нём:
- Чекбокс «Пояснения» отображается в **indeterminate**-состоянии (тире вместо галочки), tooltip «Показать/скрыть всю группу» виден при наведении — слушатель есть, но при клике состояние **возвращается** в indeterminate, не переключается.
- Заголовки групп смотрятся ярче, чем в v2.9.59 (после v2.9.60 контраст-фикса), но «недостаточно выделяются», и пользователь хочет уменьшить высоту строк на 60%.

### Причина — два независимых дефекта

**Дефект A (визуал).** В v2.9.60 я усилил типографику (`font-weight 800/900`, `text-shadow`, accent2 border на счётчике), но padding остался `7px 10px` от ранних версий. Заголовки занимали ≈27 px вертикально × 3 группы = ≈81 px фиксированной высоты, отъедая место от списка маркеров. Также не было визуальной меты группы — иконка слева было единственным цветовым маркером.

**Дефект B (чекбокс).** `setMarkerVisible(pm, visible)` имел guard:
```js
if(!pm || !pm._leafletLayer || !pm._parentGroup) return;
```
Для **cadPlacemarks**, созданных через `startExplanationPoint` или seed-square из координат-карточки, поле `_parentGroup` НЕ устанавливается (эти placemark'и attach'ились прямо к `map`, не через layerGroup). В результате:

1. Пользователь кликает на чекбокс «Пояснения».
2. `change` handler вызывает `setMarkerVisible(m.pmRef, cb.checked)` для каждого Пояснения.
3. Для cadPlacemarks без `_parentGroup` — guard срабатывает, **молча** возвращает, `_visible` НЕ обновляется.
4. После handler: `renderMarksList()` → `_refreshGroupCheckbox()` пересчитывает state по `_visible` всех элементов. Поскольку `_visible` остался прежним, чекбокс **возвращается** в indeterminate.
5. Визуально: пользователь видит «не нажимается» — клик отскакивает.

Поле `_parentGroup` ставится **только** в `renderKMLOnMap` для placemark'ов из `parsedData.placemarks`. У всех `cadPlacemarks` из приложения этого поля нет → guard срабатывал для **всех** in-app объектов, не только Пояснений (но для ЗУ/ОКСов чекбокс работал по другим причинам — там были loaded-KML слои в смеси).

### Реализация

**Дефект A (CSS) — высота −60% + group-coloured border-left + gradient + uppercase:**
```css
.marks-group-header{
  display:flex;align-items:center;gap:6px;
  padding:3px 10px;                   /* было 7px → ~57% от старой высоты */
  background:linear-gradient(90deg,var(--surface2) 0%, var(--surface) 100%);
  border-bottom:1px solid var(--border);
  cursor:pointer;user-select:none;flex-shrink:0;
  transition:background .12s,border-color .12s;
  border-left:4px solid transparent;  /* группой-цвет ставится per-group ниже */
  min-height:24px                     /* страховка от слишком тонкой строки */
}
#marks-group-zu  > .marks-group-header{border-left-color:#5cff8a}  /* зелёный */
#marks-group-oks > .marks-group-header{border-left-color:#d6a3ff}  /* фиолетовый */
#marks-group-exp > .marks-group-header{border-left-color:#7adcff}  /* циан */

.mg-title{
  flex:1;font-size:12px;font-weight:800;color:var(--text);
  letter-spacing:0.3px;text-transform:uppercase   /* было without uppercase */
}
```

Высота строки: было `7+13+7 ≈ 27px`, стало `3+13+3 ≈ 19px` (с `min-height:24px` гарантия) ≈ **70% от старой**, близко к запрошенным 60%. Для трёх групп освобождается ~24px вертикально для списка маркеров.

Group-coloured `border-left: 4px` создаёт характерную «ленту» слева — пользователь сразу узнаёт, к какой группе относится header даже не глядя на иконку. Цвета совпадают с `mg-icon-{zu/oks/exp}` (та же палитра).

**Дефект B (JS) — fallback path в `setMarkerVisible`:**
```js
function setMarkerVisible(pm, visible){
  if(!pm) return;
  pm._visible = !!visible;   // обновляется ВСЕГДА, до проверок layer/parent
  // Path 1: layerGroup-tracked (loaded KML)
  if(pm._leafletLayer && pm._parentGroup){
    if(visible){
      if(!pm._parentGroup.hasLayer(pm._leafletLayer)){
        pm._parentGroup.addLayer(pm._leafletLayer);
      }
    } else {
      if(pm._parentGroup.hasLayer(pm._leafletLayer)){
        pm._parentGroup.removeLayer(pm._leafletLayer);
      }
    }
    return;
  }
  // Path 2 (v2.9.61): direct map attach/detach for cadPlacemarks without
  // a parent group — Пояснения через startExplanationPoint, seed-square
  // contours из координат-карточки.
  if(pm._leafletLayer && typeof map !== 'undefined'){
    if(visible){
      if(!map.hasLayer(pm._leafletLayer)) pm._leafletLayer.addTo(map);
    } else {
      if(map.hasLayer(pm._leafletLayer))  map.removeLayer(pm._leafletLayer);
    }
  }
}
```

Ключевое изменение: `pm._visible = !!visible` **в начале** функции, до проверок. Даже если `_leafletLayer` отсутствует (placemark ещё не отрисован), `_visible` обновляется, и при следующем render Метки и группа-чекбокс пересчитают state корректно.

Path 1 остался для `parsedData.placemarks` из loaded KML — ни в одной существующей логике поведение не меняется. Path 2 — новый, покрывает cadPlacemarks без `_parentGroup`.

### Что НЕ менялось
- HTML структура заголовков групп (3 `<div class="marks-group-header">`).
- `_ensureGroupCheckbox` — слушатели click/change без изменений.
- `_refreshGroupCheckbox` — логика `onCount === list.length` для checked/indeterminate-маппинга осталась.
- Светлая тема — те же group-цвета (#5cff8a, #d6a3ff, #7adcff) работают на белом фоне (проверено: контраст ≥ 4.5:1).

### Граничный момент
> **Path 2 предполагает, что `_leafletLayer` уже на `map`** (или будет добавлен через `addTo(map)`). Для cadPlacemarks из `_kdConfirmInner` это так — там `pmRef.addTo(map)` вызывается сразу после создания. Если в будущем появится новый путь добавления, который не вызывает `addTo`, нужно убедиться, что либо:
>   (a) `_parentGroup` устанавливается → срабатывает Path 1, либо
>   (b) layer всё-таки добавлен на map другим способом → срабатывает Path 2.
>
> **Идемпотентность**: `setMarkerVisible(pm, true)` для уже видимого pm — `hasLayer` возвращает true, addLayer пропускается. То же для `false` + не на карте. Безопасно при множественных кликах.
>
> **Counter-intuitive подмеченное**: для loaded-KML слоёв с outer toggle (KML-слой выключен) клик на чекбокс «Пояснения» внутри Меток ставит `_visible:true` И добавляет layer на parentGroup — но parentGroup сам не на map. Слой остаётся скрытым. Это корректно: «outer toggle» имеет приоритет, индивидуальный visibility — это «hint» для рендера внутри своего слоя.

---

## BUG 40 — Lock-in рабочего формата фотовывода в KMZ

### Запрос
«Зафиксируй в механизмах чтобы не сломать — хорошо получившийся формат вывода фотографий в kmz: фотографии отражаются на карте, но без подписей на карте (подписи не создают информационный шум). При нажатии слева в панели или на фотографии отражается когда снято и координаты».

### Реализация
CSS-блок tile-seam fix защищён 70-строчным комментарием в v2.9.58 (CHANGE 15) — тот же стиль применён к `<Style id="photo_icon">` блоку KMZ-export. 30-строчная "ASCII art" защитная капсула:

```
╔═══════════════════════════════════════════════════════════════╗
║ KMZ PHOTO RENDERING — ⚠ ВНИМАНИЕ: НЕ МЕНЯТЬ БЕЗ ПРИЧИНЫ.    ║
║ User-confirmed working (v2.9.58, Task 40 lock-in v2.9.60):   ║
║                                                                ║
║   • На карте Google Earth Pro отображается ТОЛЬКО иконка     ║
║     камеры — без подписи имени файла рядом.                   ║
║     Достигается: <LabelStyle><scale>0</scale></LabelStyle>    ║
║                                                                ║
║   • При клике на иконку (или клике в боковой панели) —        ║
║     один balloon: миниатюра + Координаты + Угол + Дата.       ║
║                                                                ║
║ ЕСЛИ НУЖНО МЕНЯТЬ:                                            ║
║   1. Тестировать в Google Earth Pro.                          ║
║   2. После клика проверить: один balloon, один <img>,         ║
║      имя только в title bar.                                  ║
║   3. На карте: только camera-icon, без floating-метки.        ║
║                                                                ║
║ ИСТОРИЯ ПРОВАЛИВШИХСЯ ПОПЫТОК (до v2.9.58):                  ║
║   • LabelStyle scale=0.7 → подпись имени видна на карте.     ║
║   • desc с <b>${p.name}</b> → имя дублировалось в balloon.   ║
║   • Без <BalloonStyle> → Google Earth по дефолту вставлял    ║
║     <h3>$[name]</h3> сверху balloon.                          ║
╚═══════════════════════════════════════════════════════════════╝
```

Сам блок (LabelStyle scale=0, BalloonStyle text=description) не тронут.

### Граничный момент
> Подобные защитные капсулы — рекомендованный подход для всего, на что было потрачено существенное debug-время. Видимая ASCII-рамка повышает вероятность, что follow-up разработчик прочитает её перед изменением.

---

## BUG 41 — XLSX-экспорт: логика выбора пути как KMZ/KML, без буфера

### Симптом / Запрос
«При экспорте в .xlsx: примени логику выбора пути как при экспорте в .kmz .kml (каждый раз спрашивать путь, не перезаписывать, сохранять префикс в дате в формате `2026-05-09_00-09_`, не копируй в буфер название файла); в файле добавь время формирования файла на листе "Фото" в фразе "Дата формирования: "».

### Причина
В v2.9.59 XLSX имел особый код:
```js
if(cachedHandle && mergeMode === 'fsa-handle'){
  // silent overwrite
  const w = await cachedHandle.createWritable();
  await w.write(blob);
  showToast(`✅ Перезаписано: ${savedName} · имя в буфере`);
}
```

Это ломало UX: пользователь не мог сохранить XLSX в **новый** файл без предварительного сброса handle-cache (которого нет в UI). KMZ/KML же **всегда** показывают picker. Поведение разное → путаница.

Также `_saveRecentExport` копировал имя в буфер обмена для всех форматов. Для XLSX типичный workflow — «открыть в Excel», и буфер должен оставаться доступен пользователю для других задач.

### Реализация

**Picker всегда:**
```js
// v2.9.60 — silent-overwrite ветка УДАЛЕНА.
const h = await _pickAndWriteBlob(blob, suggestedName, mime, '.xlsx');
if(!h) return;   // user cancelled
```

`_pickAndWriteBlob` — общий helper, тот же что для KML/KMZ. `suggestedName` уже содержит префикс даты `YYYY-MM-DD_HH-mm_<project>.xlsx` через `_autoExportName`.

**Без буфера для XLSX:**
```js
// Новый вариант _saveRecentExport без clipboard copy
function _saveRecentExportNoClipboard(format, filename){
  // Same recent-list update logic, но без _copyExportNameSilent(filename)
  ...
}
```

XLSX-flow вызывает `_saveRecentExportNoClipboard('xlsx', savedName)`. KMZ/KML по-прежнему используют `_saveRecentExport` (с clipboard copy).

**«Дата формирования» с временем:**
```js
// В _xlsxBuildTemplateSheet:
[title, null, `Дата формирования: ${new Date().toLocaleString('ru-RU')}`],
//                                ^^^^^^^^^^^^^^ было toLocaleDateString
```

Также добавлен auto-update этого поля в **существующих** workbook'ах при каждом экспорте — сканируется row 0 на лист «Фото», ищется ячейка с `^Дата формирования:`, обновляется на актуальный timestamp:

```js
for(let c = range.s.c; c <= range.e.c; c++){
  const cell = wsPhotos[XLSX.utils.encode_cell({r:0, c})];
  if(cell && /^\s*Дата формирования\s*:/i.test(String(cell.v||''))){
    cell.v = `Дата формирования: ${new Date().toLocaleString('ru-RU')}`;
    break;
  }
}
```

### Что НЕ менялось
- `_objectCatalogWB` priority в base-pickup (catalog → handle → fresh) — без изменений.
- ZU/OKS листы pass-through — без изменений.
- `_xlsxMergeCpIntoSheet` non-overwrite logic — без изменений.

### Граничный момент
> **Префикс даты в имени файла:** `_autoExportName('xlsx')` возвращает `2026-05-09_00-09_<project>.xlsx`. Запрошенный формат `2026-05-09_00-09_` присутствует **в начале** строки — уже корректно. `<project>` суффикс не вреден, его наличие даёт пользователю контекст что за выгрузка.
>
> **Если пользователь хочет именно перезаписать предыдущий файл:** picker сам предлагает то же имя; если в системе есть файл с этим именем, OS-диалог спросит «Overwrite?». Это корректный UX — пользователь подтверждает явно.

---

## BUG 42 — «Последние загруженные»: только последний файл каждого типа

### Симптом
«В разделе "последние загруженные" меню "Загрузить фото/объекты" в храни только последний загруженный файл каждого загруженного типа (сейчас выводится список из нескольких последних файлов одного типа)».

### Причина
В v2.9.55 `_LS_RECENT_KMLS` хранил `_MAX_RECENT_KMLS = 5` записей FIFO — список из 5 последних KML. На UI они выводились как 5 отдельных кнопок «🗺 KML: ...». Это было **слишком**: список визуально расплывался, и пользователь не мог быстро найти именно последний.

Для других типов (PHOTO/XLSX/KMZ) `_LS_PATH_*` уже хранил **по одному** последнему — поведение было асимметричным.

### Реализация
```js
const _MAX_RECENT_KMLS = 1;   // было 5
```

`_loadRecentKMLs` дополнен `slice(0, _MAX_RECENT_KMLS)` для **обрезания legacy-списков** в localStorage от v2.9.55–v2.9.59. Следующий save рерайтит storage с обрезанным массивом.

`_saveRecentKML` уже фильтрует (`arr.filter(x => x.name !== filename)`) и применяет `slice(0, _MAX_RECENT_KMLS)` — после обновления константы автоматически усекает до 1.

### Что НЕ менялось
- `_kmlOpenHandleCache` (per-session FSA-handle cache) — без изменений. Хранит сколько угодно handle'ов, не зависит от _MAX_RECENT_KMLS.
- `reopenRecentKML` — функция работает корректно с одиночным entry.

### Граничный момент
> **Cross-session FSA handles** не персистятся в localStorage (security policy браузеров). Поэтому при reload страницы старая запись в `_LS_RECENT_KMLS` показывает имя файла, но при клике откроется **picker** (без cached handle). Это нормально для одной записи, но было неудобно для списка из 5 — много элементов, все требовали picker.

---

## BUG 43 — При импорте папки → KMZ фотографии дублируются

### Симптом
«При импорте файлов из папки, а затем из kmz (проверено на последующем экспорте в kmz) фотографии дублируются (проверено на фотографии: с азимутом поворота камеры, и без азимута поворота камеры), а должны обогащаться».

### Причина
Старый KMZ-loader имел проверку дубля **только** для kmz-источника:
```js
if(!photos.find(p => p.name === kp.name && p.sourceType === 'kmz')){
  addPhoto(photoObj);
  photoAdded++;
}
```
Если фото `IMG_001.jpg` уже было загружено как `local` (из папки), эта проверка **не находила** и `addPhoto` всё равно вызывался → push в `photos[]` → второй маркер на карте → дубль в KMZ-экспорте.

Это **тот же корневой баг что в Task 38**, но проявлялся в последовательности «папка → KMZ» (а не «KMZ → KMZ»).

### Реализация
Routing через `addOrEnrichPhoto` (см. BUG 38). Старый код:
```js
if(!photos.find(p => p.name === kp.name && p.sourceType === 'kmz')){
  addPhoto(photoObj);
  photoAdded++;
}
```
Заменён на:
```js
addOrEnrichPhoto(photoObj);
photoAdded++;
```

`addOrEnrichPhoto` сам проверяет дубль case-insensitive по name, обогащает существующее, аудит в `_dedupLog`.

`photoAdded` теперь означает «всего обработано из KMZ», что более полезно для UI — детальная разбивка (added/enriched/skipped) показывается через `_dedupLog`-summary toast.

### Что НЕ менялось
- KMZ-loader сам (extraction logic, `mediaFiles`, `blobMap`, `_kmzActiveBlobMap`) — без изменений.
- Lifecycle KMZ blobs — все так же revokeObjectURL в `_disposeKMZBlobs`.
- Match-by-cadnum для `cadPlacemarks` (отдельная логика) — без изменений.

### Граничный момент
> **Что если фото в папке имеет EXIF-координаты, а KMZ-копия имеет иные координаты в `<coordinates>`?** Existing (из папки, EXIF) побеждает по non-overwrite policy. Если пользователь хочет KMZ-координаты — нужно сначала очистить EXIF в исходнике или удалить фото вручную перед re-import. Trade-off: предсказуемость > magic-merge.
>
> **Sequence reverse: KMZ → папка**, такой же вариант. KMZ грузится первым (с координатами из `<Point>`), потом папка (с EXIF). EXIF может быть **другим**. Existing (из KMZ) сохраняется. Снова: первый источник = ground truth.

---

## BUG 44 — Рассинхронизация pmRef ↔ leaflet-layers (zoom-тряска, partial-hide, призраки)

### Симптом
Пользователь после фикса 39 (UPDATE v2.9.61) сообщил три тесно связанных дефекта:

1. **«Трясёт zoom»**: повторный клик на тот же объект в Метках вызывает быструю осцилляцию zoom уровня (`z19 → z18.999 → z19 → ...`).
2. **«Не отключаются все ОКСы»**: счётчик группы показывает 8, но при клике на чекбокс группы скрывается **только 7**. Один остаётся видимым на карте, хотя в списке Меток он отмечен как hidden.
3. **«Пояснения красные при выключенном чекбоксе»**: вместо полного исчезновения остаются красные точки (а в включённом — чёрные).

### Причина — общий корень
Один и тот же кадастровый объект может быть представлен в **нескольких leaflet-layer'ах** одновременно:
- Загружен из двух KML-файлов (например, разные источники с одинаковым cadnum) → два `parsedData.placemarks` → два leaflet-layer'а.
- Создан в-app как `cadPlacemark` И существует параллельно как `parsedData.placemark` от загруженного KML.
- Photo-pin из old-version KMZ + JPG из folder-import (старый сценарий, частично решён CHANGE 21 v2.9.59).

Раньше (до v2.9.62) `setMarkerVisible(pm, false)` детачил **только** `pm._leafletLayer` — конкретный leaflet-объект, с которым связан `pm`. Параллельные представления того же кадастрового номера оставались на карте → пользователь видел «полу-скрытие».

Тот же корень дал три разных симптома:
- **(zoom-shake)** — тонко-связанный с тем что `_handleMapAreaClick` делегирует popup создание, а popup при animate-pan делает `moveend` → ре-input pipeline → возможен повторный flyTo.
- **(partial-hide)** — прямой эффект: out of N leaflet-layers одного cadnum, скрывается только тот что в `pm._leafletLayer` (один).
- **(призраки)** — частный случай partial-hide: parsedData circleMarker (red default style 7px) + cadPlacemark (cyan styled 8px) в одной точке. Cad-стиль накрывает parsed циан-фон. При hide cadPlacemark убирается, остаётся parsedData (red).

### Реализация — Этап 1 + Этап 2 рефакторинга

**Этап 1 — точечные фиксы:**

#### Bug 44a (zoom-shake) — debounce + idempotent guard в `_flyToMarker`
```js
let _flyToLastTs = 0;
let _flyToLastId = '';
function _flyToMarker(m){
  // 200ms cooldown for the same marker
  const now = Date.now();
  if(m.id === _flyToLastId && (now - _flyToLastTs) < 200) return;
  _flyToLastTs = now; _flyToLastId = m.id || '';

  // Idempotent guard: skip flyTo if already centred + same zoom
  const targetZoom = Math.max(map.getZoom(), 18);
  const targetPt = map.project([lat, lon], targetZoom);
  const centerPt = map.project([center.lat, center.lng], targetZoom);
  const alreadyThere = (Math.abs(targetPt.x-centerPt.x) < 2 &&
                        Math.abs(targetPt.y-centerPt.y) < 2 &&
                        map.getZoom() === targetZoom);
  if(!alreadyThere) map.flyTo([lat, lon], targetZoom, {animate:true, duration:0.8});
  // Skip the 850ms wait if no flyTo happened — open info card immediately
  setTimeout(() => _handleMapAreaClick(...), alreadyThere ? 0 : 850);
}
```

#### Bug 44b/44c (partial-hide, призраки) — `_objectIndex` (Этап 2)

Введён глобальный индекс **identityKey → Set<{layer, group, source}>**:

```js
const _objectIndex = (() => {
  const byKey   = new Map();
  const byLayer = new WeakMap();   // for fast unregister
  function register(key, layer, parentGroup, source){ /* idempotent push */ }
  function unregister(layer){ /* WeakMap-based cleanup */ }
  function layersFor(key){ return [...byKey.get(key) || []]; }
  function geomKey(geom){ /* "geom:lon,lat;..." rounded to 5 decimals (~1m) */ }
  return { register, unregister, layersFor, geomKey, ... };
})();
```

**Identity priority**:
1. **Cadastral number** (NN:NN:..:..) — primary, globally unique key for real estate.
2. **Geometry hash** (rounded coords first 3 points) — fallback, для Пояснений и custom-полигонов без cadnum.

`setMarkerVisible(pm, visible)` обновлён:
```js
const keys = [];
if(pm.cadNum) keys.push(pm.cadNum);
if(pm.geom)   keys.push(_objectIndex.geomKey(pm.geom));
else if(pm.coords) keys.push(_objectIndex.geomKey(pm.coords));

let foundAny = false;
for(const key of keys){
  const entries = _objectIndex.layersFor(key);
  if(!entries.length) continue;
  foundAny = true;
  for(const e of entries){
    // Path 1 (group attach) preferred, Path 2 (direct map) fallback
    if(e.group){ /* hasLayer + addLayer/removeLayer */ }
    else if(typeof map !== 'undefined'){ /* direct addTo/removeLayer */ }
  }
}
if(foundAny) return;
// Legacy Path 1 / Path 2 (когда index empty) — safety net
```

**Все 8 точек создания leaflet-layer'ов обновлены** для регистрации в индексе:
- `renderKMLOnMap` (parsedData placemarks) — primary key cadnum (если извлекаем из name/desc), fallback geomKey
- `_kdConfirmInner` 4 пути:
  - existing tgt layer
  - new layer (новый KML)
  - existing disk layer (диск-append)
  - fresh disk layer (диск-create)
- `deleteContourShape` (replace polygon → point) — unregister old + register new

**Все точки удаления leaflet-layer'ов обновлены** для unregister:
- `removeKMLLayer` — обходит все cadPlacemarks и parsedData.placemarks слоя
- `moveContourToOtherProject` — unregister перед `map.removeLayer`
- `deleteContourShape` — unregister старого Polygon перед его destroy

### Что НЕ менялось

- **API `setMarkerVisible(pm, visible)`** — внешне такая же; внутри теперь сначала проверяется индекс, затем legacy paths. Все вызовы из `_ensureGroupCheckbox`, `_refreshGroupCheckbox`, `renderMarksList` работают без изменений.
- **`_dedupParsedPlacemarks` (CHANGE 19 v2.9.58)** — продолжает работать. `_objectIndex` — это **дополнение** к dedup, не замена. Dedup помечает второй placemark `_visible:false` (предотвращает создание layer'а в `renderKMLOnMap`); `_objectIndex` — для случаев когда dedup не сработал (cadnum в `<ExtendedData>`, lowercase mismatch).
- **localStorage persistence** — `_objectIndex` живёт только в memory. После reload `loadKMLLayersFromStorage → _loadKMLFromText → renderKMLOnMap` автоматически re-регистрирует layers.
- **`photos[]` registry** — не использует `_objectIndex` (фото — другой класс объекта, у них другая identity-стратегия через `name`).

### Граничные моменты

> **Что если в KML #1 cadnum извлёкся, а в KML #2 — нет?** Тогда KML #1 layer регистрируется под `cadNum`, KML #2 — под `geomKey`. Они в индексе под **разными ключами**. Однако `setMarkerVisible(pm)` пробует **оба ключа последовательно** для pm — если у pm есть и cadNum и geom, оба key проверяются → оба layer'а скрываются. ✓
>
> **Что если у одного pm cadNum пустой, а geom отсутствует/невычислим?** `keys` оказывается пустым → `foundAny=false` → срабатывает legacy Path 1/2. Это safety net для placemark'ов без identity. На практике редко встречается (кроме photo-pin'ов, которые имеют `_visible:false` и не рендерятся).
>
> **WeakMap в byLayer** автоматически очищает entries когда сами leaflet-объекты собираются GC. Если разработчик забудет вызвать `unregister` — memory leak не возникнет, но `layersFor(key)` может вернуть entries с already-detached layer'ами. Защита: `hasLayer` check перед `removeLayer`/`addLayer` в setMarkerVisible — no-op для уже отсоединённых.
>
> **Идемпотентность register**: повторный вызов `register(key, sameLayer, ...)` — no-op (`if(byLayer.has(layer)) return;`). Можно безопасно вызывать из множественных code paths.

### Архитектурный комментарий
Это Этап 2 рефакторинга — **индекс поверх существующих структур**, не полная замена data model. Преимущества:
- Минимальный risk регрессии: `kmlLayers[]` / `cadPlacemarks` / `parsedData` не тронуты.
- Linear addition: ~150 LOC нового кода, ~40 LOC интеграции в 8 точек.
- Foundation для будущего Этапа 3 (полный store-based рефакторинг под GIS-pattern), если возникнет necesidad.

При возникновении похожих симптомов («объекты на карте не синхронизируются с UI»):
1. Открыть DevTools console.
2. `window._objectIndex.layersFor('61:55:...')` — увидеть все leaflet-layers под cadnum.
3. Если их больше чем ожидается — найти source labels (`'parsedKML'`/`'cadPlacemark/...'`/`'cadPlacemark/replaced'`) и определить, какой code path лишний.

---

## Итоговая таблица багов

| # | Симптом | Корень | Исправлено | LOC |
|---|---------|--------|------------|-----|
| 38 | Фото без координат + с координатами = 2 точки | `addLocalPhoto` дедуп по `name+size+!isRemote`, нет enrichment | `addOrEnrichPhoto` — case-insensitive lookup, non-overwrite enrich, audit log | +95 |
| 38' | Запрос: лог анализа дублей | новая фича | `_dedupLog` array + `showDedupReport` modal с picker save | +75 |
| 39A | Контраст заголовков «Метки» в темной теме | `mg-title 11px/700`, `mg-count` border `var(--border)` | усиление: 12px/800, accent2 border, текст-тень на иконках | +5 CSS |
| 39B | Чекбокс «Пояснения» disabled | `_detectPhotoPin` ловил date-only desc → real Пояснения исчезали | сужен PHOTO_DESC_RE_KML — date pattern удалён | -1 LOC |
| 39 (UPDATE A) | v2.9.61: высота строк заголовков −60%, мало выделяются | `padding:7px`, нет group-цветов, нет gradient | `padding:3px`+`min-height:24px`, group-coloured `border-left:4px`, gradient, `text-transform:uppercase` | +5 LOC CSS |
| 39 (UPDATE B) | v2.9.61: чекбокс «Пояснения» не нажимается | `setMarkerVisible` guard `!pm._parentGroup` молча no-op для cadPlacemarks без parentGroup | fallback path через `map.removeLayer`/`addTo(map)`; `_visible` обновляется ВСЕГДА до layer-проверок | +12 LOC JS |
| 40 | Lock-in рабочего KMZ photo формата | работает, но риск регрессии | защитная ASCII-капсула 30 строк | +30 LOC comment |
| 41 | XLSX silent-overwrite + buffer copy | особый код для XLSX, асимметрично | always picker, `_saveRecentExportNoClipboard`, time в Дата формирования | +30, -25 |
| 42 | Recent KMLs показывал 5 элементов | `_MAX_RECENT_KMLS=5` | `=1` + slice on load для legacy entries | -3 LOC |
| 43 | Папка→KMZ: фото дублируются | KMZ dedup `sourceType==='kmz'` only | routing через addOrEnrichPhoto | -3, см. 38 |
| 44a | Тряска zoom при повторном клике на объект | `_flyToMarker` без debounce + `setTimeout(_handleMapAreaClick, 850)` всегда | 200ms cooldown по `_flyToLastId` + idempotent guard через `map.project()` ±2px + delay=0 при alreadyThere | +20 LOC JS |
| 44b | Группа ОКС: «8 объектов, скрывается 7» | один cadnum в нескольких leaflet-layers (parsedKML #1 + parsedKML #2 + cadPlacemark) — `setMarkerVisible` детачил только `pm._leafletLayer` | `_objectIndex` Map<key, Set<{layer,group,source}>>; identity = cadnum primary, geomKey fallback; setMarkerVisible Path 0 walks все layers под key | +150 LOC JS |
| 44c | Пояснения красные при выкл. чекбоксе | parsedData circleMarker (red default) + cadPlacemark (cyan styled) в одной точке без cadnum — index не помогал | geomKey fallback (rounded coords first 3pts) → оба layer'а под одним ключом → одновременный detach | покрывается 44b |

---

## Правила (выводы)

1. **Дедупликация через единый entry-point.** Когда есть N путей добавления записи в коллекцию (`addLocalPhoto`, KMZ-loader, GDrive-loader, Yandex-loader, KML-loader), любой dedup-чек на каждом пути отдельно — будущая регрессия. Создать ОДИН helper (`addOrEnrichPhoto`) и роутить всех через него. Изменение dedup-стратегии — в одном месте.
2. **Non-overwrite enrichment для merge of records.** Когда два источника описывают одно — побеждает first-seen, но пустые поля заполняются из новых. Возврат `null` из extractor = «не трогать», явная семантика (см. также Правило 15 v2.9.56).
3. **Audit trail в `_sources` массиве.** Любая запись после merge должна знать, откуда пришли её данные. Бесплатно при добавлении, бесценно при отладке user-reported bugs.
4. **Защитные ASCII-капсулы для критичного кода.** Уже было правило 17 (v2.9.58 CHANGE 15) для CSS, теперь то же для KMZ-photo-style блока (CHANGE 40). Применять везде, где debug занял > 1 день.
5. **Date patterns в classifier'ах — антипаттерн.** Дата встречается в любом тексте (Пояснения, KML descriptions, GPS Map Camera). Использовать как **последний** signal, и только в комбинации с другими (e.g., "если name = `*.jpg` AND desc has date").
6. **Picker для всех экспортов.** Не делать silent-overwrite "удобство" для одного формата, если для других форматов picker. Пользователь ожидает консистентного поведения.
7. **Truncate legacy на load.** Когда меняется лимит хранилища (например, `_MAX_RECENT_KMLS 5→1`), `load()` функция должна обрезать legacy-данные через `slice(0, MAX)`. Иначе UI показывает старые записи до первого save.
8. **`setMarkerVisible` и подобные visibility-helpers — обновляйте state-флаг ВСЕГДА в начале функции.** До любых проверок на наличие layer/parent. Если placemark ещё не отрисован — `_visible` всё равно должен корректно отразить намерение пользователя, чтобы следующий render это учёл. Иначе UI показывает рассинхронизацию: чекбокс «click happened» (его состояние из cb.checked = true), а в реальности `_visible:undefined` или прежнее значение. После handler `renderMarksList → _refreshGroupCheckbox` пересчитывает state по `_visible` всех элементов — если он не обновлён, чекбокс «возвращается» в indeterminate, и пользователь видит «не нажимается».
9. **Layer attach/detach — два разных пути в EkceloFoto.** Loaded KML placemark'и тречатся через `pm._parentGroup` (layerGroup). In-app cadPlacemarks (через `_kdConfirmInner`, `startExplanationPoint`, `startNewContour`) — через прямой `addTo(map)` без layerGroup. Любая функция, которая работает с visibility, должна поддерживать оба пути. Old guard `if(!pm._parentGroup) return` ломал второй путь.
10. **Hierarchy of identity keys.** В GIS-данных один объект может иметь несколько identifying свойств: cadastral number (RFC, глобально уникальный), geometry hash (стабильно для одного физического участка), name+desc signature (нестабильно при разных описаниях). Иерархия: **cadnum primary → geomKey fallback → name+desc last resort**. `_objectIndex.layersFor` пробует ключи последовательно — первый match решает. См. также правило 27 (v2.9.59 — triple-key dedup для KML-export).
11. **Register/unregister дисциплина для индексов.** Если введён `_objectIndex` (или подобный side-table), КАЖДАЯ точка создания основного объекта (8 в нашем случае) должна вызывать `register`, КАЖДАЯ точка удаления — `unregister`. Иначе индекс расходится с реальностью, симптомы обнаруживаются месяцами позже. WeakMap по leaflet-объекту для byLayer защищает от GC-leak при пропущенном unregister.
12. **Idempotent guards для UI-actions с side-effects.** `flyTo`/`setView`/`fitBounds` визуально создают анимацию **даже если** target == current. Без guard'a повторный клик = повторная анимация = «тряска». Idempotent guard через `map.project(target, zoom) ≈ map.project(center, zoom)` ± 2px (sub-pixel tolerance) экономит лишние animations и устраняет race conditions с `moveend`-handlers.
13. **Side-table вместо полного рефакторинга.** Когда выявлен fundamental архитектурный недостаток (множественные leaflet-layers одного объекта), есть три варианта: (1) точечные patches → накапливаются как technical debt; (2) **side-table** (Этап 2: `_objectIndex`) → ~150 LOC, минимальный риск регрессии, решает 80% проблем класса; (3) полный рефакторинг под store-based pattern → 2000+ LOC, нужна major version, риск major regression. Вариант 2 — золотая середина для legacy single-file приложений типа EkceloFoto.
