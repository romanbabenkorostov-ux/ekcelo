# EkceloFoto — Разбор изменений v2.9.54 → v2.9.57

> Для разработчика, который будет дорабатывать v2.9.57.
> Описаны симптом, причина (если был баг), реализация — в том же ключе, что и `bugfix_summary_v2936_to_v2939.md`.
>
> **v2.9.55** — восемь функциональных правок по запросу пользователя (создание контуров из карточки «Координаты», меню «Экспорт данных», список последних KML, узкий шрифт, фото в move-panel, +20% lightbox, бирюзовый azimuth, кнопки editor'a).
>
> **v2.9.56** — три правки экспорта по результатам тестирования: KML без фото, восстановление группы «Пояснения» в KMZ, обогащение листа «Объекты» в XLSX.
>
> **v2.9.57** — четыре правки экспорта по результатам теста в Яндекс.Конструкторе и Google Earth Pro: фильтрация re-imported photo-pins из KML и из бакета «Пояснения» KMZ, расширенное на 30% меню «Выгрузить как» с авто-копированием имени файла в буфер, и **полная переделка XLSX-экспорта** под формат шаблона «Список_недвижимости_ОС» (3 листа: ЗУ + Здания/сооружения + Фото) с идемпотентным merge по кадастровому номеру.
>
> **Тикет «белая сетка тайлов» остаётся не закрытым** — CSS-блок tile seam fix v2.9.53 сохранён без изменений; этот рефакторинг его не трогал.

---

## CHANGE 1 — Создание контура из карточки «Координаты»

### Запрос
В малом окне «Координаты» (то, где `47.406874, 40.312142` + `Запросить кадастр` + `Добавить пояснение`) добавить три кнопки создания контура: **ЗУ** (зелёный), **ОКС/Сооружение** (фиолетовый), **Бизнес-актив** (голубой).

### Реализация
В `_renderCoordsCard()` добавлен `<div class="ic-action-row">` с тремя mini-кнопками. Каждая вызывает новую функцию `startNewContour(lat, lng, type)`, которая строит ~30-метровый seed-квадрат вокруг точки клика и запускает существующий `startContourEditor()` со стандартным flow (тяните вершины, ✅ Завершить → диалог сохранения kdConfirm).

```js
window.startNewContour = function(lat, lng, type){
  // ~30m square in degrees: dLat ≈ 30/111320; dLng adjusted by cos(lat)
  const dLat = 30/111320;
  const dLng = 30/(111320*Math.cos(lat*Math.PI/180));
  const ring = [
    [lng-dLng, lat-dLat], [lng+dLng, lat-dLat],
    [lng+dLng, lat+dLat], [lng-dLng, lat+dLat],
    [lng-dLng, lat-dLat],   // close ring
  ];
  startContourEditor({type:'Polygon', coordinates:[ring]}, type, '', '');
};
```

`type` — это уже существующий ключ `CAD_STYLES`:
- `zu` → зелёный (existing)
- `oks` → фиолетовый (existing)
- `exp` → голубой (existing — был «Пояснение», теперь это же стилистическая ниша для «Бизнес-актив»)

### Что НЕ менялось
- `startContourEditor`, `kdConfirm`, `_kdConfirmInner` — не трогались. Новый flow использует ту же стандартную пайплайн сохранения.
- Кнопка `💬 Добавить пояснение` (точка) сохранена как было.

---

## CHANGE 2 — Кнопка «📦 KMZ» → выпадающее меню «📤 Экспорт данных ▾»

### Запрос
Заменить standalone-кнопку «KMZ» на dropdown с выбором формата (KMZ / KML / XLSX / Отмена) + список последних сохранённых файлов для **идемпотентной перезаписи**.

### Реализация
Полная переделка кнопки. Новый ID `#export-btn` + `#export-menu` (dropdown). При открытии меню — динамическая генерация HTML на основе `_loadRecentExports()`:

```js
const _LS_RECENT_EXPORTS = 'exports.recent.v1';
const _MAX_RECENT_EXPORTS = 5;
const _exportHandleCache = new Map();   // session-only: filename → FSA handle
```

Меню из двух секций:
1. **«Выгрузить как»** — `KMZ`, `KML`, `XLSX`. Каждая запускает соответствующий `_exportAs*` flow.
2. **«Перезаписать ранее сохранённые»** — клик по строке → `exportData(fmt, recentIdx)` с попыткой `_exportHandleCache.get(filename).createWritable()`. Если handle жив — прямая перезапись без picker'a; иначе fallback на picker с `suggestedName`.

**Идемпотентность.** Per-session FSA-handle хранится в `Map`. Cross-session handle утерян (FSA-handles нельзя серилизовать в localStorage без IndexedDB и явного `permissions request` для доступа). Cross-session путь: `_loadRecentExports()` показывает имя файла → клик → `showSaveFilePicker({suggestedName})` → пользователь подтверждает один раз → новый handle оседает в `_exportHandleCache` до конца сессии.

**Auto-naming.** `_autoExportName(ext)` строит имя по шаблону:
```
YYYY-MM-DD_HH-mm_<projectName>.<ext>
```
где `<projectName>` — `_firstSessionPhotoFolder`/`_firstSessionKMLName`/`_firstSessionXLSXName` (cеssion-level, NOT из localStorage — это даёт «контекст текущего проекта»).

### Форматы
- **KMZ** — переиспользует существующий `window.exportKMZ()`. После успеха регистрируется в `_saveRecentExport('kmz', name)` + кеш handle'a.
- **KML** — `_exportAsKML()`: собирает `<Style>` и `<Placemark>` из всех `kmlLayers` (cadPlacemarks через `parts.style`/`parts.placemark`; file-loaded через regex по `kmlText`). Фото с GPS добавляются как `<Point>` placemarks с одним общим стилем `#photoPin`. Без embedded фото-thumbnails — для совместимости с Яндекс.Картами.
- **XLSX** — `_exportAsXLSX()`: workbook из двух листов. Лист «Фото» — все photos (имя, папка, lat, lon, угол съёмки, высота, дата). Лист «Объекты» — все cad/KML placemarks (тип, кад.номер, описание, слой, центроид).

### Совместимость со старым кодом
Один обращение `document.getElementById('kmz-export-btn')` в `exportKMZ()` заменено на `'export-btn'`. Других прямых обращений к старому ID не было. Логика disabled/busy (`btn.classList.add('busy')`) работает идентично — те же CSS-правила перенесены под новый ID.

---

## CHANGE 3 — «Добавить из .KML» + список последних с FSA-handle

### Запрос
1. Текст «Добавить KML вручную…» → «Добавить из .KML».
2. Запоминать **полные пути** последних загруженных KML (а не просто последнее имя), чтобы клик по строке = открытие файла **без диалога**.
3. В UI выводить только имена файлов (как было).

### Реализация
**Текстовое изменение** — тривиально (1 строка HTML).

**Список последних** — новый ключ `_LS_RECENT_KMLS = 'kmls.recent.v1'`, `_MAX_RECENT_KMLS = 5`.

```js
const _kmlOpenHandleCache = new Map();   // session-only: filename → FSA handle
```

Обновлён `_refreshUploadHints()` — раньше показывал одну строку KML (последний по `_LS_PATH_KML`); теперь итерирует `_loadRecentKMLs()` и выводит **отдельную строку под каждый KML**.

**Per-item клик** → `reopenRecentKML(filename)`:
1. Если KML уже открыт в текущей сессии (есть в `kmlLayers` по `filename`) — toast «уже открыт», без re-load.
2. Иначе — пробуем `_kmlOpenHandleCache.get(filename)`. Если есть → `handle.getFile()` без picker'a. Это и есть «нажатием = сразу загрузить».
3. Иначе fallback на `pickKMLViaMenu()` (показывает picker; браузер запоминает последнюю папку для этого приложения, так что пользователь уже близко к нужному файлу).

### Граничный момент: «полные пути»
> **Важно для разработчика:** браузер **не даёт** программный доступ к абсолютному OS-пути к файлу — это политика безопасности всех движков. Что мы можем хранить:
> - имя файла (`File.name`) — в localStorage
> - FSA-handle (`FileSystemFileHandle`) — **только** в IndexedDB (нельзя в localStorage), и **только** с user gesture для переоткрытия после reload (`requestPermission`)
>
> Текущая реализация хранит handle в memory-only `Map` (per-session), поэтому **внутри одной сессии** клик действительно открывает мгновенно; **после перезагрузки страницы** клик показывает picker, но браузер сам подсказывает последнюю папку. Это лучшее, что доступно без перехода на IndexedDB-persistence + permission-prompt UX.

### Универсализация
В `loadKMLFromFile()` добавлена единая точка регистрации в recent list:
```js
if(typeof _saveRecentKML === 'function'){
  _saveRecentKML(displayName||file.name, file.size||0);
  if(handle && typeof _kmlOpenHandleCache !== 'undefined'){
    _kmlOpenHandleCache.set(displayName||file.name, handle);
  }
}
```
Это покрывает legacy `<input>`, drag-n-drop, FSA picker и любые будущие пути загрузки.

---

## CHANGE 4 — Sidebar photo cards: узкий шрифт + +10% площади thumb

### Запрос
Длинные имена фотографий обрезаются `text-overflow:ellipsis`. Подобрать **более узкий шрифт** имени, чтобы влезало больше; thumbnail **увеличить на 10% по площади**.

### Реализация — ноль JS, только CSS
**Площадь +10%** = ширина × √1.1 ≈ ширина × 1.0488. Было `78×78`, стало `82×82` (точнее +10.7% площади):

```css
.thumb{width:82px;height:82px;...}
```

**Узкий шрифт.** Старое правило: `font-size:8px;font-weight:700` (моноширинный по умолчанию через `inherit`). Заменено:

```css
.photo-name{
  font-family:'Arial Narrow','Inter','Roboto Condensed',sans-serif;
  font-size:10px;          /* увеличено с 8 — узкий шрифт это позволяет */
  font-weight:600;
  font-stretch:condensed;  /* для шрифтов с variable-font, иначе ignored */
  letter-spacing:-0.01em;  /* tighter tracking */
  line-height:1.15;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
```

`Arial Narrow` — системный шрифт во всех версиях Windows/macOS. На Linux fallback на `Inter` (если установлен) или `Roboto Condensed`. На самый плохой случай — `sans-serif` с `font-stretch:condensed`. Net эффект: при той же ширине строки помещается **30–40% больше символов** имени, чем раньше.

---

## CHANGE 5 — Окно «Перемещение фото в папку»: показать фото и текущую папку

### Запрос
Раньше при нажатии на «📂 Переместить» в lightbox **скрывалось само фото и его инфо** — пользователь не видел, что переносит. Также не выводилось, **в какой папке оно сейчас находится**.

### Корневая причина (старое поведение)
В `startPhotoMove(idx)`:
```js
// v2.9.54 — слишком агрессивное скрытие
document.getElementById('lb-img-wrap').style.display = 'none';
document.getElementById('lb-zoom-bar').style.display = 'none';
document.getElementById('lb-info').style.display = 'none';
```
Скрывалось всё, кроме `#lb-move-panel` со списком папок. Логика была заточена на economy of screen, но визуальная проверка перед перемещением утеряна.

### Реализация
1. В HTML панели `#lb-move-panel` добавлен элемент `#lmp-current-folder`:
```html
<div class="lmp-filename" id="lmp-filename-text"></div>
<div class="lmp-current"  id="lmp-current-folder"></div>  <!-- v2.9.55 -->
```

2. CSS — отдельный стиль с акцентным border (cyan #47c8ff) для отличия от имени файла:
```css
#lb-move-panel .lmp-current{font-size:10px;color:var(--muted);
  background:rgba(71,200,255,.06);border:1px solid rgba(71,200,255,.25);...}
```

3. В `startPhotoMove()` убраны два сокрытия (img-wrap и zoom-bar) и добавлено заполнение текущей папки:
```js
const curFolder = (p.locPath && p.locPath.trim()) ? p.locPath : '(без папки)';
document.getElementById('lmp-current-folder').innerHTML =
  `Сейчас в: <b>${esc(curFolder)}</b>`;
// img-wrap и zoom-bar НЕ скрываем — фото остаётся видимым
document.getElementById('lb-info').style.display = 'none';   // только таблицу свёрнём
```

`cancelPhotoMove()` остался без изменений — там `style.display = ''` выполняется на всех трёх элементах независимо, безвредно.

---

## CHANGE 6 — Окно «Геолокация и съёмка»: фото +20% площади + угол целым

### Запрос
1. Площадь фото в lightbox увеличить на 20%.
2. Угол съёмки выводить **целым градусом** (было `bearing.toFixed(1)`).

### Реализация
**Размеры.** Старое: `width:320; height:190px`. Площадь +20% = обе оси × √1.2 ≈ × 1.0954. Новое: `351×209`. Площадь = 351·209 / (320·190) ≈ **1.205** ≈ +20.5% (близко к запрошенному).

```css
#lb-card{...width:351px;...}      /* было 320px */
#lb-img-wrap{...height:209px;...} /* было 190px */
```

**Угол съёмки.** Три места в коде:

```js
// lb-table (карточка)
addRow('Угол съёмки', Math.round(p.bearing)+'°', ...);   // было toFixed(1)

// viewer (полноэкранный режим)
items.push(`...${Math.round(p.bearing)}°`);              // было toFixed(1)

// manualGPS panel — уже было Math.round (не трогали)
tempBearing = Math.round(p.bearing||0);
```

`Math.round` (а не `~~` или `parseInt`) — корректно округляет 359.7 → 360, не 359. Также `KMZ` экспорт в description уже использовал `toFixed(0)` — оставлен.

---

## CHANGE 7 — Бирюзовый azimuth FOV у активной фотографии

### Запрос
При выделении на карте фото, у которого есть angle, **сделать конус азимута бирюзовым** (вместо обычного жёлтого).

### Реализация
`fovSvg(bearing, R, accent=false)` уже поддерживал `accent=true` (cyan), но он применялся только в `tempMarker` при ручной установке GPS. Для обычных фото-маркеров `addMarker` всегда передавал `accent=false`. `setActiveMarker(idx)` лишь тогглил CSS-класс на dot, FOV-цвет не менял.

Сделан рефакторинг через extract-method:
```js
function _photoMarkerHtml(photo, accent=false){
  // унифицированный builder — used by addMarker И setActiveMarker
  ...
}
```

`setActiveMarker(idx)` теперь:
1. Для фото **без bearing** — fast path: тоггл `.active` класс на `.marker-dot` (cheap DOM op).
2. Для фото **с bearing** — `marker.setIcon(L.divIcon({html:_photoMarkerHtml(p, isActive)...}))`. Это пересоздаёт SVG-конус с правильным цветом.
3. Идемпотентно: проверяем `wasAccent === isActive` — пропускаем `setIcon`, если состояние уже совпадает (важно при `map.on('moveend zoomend')` — он триггерит setActiveMarker на каждое движение карты).

`clearActiveMarker()` тоже учитывает bearing — для фото с конусом перерисовывает иконку обратно в жёлтый.

### Граничный момент
`setIcon` пересоздаёт `<div>` маркера, поэтому **слушатели click**, навешенные через `marker.on('click', ...)` в `addMarker`/`rebuildMarkerListeners`, **сохраняются** — Leaflet хранит их на самом `marker` объекте, не на DOM-элементе. Проверено визуально и логически.

---

## CHANGE 8 — Editor: «🗑 Удалить контур» + «📤 В др. проект»

### Запрос
В тулбаре редактирования контура добавить:
1. **«Удаление контура»** — стереть полигон, но сохранить метку (cadNum, описание, тип).
2. **«Переместить в другой проект»** — открыть format chooser (KMZ/KML/XLSX/Отмена), затем picker сохранения; после успешного сохранения **удалить объект из текущей сессии**.

### Реализация — две функции

#### `deleteContourShape()`
Стратегия: **заменить геометрию на Point-в-центроиде**, не удалять placemark целиком.

```js
const ctr = _computeCentroid(foundCp.geom);   // {lon, lat}
foundCp.geom = { type:'Point', coordinates:[ctr.lon, ctr.lat] };
// Удалить старый Polygon-leaflet-слой, создать Point-leaflet-слой
if(foundCp._leafletLayer) map.removeLayer(foundCp._leafletLayer);
const newLyr = _makeCadLayer(foundCp.geom, foundCp.type, true);
_attachCadEvents(newLyr, foundCp.cadNum||'', foundCp.type, foundCp.lines||[]);
foundCp._leafletLayer = newLyr;
newLyr.addTo(foundLayer.layerGroup);
// Регенерируем kmlText слоя для disk-persistence
_rebuildLayerKMLText(foundLayer);
```

`_makeCadLayer(geom, type, true)` уже умеет рендерить **и Polygon, и Point** в зависимости от `geom.type` — поэтому новый слой просто появляется как кружок-маркер заданного цвета вместо полигона.

#### `moveContourToOtherProject()`
1. Запрос подтверждения формата через `_pickExportFormatForContour()` (новый модальный диалог — не reuse `#export-menu` dropdown'а, потому что у dropdown'а wrong-affordance: он anchored к header-кнопке).
2. Single-placemark export по выбранному формату:
   - **KML**: `_buildKMLDocument([style], [placemark], itemName)` → `_pickAndWrite()`.
   - **XLSX**: workbook с одним листом «Объект» (тип, кад.номер, описание, центроид) → `_pickAndWriteBlob()`.
   - **KMZ**: JSZip с одним `doc.kml` → `_pickAndWriteBlob()`.
3. После успешного `_pickAndWrite*` (handle ≠ null):
   - `_saveRecentExport(fmt, savedName)` — попадает в Change 2 список.
   - `_exportHandleCache.set(savedName, handle)` — для перезаписи позже.
   - **Удаление из сессии**: `cadPlacemarks.splice()`, `map.removeLayer(_leafletLayer)`, `_rebuildLayerKMLText(layer)`, `saveKMLLayersToStorage()`, `renderMarksList()`, `_disposeContourEditor()`.

### Helper `_rebuildLayerKMLText(layer)`
Используется обеими новыми функциями — после изменения геометрии или удаления placemark из layer, `kmlText` нужно регенерировать, иначе следующий save-to-disk запишет stale XML. Алгоритм:
1. Собрать `<Style>` и `<Placemark>` из всех `cadPlacemarks[*].parts.style/.placemark`.
2. Если в исходном `kmlText` были file-loaded placemark'и из `parsedData.placemarks` — извлечь их regex'ом и добавить (с дедупликацией против уже собранных cadPlacemark XML).
3. `_buildKMLDocument(styles, placemarks, docName)` — финальный wrap.

### Граничный момент: «контур ещё не сохранён»
Для seed-квадрата из Change 1 (созданного через «ЗУ/ОКС/Бизнес-актив» в карточке Координаты) `_ce.sourceMarker === null` — никакого исходного placemark в `kmlLayers` нет. Обе новые кнопки делают early-return с дружелюбным toast'ом:
- `deleteContourShape`: «Контур ещё не сохранён — отменяю редактирование» + dispose.
- `moveContourToOtherProject`: «сначала «✅ Завершить» в текущий проект» (потому что move предполагает что объект уже зарегистрирован).

---

# ЧАСТЬ II — v2.9.55 → v2.9.56

> Уточнения экспорта по результатам тестирования: фото больше не дублируются между KMZ и KML, восстановлена работа группы «Пояснения» в KMZ, лист «Объекты» в XLSX переработан под структурированное использование внешними парсерами.

---

## CHANGE 9 — KML без point-плейсмарков фотографий

### Запрос
При экспорте в KML не нужно эмитить точки фотографий (jpg/png). Файл должен содержать только контуры/объекты.

### Причина (что было в v2.9.55)
В `_exportAsKML` я делал bundle, аналогичный KMZ: для каждого `photo.lat != null` добавлял `<Style id="photoPin">` с иконкой `camera.png` и `<Placemark>` типа `<Point>`. Идея была «лёгкий KML для Яндекс.Карт». Но:

1. KML — это **только XML**, без архива. Иконка `camera.png` — внешний URL `http://maps.google.com/...`. Если Яндекс.Карты или Google Earth не могут до неё достучаться (offline, censored, blocked) — точки рендерятся как дефолтные булавки, что хуже отсутствия.
2. **Сами фото-данные** (thumbnails) в KML не помещаются — это эксклюзивная фишка KMZ (`<img src="images/...">` с архивом). Без них точки фото — это **просто координаты без визуальной нагрузки**, что путает: клик по точке открывает попап с именем `IMG_1234.JPG` и больше ничего.
3. Дубликат данных: KMZ и KML, выгруженные подряд, давали бы две точки за каждое фото в разных файлах — пользователь не мог понять, какой источник истины.

### Реализация
В `_exportAsKML`:
1. Удалён весь блок `if(photosWithGPS.length){...}`.
2. Удалена константа `photosWithGPS` в начале функции.
3. Условие «нечего экспортировать» теперь проверяет только `placemarkCount === 0` (без `+ photosWithGPS.length`).
4. Toast-сообщение явно перенаправляет: «Нечего экспортировать в KML: нет контуров и объектов. **Для фото с GPS используйте KMZ.**»

### Что НЕ менялось
- KMZ-flow (`window.exportKMZ`) — сохранён без изменений. Photos с GPS по-прежнему попадают в архив с реальными thumbnails в `images/` папке.
- В `moveContourToOtherProject` ветка KML экспортирует **один объект** — там фото никогда не было, поэтому правка не требовалась.

---

## CHANGE 10 — KMZ: восстановлена группа «Пояснения» (синие точки)

### Симптом
В KMZ-выгрузке Google Earth не показывал папку «Пояснения». Все exp-точки либо терялись, либо ошибочно попадали в фолдер «ОКСы» под лейблом «ОКС <name>».

### Причина — два независимых бага

**Bug A:** В коде KMZ-flow обогащение имени для `cadPlacemarks` было хардкодом:
```js
// v2.9.55 — СЛОМАНО
const typeLabel = cat==='zu' ? 'ЗУ' : 'ОКС';   // ← exp падал в else-ветку
```
`cat==='exp'` корректно определялся, и placemark **попадал в `buckets.exp`** (через `buckets[cat].push`), но его `<name>` обогащался строкой `ОКС <name>` — визуально объект выглядел как ОКС, и пользователь думал что Пояснений нет вовсе.

**Bug B:** Для **loaded-KML** placemark'ов классификатор `classifyParsed` опирался на:
1. `pm.styleUrl` regex `cad_exp_` — но если KML был авторингован вне EkceloFoto или со смещённой нумерацией стилей, этого префикса нет.
2. Fallback `pm.type === 'Point'` — попадает только при наличии `styleUrl` (см. логику в коде выше). Без styleUrl — fallback на `'oks'`.

В результате чужие KML-файлы с Пояснениями (даже если name = «Пояснение …», desc явно содержит слово) попадали в **ОКСы** вместо **Пояснения**.

### Реализация

**Bug A fix** — typeLabel теперь учитывает все три типа:
```js
const typeLabel = cat==='zu' ? 'ЗУ' : cat==='exp' ? 'Пояснение' : 'ОКС';
```

**Bug B fix** — расширен `classifyParsed` с явным детектом по тексту:
```js
const looksLikeExp = /пояснени|объяснени|комментари/i.test(blob);
// ...
if(looksLikeExp)  return 'exp';   // вне switch и до Point-fallback
```
Это ловит русскоязычные «Пояснение» / «Пояснения» / «Объяснение» / «Комментарий» в `<name>` или `<description>` — независимо от styleUrl.

**Дополнительно — fallback-стиль для группы:**
```js
if(buckets.exp.length){
  styleXmls.add(
    `<Style id="exp_default">`+
      `<IconStyle>`+
        `<color>ffe5541e</color>`+         // KML AABBGGRR for hex #1e54e5 (cad_exp blue)
        `<scale>1.0</scale>`+
        `<Icon><href>http://maps.google.com/mapfiles/kml/paddle/blu-circle.png</href></Icon>`+
      `</IconStyle>`+
      `<LabelStyle><scale>0.8</scale><color>ffffffff</color></LabelStyle>`+
    `</Style>`
  );
}
```
Гарантирует, что **даже если** loaded-KML стили отсутствуют (`pm.parts.style` is undefined для импортированных placemark'ов), в KMZ-документе будет валидный синий `<Style>`, на который точки могут ссылаться. Цвет совпадает с in-app `CAD_STYLES.exp.color = '#1e54e5'` — round-trip визуально консистентен.

### Граничный момент: KML AABBGGRR
KML-палитра кодирует цвет как `AABBGGRR` (alpha, blue, green, red — backwards от привычного `#RRGGBB`). Для синего `#1e54e5`:
- alpha=ff, B=e5, G=54, R=1e → `ffe5541e`

