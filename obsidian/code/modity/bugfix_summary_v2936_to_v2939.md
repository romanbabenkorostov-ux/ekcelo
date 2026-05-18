# EkceloFoto — Разбор ошибок v2.9.36 → v2.9.39

> Для разработчика, который делал версию 2.9.36.  
> Все баги — следствие трёх изменений, внесённых в v2.9.36. Ни один из них не работал как ожидалось.

---

## BUG 1 — Белая сетка между тайлами карты (все браузеры, все zoom)

### Симптом
Видимая сетка из белых полосок между тайлами OSM/спутника на любом zoom.  
В v2.9.28 проблемы не было.

### Причина
В v2.9.36 добавили светлую тему (`--map-bg: #f2efe9`). CSS `filter` был назначен на **каждый отдельный `.leaflet-tile`**:

```css
/* v2.9.36 — СЛОМАНО */
.leaflet-tile-pane { background: var(--map-bg); }
.leaflet-tile      { filter: var(--map-filter); }
```

`filter` на элементе принудительно создаёт **отдельный GPU compositing layer** для каждого тайла (~20–30 штук). Браузер позиционирует каждый слой через `translate3d()` с **независимым** округлением float→int координат. Соседние тайлы оказываются на позициях, например, `256px` и `257px` вместо `256px` и `256px` → между ними остаётся **1px щель**, через которую просвечивает светлый фон панели.

В v2.9.28 тема была только тёмной (`#0d1117`) → щели были тёмными → не видны.

