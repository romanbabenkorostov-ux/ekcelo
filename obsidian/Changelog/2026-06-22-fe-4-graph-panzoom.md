# 2026-06-22 — FE-4: pan/zoom графа владения

## Задача
SVG-граф (FE-2) был статичным — не двигался и не масштабировался. При большом
графе (api-режим, много бенефициаров) узлы не помещались / накладывались. Нужен
pan + zoom.

## Что сделал
- **Вьюпорт-обёртка.** Всё содержимое графа (рёбра + узлы) теперь в одном
  `<g class="graph-viewport">`; pan/zoom = `transform: translate() scale()` на
  нём, узлы не перерисовываются.
- **Фон-хитзона.** Прозрачный `<rect class="graph-bg">` на весь viewBox —
  стабильная цель для перетаскивания (на пустых местах svg узлов нет).
- **Zoom** колесом к курсору (точка под курсором остаётся на месте),
  ограничение scale 0.3..5.
- **Pan** перетаскиванием фона (pointer events, 1:1 в единицах viewBox через
  `getBoundingClientRect`). Узлы тянуть нельзя — это конфликтовало бы с
  кликом-навигацией (`onBackground` проверяет target = bg/svg).
- **Reset** — двойной клик по фону → `translate(0 0) scale(1)`.
- Курсор `grab` / `grabbing`, `touch-action: none` (тач-драг без скролла
  страницы).

## Файлы
- ✏️ `ekcelo-site/src/ui/graph-svg.ts` — bg + viewport, `enablePanZoom()`.
- ✏️ `ekcelo-site/src/styles.css` — курсоры, `.graph-bg`.
- ✨ `ekcelo-site/tests/graph-svg.test.ts` — +5 тестов (вьюпорт, zoom, pan,
  reset, узел-не-паннит).

## Тесты
- **79 vitest** (74 + 5). tsc strict 0. `npm run lint` (src) 0.
- Build: index 29.17 КБ (gz 12.0) + leaflet chunk lazy.

## Заметки для тест-среды
- happy-dom: `getBoundingClientRect` → width 0 → fallback 1:1 (ux/uy=1), поэтому
  pan-дельта в тесте = client-дельте. `setPointerCapture` обёрнут в try/catch
  (нет pointerId у MouseEvent). Zoom к курсору в браузере точный, в тесте —
  относительно (0,0), что достаточно для проверки scale.

## Канал доставки
zip-handoff (sandbox-proxy блокирует push).