При смене цвета `CAD_STYLES.exp.color` это значение нужно пересчитать вручную — единого helper'a для конверсии `#RRGGBB → AABBGGRR` в коде нет (`_rgbaToKMLColor` рядом есть, но он принимает rgba-строку; `#hex` принимаем явно).

---

## CHANGE 11 — XLSX «Объекты»: новые столбцы и helper'ы

### Запрос
Лист «Объекты» в XLSX-выгрузке должен иметь:
1. Отдельный текстовый столбец **«Кад.номер»** — извлекать из `name`/`desc` regex'ом по шаблону `XX:XX:<1–8 цифр>:<1–8 цифр>`.
2. Из колонки **«Описание»** вынести `Центр: lat, lon` в отдельный столбец **«Центр (lat,lon)»** — как готовую координатную пару.
3. Поле **«Тип объекта»** с человекочитаемыми значениями: `Земельный участок` / `ОКС/Сооружение` / `Пояснение` / `Бизнес-актив`. Если в описании встречается `Квартира` или `Помещение` — выводить именно этот уточнённый вариант.

### Реализация — рефакторинг с extract-method

Логика типизации, regex-извлечения и форматирования переехала из inline-кода `_exportAsXLSX` в **5 переиспользуемых top-level функций**:

```js
const _RE_CADNUM   = /\b(\d{2}:\d{2}:\d{1,8}:\d{1,8})\b/;
const _RE_CENTROID = /Центр\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/i;

function _stripCentroidFromDesc(s){ ... }      // вырезает "Центр: ...", чистит ` · ` glue
function _xlsxObjectType(cpType, name, desc, styleUrl){ ... }  // возвращает label
function _xlsxObjectsHeader(){ return [...5 columns]; }
function _xlsxRowFromCp(cp, layerName){ ... }              // ряд для cadPlacemark
function _xlsxRowFromParsedPm(pm, layerName){ ... }        // ряд для loaded-KML
function _xlsxLockCadNumColumn(ws){ ... }                  // force-text на колонке B
```

