# ADR: Tile-seam fix (Leaflet карта)

**Status:** Active · **Date:** 2026-05-26 · **Scope:** `viewer/index.html`

## Симптом
Тонкая (1px) сетка-щели цвета фона между соседними тайлами OSM/Esri.
Чаще всего — на HiDPI экранах и в светлой теме. Браузеры: Chrome, Yandex.Браузер, Firefox.

## Корень проблемы
1. Leaflet располагает плитки через `transform: translate3d(...)`. На субпиксельных позициях движки округляют по-разному, образуя 1px-щель **между** GPU-слоями.
2. Каждая `.leaflet-tile` получает собственный композитный слой, если:
   - на ней висит `filter` (по умолчанию `leaflet.css` ставит `filter: inherit`);
   - или висит `will-change` / `transform` / `backface-visibility` (v2.9.50 — провал);
   - или ширина/margin отличаются от рассчитанной Leaflet'ом (v2.9.33 — катастрофа на z>maxNativeZoom).
3. Если на панели НЕТ единого композитного слоя (identity `--map-filter` в светлой теме оптимизируется компоновщиком), `mix-blend-mode: plus-lighter` нечего склеивать.

## Решение (контракт)
Универсальное CSS-решение, **без JS** и **без UA-сниффинга**:

```css
.leaflet-tile-pane{
  background: var(--map-bg);   /* последний рубеж: цвет щели = цвет тайла */
  filter: var(--map-filter);   /* темизация (в светлой теме identity!) */
  isolation: isolate;          /* изолированная blending-группа */
  will-change: transform;      /* ПРИНУДИТЕЛЬНО один композитный слой */
  transform: translateZ(0);    /* belt+suspenders */
}
.leaflet-container img.leaflet-tile{
  mix-blend-mode: plus-lighter;  /* Leaflet PR #8891, Chromium #600120 */
}
.leaflet-tile{
  filter: none !important;     /* перебить leaflet.css filter:inherit */
  outline: 1px solid transparent;  /* закрыть субпиксельную трещину */
}
@supports not (mix-blend-mode: plus-lighter){
  .leaflet-tile{ outline-color: var(--map-bg); }
}
```

### Почему именно эти правила
- `isolation: isolate` создаёт **изолированную blending-группу**. По спеке без неё `mix-blend-mode` сливает плитку с тем, что под пана́лью (карта-фон), а не с соседним тайлом.
- `will-change: transform` на **панели** (не на плитках!) делает её отдельным композитным слоем независимо от значения `filter`. Это снимает регрессию в светлой теме, где `--map-filter` = `brightness(1) saturate(1)` оптимизировался компоновщиком в no-op.
- `mix-blend-mode: plus-lighter` склеивает соседние `<img>` поверх 1px-щели.
- `filter: none !important` на плитках перебивает `leaflet.css` `.leaflet-tile{filter:inherit}` — иначе плитки получают per-tile композитные слои (а именно они — источник щели).
- `outline: 1px solid transparent` — субпиксельный патч для WebKit.
- `@supports not (...)` — fallback для древнего Chromium (старые билды Я.Браузера): красим уже существующий 1px-outline в цвет фона, **никаких** изменений геометрии (никогда `width`/`margin`!).

## Запрещено (повторы провалов)
- ✗ `width` / `margin` на `.leaflet-tile` — катастрофа на z>maxNativeZoom (v2.9.33).
- ✗ `will-change` / `transform` / `backface-visibility` на `.leaflet-tile` — создаёт per-tile слои, источник щели (v2.9.50).
- ✗ `filter` на `.leaflet-tile` — то же.
- ✗ UA-сниффинг (`/YaBrowser/`) как условие фикса — часть браузеров остаётся без него, регрессия (v2.9.62b).
- ✗ JS-MutationObserver на `tileload` — JS-двойник сломанного CSS-правила.

## Проверка изменений (обязательная)
1. Chrome + Firefox + Yandex.Browser — все три.
2. Zoom: 10, 18, 22 (нормальный и upscaled выше maxNativeZoom).
3. HiDPI монитор (devicePixelRatio > 1) — там сетка появляется первой.
4. Светлая И тёмная темы.
5. Метки / Контуры / фото-пины не сломались.

## Хроника провалов (для предотвращения повторов)
- v2.9.30 — `filter` на `.leaflet-div-icon` — мимо мишени.
- v2.9.31 — `delete L.Icon.Default._getIconUrl` — не туда.
- v2.9.32 — `mergeOptions({iconUrl:''})` — сломало фото-маркеры.
- v2.9.33 — `width:257px; margin:-1px; transform:scale(1.02)` — на z22 квадраты 1791×1791 px пустоты.
- v2.9.34 — `filter` на тайле — Firefox ок, Chrome — щели.
- v2.9.36 — добавили светлую тему → щели стали видны.
- v2.9.50 — `will-change`/`backface-visibility` на тайлах — стало хуже.
- v2.9.53 — пять CSS-правил без `isolation:isolate` — работало пока `--map-filter` не был identity.
- v2.9.62 — `@supports`-стиль fallback через JS-класс `tile-seam-fallback`.
- v2.9.62b — UA-гейт на YaBrowser → щель возвращалась на Chrome/Firefox при identity filter.
- **2026-05-26** — universal CSS (isolation + will-change на панель, безусловно), JS убран.

## Связанные файлы
- `viewer/index.html` — реализация (CSS-блок «TILE SEAM FIX»).
- Leaflet PR #8891, Chromium bug #600120 — внешние источники механизма.