Дополнительно: в **Chrome** каждый `<img>` тайл создаёт отдельный compositing layer даже без `filter` — это отдельный баг Chromium (#600120).

### Исправление (v2.9.37 + v2.9.38)

```css
/* v2.9.37/38 — ПРАВИЛЬНО */
.leaflet-tile-pane {
  background: var(--map-bg);
  filter: var(--map-filter);   /* один compositing layer для ВСЕХ тайлов */
}
.leaflet-container img.leaflet-tile {
  mix-blend-mode: plus-lighter; /* Chrome-specific fix: объединяет img в один blending context */
}
.leaflet-tile {
  outline: 1px solid transparent; /* WebKit sub-pixel crack suppressor */
}
```

**Правило:** `filter` всегда вешать на контейнер (`.leaflet-tile-pane`), **никогда** на отдельные тайлы.

---

## BUG 2 — OSM тайлы 403 в Firefox при открытии с `file://`

### Симптом
Firefox показывает тайлы OSM с ошибкой `"Access blocked — Referer is required"`. Chrome работает нормально.

### Причина — два слоя

**Слой A (внешний):** OSM с марта 2026 обязательно требует заголовок `Referer` в запросах к тайлам. Это новая enforcement-политика для борьбы со скраперами.

**Слой B (наш баг):** В v2.9.38 мы добавили:
```html
<meta name="referrer" content="strict-origin-when-cross-origin"/>
```
При открытии страницы с `file://` origin документа = `"null"` (специальное значение для локальных файлов). По спецификации `strict-origin-when-cross-origin` при cross-origin запросе с `null`-origin → браузер отправляет `Referer: "null"`. OSM отвергает `"null"` как невалидный Referer → **403**.

Chrome от `file://` обрабатывает это иначе (не отправляет Referer вообще, а не строку `"null"`), поэтому не ломался.

**Дополнительно:** Leaflet 1.9.4 **не поддерживает** опцию `referrerPolicy` в `L.tileLayer()`. Строка `referrerPolicy:'strict-origin-when-cross-origin'` в опциях тайл-слоя — **no-op**, она игнорируется.

### Исправление (v2.9.39)

1. Убрать `<meta name="referrer">` полностью.
2. Патчить `createTile()` у OSM слоя напрямую, устанавливая `img.referrerPolicy` на уровне элемента (переопределяет политику документа):

```js
const _osmTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {...});
_osmTileLayer.createTile = (function(_orig){
  return function(coords, done){
    const img = _orig.call(this, coords, done);
    img.referrerPolicy = 'no-referrer-when-downgrade'; // per-element, всегда работает
    return img;
  };
})(_osmTileLayer.createTile.bind(_osmTileLayer));
```

`no-referrer-when-downgrade` = отправить Referer при https→https, не отправлять при downgrade. Работает из любого контекста (file://, http://, https://).

---

## BUG 3 — Тайлы кадастра НСПД не загружаются

### Симптом
Слои кадастра (ОКС, Зем.участки и т.д.) не отображаются. В v2.9.28 работали.

### Причина — два изменения в v2.9.36

#### 3A. `crossOrigin: true` в опциях WMS-слоя

```js
// v2.9.36 — СЛОМАНО
L.tileLayer.wms(url, {
  crossOrigin: true,  // ← эта строка убивает кадастр
  ...
})
```

`crossOrigin: true` переключает `<img>` в **CORS-режим**: браузер добавляет заголовок `Origin` и требует `Access-Control-Allow-Origin` в ответе. `nspd.gov.ru` CORS-заголовки **не возвращает**. Браузер блокирует ответ на клиентской стороне — тайл остаётся пустым, даже если сервер вернул 200 с валидной PNG. В v2.9.28 `crossOrigin` не был задан → работало.

#### 3B. `<img>` элементы не могут отправить `Referer: https://nspd.gov.ru/`

`nspd.gov.ru` требует заголовок `Referer: https://nspd.gov.ru/`. При загрузке тайлов через `L.tileLayer.wms` браузер ставит в Referer URL текущей страницы (`file:///E:/...` или `https://yoursite.com/`) — **не** `nspd.gov.ru`. Переопределить Referer для `<img src>` невозможно: это forbidden header для атрибута `src`.

### Исправление (v2.9.39)

Заменить `L.tileLayer.wms` на **кастомный `L.GridLayer`** (`L_NspdLayer`), который:
1. Загружает каждый тайл через `fetch()` с опцией `referrer: 'https://nspd.gov.ru/'`  
   (`referrer` в fetch init — **не** forbidden header, работает корректно)
2. Конвертирует blob-ответ в objectURL → устанавливает как `<img>.src`
3. После загрузки отзывает objectURL

```js
const L_NspdLayer = L.GridLayer.extend({
  createTile(coords, done){
    const img = document.createElement('img');
    // ... вычисление EPSG:3857 BBOX через L.CRS.EPSG3857 ...
    fetch(url, {
      referrer: 'https://nspd.gov.ru/',
      referrerPolicy: 'unsafe-url',
      headers: { Accept: 'image/png,image/*' },
    })
    .then(r => r.ok ? r.blob() : Promise.reject(r.status))
    .then(blob => {
      const burl = URL.createObjectURL(blob);
      img.onload  = () => { URL.revokeObjectURL(burl); done(null, img); };
      img.onerror = () => { URL.revokeObjectURL(burl); done(new Error('img')); };
      img.src = burl;
    })
    .catch(e => done(new Error('nspd fetch ' + e)));
    return img;
  },
});
```

Работает из `file://`, `http://localhost` и любого `https://`.

---

## Итоговая таблица

| # | Баг | Версия появления | Версия исправления | Корень проблемы |
|---|-----|------------------|--------------------|-----------------|
| 1 | Белая сетка тайлов | v2.9.36 | v2.9.37/38 | `filter` на `.leaflet-tile` вместо `.leaflet-tile-pane` |
| 1b | Белая сетка в Chrome | v2.9.36 | v2.9.38 | Отсутствие `mix-blend-mode: plus-lighter` |
| 2 | OSM 403 в Firefox с file:// | v2.9.38 (наш фикс) | v2.9.39 | `<meta referrer>` + `null`-origin из file:// |
| 3A | Кадастр пустой (CORS) | v2.9.36 | v2.9.38 | `crossOrigin:true` без CORS-заголовков на сервере |
| 3B | Кадастр пустой (Referer) | всегда | v2.9.39 | `<img src>` не может отправить чужой Referer → fetch-layer |

---

## Правила на будущее

1. **`filter` CSS — только на контейнер**, никогда на отдельные тайлы.
2. **`crossOrigin: true`** — только если сервер возвращает `Access-Control-Allow-Origin`. Проверять в DevTools → Network → Response Headers.
3. **`referrerPolicy` в опциях `L.tileLayer`** — no-op в Leaflet ≤ 1.9.4. Патчить `createTile` вручную.
4. **`<meta name="referrer">`** уровня документа — не использовать для управления заголовками тайлов. Это влияет на все ресурсы страницы и ломается при `file://`.
5. **Referer для внешних WMS** (НСПД и подобных) — только через `fetch()` с `{referrer: '...'}`, завёрнутый в кастомный `L.GridLayer`.