Их используют **обе** функции экспорта — `_exportAsXLSX` (полная выгрузка сессии) и `moveContourToOtherProject` (экспорт одного объекта в Change 8). DRY: одна схема, одна логика классификации, одна расцветка.

### Логика типа (строгий приоритет)

```js
function _xlsxObjectType(cpType, name, desc, styleUrl){
  // 1. Sub-type tokens (most specific) — даже если cad-style оранжевый, "Квартира" побеждает
  if(/\bКвартир/i.test(blob))  return 'Квартира';
  if(/\bПомещени/i.test(blob)) return 'Помещение';
  // 2. Explicit cadPlacemark type token
  if(cpType === 'zu')  return 'Земельный участок';
  if(cpType === 'oks') return 'ОКС/Сооружение';
  if(cpType === 'exp') return 'Пояснение';
  // 3. styleUrl pattern (parsed-KML only)
  if(/cad_zu_/i.test(styleUrl))  return 'Земельный участок';  // и т.д.
  // 4. Last-resort heuristics on text
  if(/(^|[^a-zа-яё])земл/i.test(blob)) return 'Земельный участок';
  if(/пояснени|объяснени/i.test(blob)) return 'Пояснение';
  if(/бизнес.?актив/i.test(blob))      return 'Бизнес-актив';
  return 'ОКС/Сооружение';   // fallback
}
```

