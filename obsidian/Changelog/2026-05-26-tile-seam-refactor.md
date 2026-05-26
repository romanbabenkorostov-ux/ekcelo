# 2026-05-26 — tile-seam: universal CSS, убран UA-сниффинг

## Задача
Артефакты-плитки (1px белая сетка между тайлами OSM/Esri) снова вылезли в Firefox, Chrome и Яндекс.Браузере при построении карты. Зафиксировать правильную защиту в Obsidian.

## Корень
- В светлой теме `--map-filter` = `brightness(1) saturate(1)` (identity) — компоновщик оптимизирует фильтр в no-op → панель НЕ получает единого композитного слоя → плитки рендерятся как отдельные GPU-слои → `translate3d` округляется субпиксельно → 1px-щель.
- Прежний JS-IIFE гейтил защиту по `/YaBrowser/` UA → Chrome/Firefox оставались без `isolation:isolate` + `will-change:transform` → именно там сетка и возвращалась.

## Решение
`viewer/index.html` — CSS-блок «TILE SEAM FIX»:
- На `.leaflet-tile-pane` добавлены **безусловно**: `isolation: isolate` + `will-change: transform` (раньше только под `html.tile-seam-yandex`).
- Fallback для древнего Chromium без `mix-blend-mode: plus-lighter` переведён с JS-класса (`tile-seam-fallback`) на `@supports not (...)`.
- Удалён JS-IIFE `fixTileSeams()` целиком — UA-сниффинг и `CSS.supports`-чек больше не нужны.
- Удалены классы `html.tile-seam-fallback` / `html.tile-seam-yandex` из CSS.
- Обновлён длинный комментарий-контракт: явный список ЗАПРЕЩЁННОГО + ссылка на ADR.

## Документация
- Создан `obsidian/Decisions/tile-seam-fix.md` — полная история провалов + контракт + чеклист проверки.

## Проверка (обязательно перед merge)
1. Chrome + Firefox + Yandex.Browser.
2. Zoom 10, 18, 22.
3. HiDPI (devicePixelRatio > 1).
4. Светлая И тёмная темы.
5. Метки / Контуры / фото-пины не сломались.

## Файлы
- `viewer/index.html` — CSS (`.leaflet-tile-pane`, `.leaflet-tile`) + удалён JS-IIFE.
- `obsidian/Decisions/tile-seam-fix.md` — новый ADR.