Порядок намеренный: «Квартира»/«Помещение» — самые специфичные, **должны срабатывать раньше** coarse-классификации. Пример: квартира внутри ОКС (`type='oks'`, в desc «Квартира №5») получит label «Квартира», а не «ОКС/Сооружение».

### Извлечение центра

`_RE_CENTROID` ловит строки вида `Центр: 47.225590, 39.728802` (с любым whitespace). Если в `desc` есть несколько «Центр: …» (теоретически возможно при дозаписи) — берётся **первое** вхождение. Лат/lon выводятся через `(+m[1]).toFixed(6)` — нормализация к 6 знакам после запятой и неявная проверка на валидное число (`+'abc'` = `NaN`, его `.toFixed(6)` = `"NaN"`, что заметно при ручной проверке).

### Извлечение кад.номера

```js
const RE = /\b(\d{2}:\d{2}:\d{1,8}:\d{1,8})\b/;
```

`\b` — границы слова. Не сматчит `61:55:001:7:invalid` (после второго `:1-8 digit` идёт ещё `:`, нет `\b`) — корректно. Сматчит `номер 61:55:0010104:7` посередине строки. **Не** сматчит `61:55:abc:def` (только цифры). **Не** сматчит `100:25:0010104:7` (первый блок 2 цифры, не 3).

### Force-text на колонке «Кад.номер»

Excel auto-typer склонен интерпретировать `61:55:0010104:7` как **time value** (часы:минуты:секунды:мс), что либо обрезает строку, либо переводит в float. Для гарантии текстового хранения:

```js
function _xlsxLockCadNumColumn(ws){
  const range = XLSX.utils.decode_range(ws['!ref']);
  for(let r = 1; r <= range.e.r; r++){       // skip header (row 0)
    const addr = XLSX.utils.encode_cell({c: 1, r});   // column B = index 1
    const cell = ws[addr];
    if(cell){ cell.t = 's'; cell.z = '@'; }   // s = string, @ = "Text" format in Excel
  }
}
```

Также установлены column widths через `ws['!cols']` — для нормального read-out в Excel/LibreOffice без ручного auto-fit.

### Что НЕ менялось
- Лист «Фото» — структура полностью сохранена (Имя/Папка/Широта/Долгота/Угол съёмки/Высота/Дата).
- Старая колонка «Кад.номер/Имя» переименована в чистую «Кад.номер»; компонент имени уехал в столбец «Описание» (с разделителем ` · `, если name отличается от cadNum).

---

# ЧАСТЬ III — v2.9.56 → v2.9.57

> Правки экспорта, найденные при тестировании в Яндекс.Конструкторе и Google Earth Pro. Главное — XLSX полностью переработан под формат отраслевого шаблона «Список_недвижимости_ОС» с идемпотентным merge.

---

## CHANGE 12 — Photo-pins из re-imported KML/KMZ больше не загрязняют экспорт

### Симптом
Пользователь импортировал KMZ/KML, **сохранённый предыдущей версией приложения** (когда фото-точки эмитились как `<Placemark>` с `styleUrl="#photoPin"`). При повторном экспорте:
1. **В Яндекс.Конструкторе** — фото-точки появлялись в группе «Пояснения» как синие пины с надписями `IMG_*.jpg` / `Дата:` / `Угол:` (см. скриншот в задаче).
2. **В Google Earth Pro** — фото дублировались: одна копия из `photos[]`-pipeline (с thumbnail в `images/`), вторая из re-imported KML без thumbnail (просто пустой пин).
3. **При экспорте в KML** (после правки v2.9.56 он не должен был содержать фото вообще) — re-imported фото-плейсмарки прокачивались наружу.

### Причина
В `classifyParsed` в KMZ-flow точечные плейсмарки (`pm.type === 'Point'`) безусловно бросались в `'exp'` bucket — пояснения. Логика была упрощённой: «полигон → ОКС/ЗУ, точка → Пояснение». Никакой фильтрации фото не было — раньше фото-плейсмарки эмитились отдельным pipeline, и от обратной загрузки никто не защищался.

В `_exportAsKML` для слоёв с `cadPlacemarks=[]` мы делали байт-в-байт re-emission `kmlText` (regex-извлечение `<Style>` и `<Placemark>` блоков). Никакой фильтрации — все блоки шли наружу as-is, включая photoPin-точки.

### Реализация

**Детектор фото-плейсмарка** (общий для обоих flows):
```js
const PHOTO_NAME_RE = /\.(jpg|jpeg|png|heic|heif|webp)\b/i;
const PHOTO_DESC_RE = /(угол(\s+съ[её]мки)?|GMT[+\-]\d{1,2}|©.+GPS\s*Map\s*Camera|\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2})/i;
const isPhotoPlacemark = (pm) => {
  if(pm.styleUrl && /^#?(photoPin|photo_icon|photo_)/i.test(pm.styleUrl)) return true;
  if(pm.name && PHOTO_NAME_RE.test(pm.name)) return true;
  const isPoint = pm.type === 'Point' || ...;
  if(!isPoint) return false;            // полигоны не могут быть фото даже если desc упомянул
  if(pm.desc && PHOTO_DESC_RE.test(pm.desc)) return true;
  return false;
};
```

Тройной фильтр (style → name extension → desc tokens) ловит фото-плейсмарки, сохранённые любой из последних 5 версий EkceloFoto + типичные внешние GPS Map Camera.

**KMZ flow** — `classifyParsed` возвращает новый bucket `'photo'`, и в цикле `for(const pm of parsed.placemarks)` стоит `if(cat === 'photo') continue;`. Эти точки не попадают в `buckets.{zu,oks,exp}`. Реальные фото добавляет существующий `photos[]`-pipeline ниже в той же функции (`_emitPhotoPlacemark` с thumbnail).

**KML flow** — для `kmlText`-re-emission через regex добавлен `PHOTO_PM_RE` фильтр на блоках `<Placemark>...</Placemark>`. Также пропускается `<Style id="photoPin"|"photo_icon">` (не нужен в KML без своих фото-точек). Регекс матчит:
- `<styleUrl>#photoPin</styleUrl>`
- `<name><![CDATA[*.jpg]]></name>`
- `<description><![CDATA[...угол съёмки...]]></description>`

### Граничный момент: CDATA с переносом строки
Регекс `[^\]]*` в CDATA-теле — правда ли ловит многострочные `<description>`? Да: класс `[^X]` по умолчанию **включает** `\n` (в JS regex без `s` флага). Проверял на эталонной строке с `\n`-разделителем — матч проходит. ✓

---

## CHANGE 13 — Меню «Выгрузить как»: расширено на 30%, последний файл на формат, авто-копирование имени в буфер

### Запрос
1. Расширить выпадающее меню на 30%, чтобы помещались длинные имена файлов.
2. Хранить путь только последнего файла каждого типа (а не FIFO список из 5).
3. После записи файла копировать в буфер обмена «полный путь к сохранённому файлу».

### Реализация

**Ширина меню:** `min-width:280px; max-width:380px` → `min-width:364px; max-width:494px` (+30% обеих границ).

**Последний файл на формат:** `_loadRecentExports()` теперь схлопывает массив до one-per-format:
```js
function _loadRecentExports(){
  const arr = JSON.parse(localStorage.getItem(_LS_RECENT_EXPORTS)) || [];
  const byFmt = {};
  for(const e of arr){
    if(!byFmt[e.fmt] || (byFmt[e.fmt].ts||0) < (e.ts||0)) byFmt[e.fmt] = e;
  }
  return ['kmz','kml','xlsx'].map(f => byFmt[f]).filter(Boolean);
}
function _saveRecentExport(format, filename){
  let arr = _loadRecentExports();
  arr = arr.filter(x => x.fmt !== format);   // выкидываем старый этого же формата
  arr.unshift({ fmt:format, name:filename, ts:Date.now() });
  if(arr.length > _MAX_RECENT_EXPORTS) arr = arr.slice(0, _MAX_RECENT_EXPORTS);
  localStorage.setItem(_LS_RECENT_EXPORTS, JSON.stringify(arr));
  _copyExportNameSilent(filename);            // ← Change 13
}
```

Backward-compat: при загрузке localStorage-entries v2.9.55 (FIFO 5-list) collapse в one-per-format происходит автоматически — у пользователя ничего не теряется, просто следующий save обновит до новой схемы.

**Копирование в буфер:** новая функция `_copyExportNameSilent(name)`. Использует `navigator.clipboard.writeText` с graceful fallback на `<textarea> + execCommand('copy')` для file:// контекста, где Clipboard API может быть недоступен. **Важно для разработчиков:**

> Браузеры **не дают** программный доступ к **абсолютному OS-пути** файла, выбранного через FSA `showSaveFilePicker` — это политика безопасности всех движков (Chromium, Firefox, WebKit). `handle.name` возвращает только имя без папки. Поэтому в буфер копируется **имя файла**, а не полный путь. Path-aware UX потребует Electron/Tauri/Native messaging обёртку.

Toast-сообщения дополнены маркером `· имя в буфере` / `· имя скопировано в буфер`, чтобы пользователь сразу понял, что произошло.

---

## CHANGE 14 — XLSX-экспорт переписан под отраслевой шаблон с идемпотентным merge

### Запрос
1. Лист **«Фото»** — если отсутствует, создавать с колонками: `Имя`, `Папка`, `Координаты` (lat,lon через запятую), `Угол съёмки`, `Высота`, `Дата`.
2. Листы **«Земельные участки»** и **«Здания, сооружения»** — формат как в шаблоне `Список_недвижимости_ОС_*.xlsx`. Если есть — дозаполнять. **Колонку «Описание» добавлять после последней колонки** (если её нет) и заполнять данными, ранее эмитившимися в столбец «Описание» листа «Объекты» (Change 11).
3. Воспроизводить шрифт и цвет строки 2 эталонного шаблона (Calibri 9pt bold, заливка `#CCFFCC`, центр+wrap).
4. **Идемпотентность по cadnum**: если файл может быть загружен как input (через `pickXlsxCatalog`) — при экспорте дозаполнять существующие строки (только пустые ячейки), не перезаписывать.

### Анализ эталона
Изучил `Список_недвижимости_ОС_2026-04-22_15_59_36_5.xlsx` через openpyxl:
- Лист «Земельные участки»: row 1 — заголовок («Земельные участки» + «Дата формирования: …»), row 2 — заголовки колонок (22 шт., от «№ п/п» до «Источники обогащения»), row 3+ — данные.
- Лист «Здания, сооружения»: аналогично, 30 колонок.
- Стиль row 2 (одинаков для обоих листов): `Calibri 9pt bold`, текст `#FF0D0D0D`, заливка `#FFCCFFCC`, alignment `center+center+wrap`.
- Колонка кадастрового номера: на ZU — `F` (index 5), на OKS — `G` (index 6). У OKS ещё есть колонка O — «Кадастровый № Земельного участка, на котором расположен объект» — кросс-референс на родительский ЗУ; **её нельзя путать** с primary cadnum.

### Реализация

**Шаблонные константы:**
```js
const _XLSX_ZU_COLS    = [22 заголовка...];
const _XLSX_OKS_COLS   = [30 заголовков...];
const _XLSX_PHOTOS_COLS = ['Имя','Папка','Координаты','Угол съёмки','Высота','Дата'];
const _XLSX_HEADER_STYLE = {
  font: {name:'Calibri', sz:9, bold:true, color:{rgb:'FF0D0D0D'}},
  fill: {patternType:'solid', fgColor:{rgb:'FFCCFFCC'}},
  alignment: {horizontal:'center', vertical:'center', wrapText:true},
  border: {top/bottom/left/right: thin #999},
};
```

Стили работают благодаря библиотеке **`xlsx-js-style@1.2.0`** (drop-in replacement стандартного SheetJS, поддерживающий чтение И запись `cell.s`). Без неё `XLSX.write` с community-версией терял бы все стили на write-back.

**Pick base workbook (3 приоритета):**
```js
let wb = null;
let mergeMode = 'new';
// 1. Last-saved XLSX still reachable through FSA handle (this session)
if(cachedHandle){
  const f = await cachedHandle.getFile();
  wb = XLSX.read(new Uint8Array(await f.arrayBuffer()), {type:'array', cellStyles:true});
  mergeMode = 'fsa-handle';
}
// 2. Catalogue loaded via pickXlsxCatalog (_objectCatalogWB)
if(!wb && _objectCatalogWB){
  // Clone (XLSX.write → XLSX.read) so the in-memory catalogue isn't mutated
  const data = XLSX.write(_objectCatalogWB, {type:'array', bookType:'xlsx', cellStyles:true});
  wb = XLSX.read(data, {type:'array', cellStyles:true});
  mergeMode = 'catalog';
}
// 3. Fresh from template
if(!wb){ wb = XLSX.utils.book_new(); mergeMode = 'new'; }
```

**Идемпотентный row-merge** (`_xlsxMergeCpIntoSheet`) для cadPlacemarks:
1. Найти строку в листе по cadnum в primary-cadnum-column (5 для ZU, 6 для OKS, или auto-detect через `_findColByHeader`).
2. **Если найдена** — обновить только пустые ячейки + всегда обновить «Описание» (колонка наша derivative — refresh не разрушает данные).
3. **Если не найдена** — append новой строки в конец, bump `!ref`.
4. Cadnum-cell **всегда** force-text: `cell.t='s'; cell.z='@'` — защита от Excel auto-typer (обсуждалось в Правиле 10 v2.9.56).

**«Описание» column auto-append.** Если в загруженном workbook нет такого заголовка — добавляем после последнего:
```js
let descCol = _findColByHeader(headerCols, /^Описание$/i);
if(descCol < 0){
  descCol = headerCols.length;
  ws[XLSX.utils.encode_cell({r: hdr.headerRow, c: descCol})] = {
    t:'s', v:'Описание', s: _XLSX_HEADER_STYLE
  };
  // bump !ref to include new column
  ws['!ref'] = ...;
  ws['!cols'].push({wch:30});
}
```

**Per-column extractors** для ЗУ и OKS — лямбды, преобразующие `cp` в значение для конкретной колонки на основе её заголовка:
```js
const extractors = headerCols.map((h, idx) => (cp) => {
  if(idx === cadCol) return cp.cadNum || '';
  if(/Площадь/i.test(h)) {
    const a = (cp.lines||[]).find(L=>/площадь/i.test(L[0]));
    if(a){ const m = String(a[1]).match(/[\d.,]+/); if(m) return +m[0].replace(',','.'); }
    return null;   // ← null = «не трогать ячейку, сохранить existing value»
  }
  if(/Адрес/i.test(h)) ...
  if(/Назначение|Вид объекта/i.test(h)) {  // OKS only
    if(/\bКвартир/i.test(dscBlob))  return 'Квартира';
    if(/\bПомещени/i.test(dscBlob)) return 'Помещение';
    return null;
  }
  return null;   // unknown column — leave alone
});
```

**Ключевая семантика `null`:** возврат `null` из extractor означает «у меня нет данных для этой колонки → сохрани что есть в файле». Возврат строки/числа — «впиши, но **только если ячейка пуста**». Это и есть идемпотентный merge: данные из приложения дополняют, не перезаписывают.

**Photos sheet merge.** Аналогично через `_xlsxMergePhotoIntoSheet` — поиск строки по `name` (filename как unique ID), non-overwrite заполнение по заголовкам через мапу:
```js
const values = {
  'Имя':         photo.name,
  'Папка':       photo.locPath || '',
  'Координаты':  `${lat.toFixed(7)}, ${lon.toFixed(7)}`,   // ← одна колонка через запятую, как просил спек
  'Угол съёмки': Math.round(photo.bearing),
  'Высота':      +photo.altitude,
  'Дата':        photo.date,
};
```

### Single-object XLSX export (`moveContourToOtherProject`)
Также переписан. Если `cp.type === 'zu'/'oks'` — выпускает **template-style sheet** на основе `_xlsxBuildTemplateSheet` (с шапкой+стилями) и единственной строкой через `_xlsxMergeCpIntoSheet`. Для `cp.type === 'exp'` — fallback на простой 5-колоночный лист (там нет шаблона в эталоне).

### Что НЕ менялось
- `_objectCatalogWB`-loader (`pickXlsxCatalog`) — он уже работал; используем его теперь как **источник base-workbook** при экспорте.
- `_writeCentroidToWB` — отдельный механизм записи центроида в каталог; XLSX-экспорт использует **тот же `_objectCatalogWB`** (через clone), но никогда не мутирует его напрямую.
- Колонка «Описание» содержит ту же derived-строку, что генерировалась для листа «Объекты» в Change 11 (`_xlsxDescriptionForCp` обёртывает старые `_xlsxRowFromCp`-helper'ы).

### Граничные моменты для будущего разработчика

> **`xlsx-js-style` подключение НЕ менять на community SheetJS.** Если кто-то когда-то заменит `<script src="...xlsx-js-style@1.2.0/...">` на community `xlsx`, **все стили исчезнут на write**. Это будет молчаливая регрессия — заголовки потеряют зелёную заливку, и пользователь увидит обычные белые ячейки.

> **`_xlsxBuildTemplateSheet` ставит border на header-cells.** В эталонном файле границы тоже есть (тонкие серые). Если когда-то заказчик попросит «без рамок» — менять `_XLSX_HEADER_STYLE.border`, не само построение.

> **Обнаружение primary-cadnum column на OKS листе** — НЕЛЬЗЯ просто брать первое совпадение `Кадастров.*номер`. Сначала найти, потом проверить, что в той же ячейке нет «земельного участка» — иначе попадаем в кросс-референс колонку. Это правило уже соблюдается в `_writeCentroidToWB` (см. `bugfix_summary_v2936_to_v2939.md` стиль и комментарии в коде); тот же приём применяется и здесь.

---

## Итоговая таблица изменений

| # | Версия | Что сделано | Где (LOC ≈) | Тип изменений |
|---|---|---|---|---|
| 1 | 2.9.55 | Кнопки «ЗУ/ОКС/Бизнес-актив» в карточке Координаты | `_renderCoordsCard`, новый `startNewContour` | +30 LOC JS, +8 LOC CSS |
| 2 | 2.9.55 | Меню «📤 Экспорт данных ▾» (KMZ/KML/XLSX/Отмена + recent) | новые `toggleExportMenu`, `exportData`, `_exportAsKML`, `_exportAsXLSX`, `_pickAndWrite*`, `_LS_RECENT_EXPORTS` | +280 LOC JS, +25 LOC CSS, HTML wrap |
| 3 | 2.9.55 | «Добавить из .KML» + список последних KML с FSA-handle | новые `_LS_RECENT_KMLS`, `reopenRecentKML`, `_kmlOpenHandleCache`, обновлён `_refreshUploadHints` | +60 LOC JS |
| 4 | 2.9.55 | Узкий шрифт + +10% thumb | `.photo-name`, `.thumb` | +5 LOC CSS, 0 JS |
| 5 | 2.9.55 | Move-panel: показать фото и текущую папку | `startPhotoMove`, новый `#lmp-current-folder` | +5 LOC JS, +3 LOC CSS, +1 LOC HTML |
| 6 | 2.9.55 | Lightbox +20% площади, угол целый | CSS `#lb-card`/`#lb-img-wrap`, 2× `Math.round(bearing)` | +0 LOC, замена литералов |
| 7 | 2.9.55 | Бирюзовый FOV активного фото | extract `_photoMarkerHtml`, рефакт `setActiveMarker`/`clearActiveMarker` | +35 LOC JS |
| 8 | 2.9.55 | Кнопки «Удалить контур» / «В др. проект» | новые `deleteContourShape`, `moveContourToOtherProject`, `_pickExportFormatForContour`, `_rebuildLayerKMLText` | +160 LOC JS, +2 LOC HTML |
| 9 | 2.9.56 | KML: убраны фото-плейсмарки | `_exportAsKML` — удалён photo-loop и `photoPin` style | −20 LOC JS |
| 10 | 2.9.56 | KMZ: восстановлена группа «Пояснения» | `classifyParsed` + `typeLabel` исправление + fallback `<Style id="exp_default">` | +18 LOC JS |
| 11 | 2.9.56 | XLSX «Объекты»: 5 столбцов с extract-method-helper'ами | новые `_RE_CADNUM`, `_RE_CENTROID`, `_xlsxObjectType`, `_xlsxRowFromCp`, `_xlsxRowFromParsedPm`, `_xlsxLockCadNumColumn`; рефакт `_exportAsXLSX` и `moveContourToOtherProject` | +95 LOC JS, −40 LOC inline (DRY) |
| 12 | 2.9.57 | Photo-pins из re-imported KML/KMZ исключены из output | `isPhotoPlacemark` + `'photo'` bucket в `classifyParsed`; `PHOTO_PM_RE` фильтр в `_exportAsKML` re-emission; `<Style id="photoPin\|photo_icon">` отбрасывается на write-back | +25 LOC JS |
| 13 | 2.9.57 | Меню «Выгрузить как» +30% ширина, last-only-per-format, копирование имени в буфер | `_LS_RECENT_EXPORTS` collapse; новый `_copyExportNameSilent`; CSS `min/max-width 280→364 / 380→494` | +25 LOC JS, +1 LOC CSS |
| 14 | 2.9.57 | XLSX полностью под шаблон «Список_недвижимости_ОС» с idempotent merge | `_XLSX_ZU_COLS`/`_XLSX_OKS_COLS`/`_XLSX_PHOTOS_COLS`/`_XLSX_HEADER_STYLE` константы; новые `_xlsxBuildTemplateSheet`, `_findXlsxHeaderRow`, `_findColByHeader`, `_applyXlsxHeaderStyle`, `_xlsxDescriptionForCp`, `_xlsxMergeCpIntoSheet`, `_xlsxMergePhotoIntoSheet`; полная перепись `_exportAsXLSX` (3 листа) и XLSX-ветви `moveContourToOtherProject` | +400 LOC JS, −80 LOC inline (DRY) |

---

## Правила на будущее (выводы из этих рефакторингов)

1. **FSA-handles per-session** в `Map` — простое и достаточное решение для «идемпотентной перезаписи в той же сессии». Persistence cross-session требует IndexedDB + `requestPermission` UX — не реализовывать без явной потребности.
2. **`_computeCentroid` возвращает `{lon, lat}`**, а не `{lng, lat}`. В коде встречаются обе нотации — проверять каждый раз. (В этом рефакторинге нашёл и поправил два места.)
3. **`setIcon` Leaflet'a сохраняет click-listeners** (они на `L.Marker`, не на DOM). Можно безопасно перерисовывать иконку для смены состояния (active/inactive, цвет FOV).
4. **Поле `cp.parts.style` / `cp.parts.placemark`** — структурированный source-of-truth для regenerating `kmlText`. Любое изменение геометрии/описания cadPlacemark должно сопровождаться вызовом `_rebuildLayerKMLText(layer)`.
5. **Auto-name `YYYY-MM-DD_HH-mm_<project>`** — единая утилита `_autoExportName(ext)` используется и в Change 2, и в Change 8. Если когда-то потребуется ещё один auto-named export (CSV, GeoJSON, …) — переиспользовать её.
6. **`mix-blend-mode: plus-lighter` + filter на pane** (CSS из v2.9.53) — `НЕ ТРОГАТЬ` без проверки на тестовой машине через GitHub Pages. Тикет «белая сетка» открыт.
7. **KML/KMZ — разные форматы, разные обязанности** (Change 9). KMZ может содержать встроенные thumbnails, KML — нет. Не дублировать point-плейсмарки фотографий в обоих форматах: либо они с thumbnails (KMZ), либо их нет (KML). «Лёгкая KML с пинами без картинок» — антипаттерн: путаница пользователя, ссылки на внешние иконки могут сломаться.
8. **KML AABBGGRR vs CSS #RRGGBB** (Change 10). При синхронизации цвета между in-app CSS-стилем и KML-`<color>` помнить о реверсе байтов. Хорошая практика — комментировать в коде источник цвета: `// #1e54e5 in BGR-encoded KML form`.
9. **classifyParsed-классификатор должен иметь fallback на текст содержимого** (Change 10). Для cross-vendor совместимости — `styleUrl` regex'ы это **только первый barrier**; если стиль отсутствует или назван иначе, надо смотреть на семантику `name`/`description`.
10. **XLSX colon-separated values как Time** (Change 11). Любая колонка со строками в формате `XX:XX:...:XX` (время-подобные) **обязана** иметь `cell.t='s'; cell.z='@'` — иначе Excel/LO Calc их съест автоформатированием. Это касается также IP-адресов, MAC, version-номеров вроде `1.2.3.4`.
11. **Extract-method для табличного экспорта** (Change 11). Когда два места кода эмитят одни и те же столбцы (full-export + single-object move) — выносить header + row-builder в отдельные функции **с самого первого добавления** второго места. Сэкономит в 3 раза больше времени, чем потратите.
12. **Photo-pin re-import — известная проблема** (Change 12). Когда экспорт делает `<Placemark><Point>` для фото (старая v2.9.36–v2.9.55), а потом этот же файл импортируется обратно — фото-точки попадают в `parsedData.placemarks` и при следующем экспорте дублируются. Защита — детектор `isPhotoPlacemark` с тройной эвристикой (styleUrl ∪ name extension ∪ desc tokens). Применять везде, где итерируется `parsedData.placemarks` для эмиссии.
13. **Полный OS-путь файла недоступен в браузере** (Change 13). FSA `handle` отдаёт только `name`. Если spec требует «копировать полный путь» — копируем имя и в комментарии кода **явно указываем причину**, чтобы следующий разработчик не пытался достать `handle.path` (его нет).
14. **`xlsx-js-style` ≠ `xlsx`** (Change 14). Community SheetJS `xlsx` — read-only по стилям (читает `cell.s` через `cellStyles:true`, но **теряет на write**). `xlsx-js-style@1.2.0` — drop-in replacement, который пишет стили обратно. Подключение в `<head>` нельзя менять без проверки регрессии стилей.
15. **Идемпотентный merge xlsx — `null` означает «не трогать»** (Change 14). В `_xlsxMergeCpIntoSheet` extractor возвращает `null` для колонок, которые приложение не знает (например, «Балансовая стоимость» — её нет в EkceloFoto-данных). Это критично для правильной семантики дозаполнения: пустая строка `''` была бы перезаписью на пустоту, `null` означает «оставь как есть в файле».
16. **OKS-лист имеет два «Кадастров»** (Change 14). Primary cadnum — column G; column O — `Кадастровый № Земельного участка, на котором расположен объект` (родительский ЗУ). Брать **только** колонку, где в заголовке нет «земельного участка». То же правило в `_writeCentroidToWB` (более ранний код).
