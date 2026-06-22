# 2026-06-22 — FE-2 интерактивный граф + kmz→ViewModel адаптер

## Что сделал

1. **kmz→ViewModel адаптер** (`adapters/kmz.ts`) — порт KMZ-парсера:
   ZIP-распаковка (fflate) + KML-парсинг (DOMParser) → ViewModel идентичной
   api-форме. Офлайн-режим drag-drop KMZ.
2. **Интерактивный SVG-граф** (`ui/graph-svg.ts`) — замена текстового из FE-1.
   Радиальный layout, hover-подсветка, клик-навигация, a11y.
3. **main.ts** — двух-адаптерный режим: объект из KMZ или из api рисуется
   одним UI (DoD SPEC_frontend).

## Файлы
- ✨ `ekcelo-site/src/adapters/kmz.ts` — parseKmzBytes/parseKmzFile/
  parseKmlText/kmzToViewModel/kmzToGraph.
- ✨ `ekcelo-site/src/ui/graph-svg.ts` — renderGraphSvg.
- ✏️ `ekcelo-site/src/main.ts` — KMZ drop + источник-бейдж + SVG-граф.
- ✏️ `ekcelo-site/src/styles.css` — стили SVG-графа + mode-bar.
- ✏️ `ekcelo-site/package.json` + `package-lock.json` — +fflate.
- ✨ `ekcelo-site/tests/kmz-adapter.test.ts` — 14 тестов (реальный sample).
- ✨ `ekcelo-site/tests/graph-svg.test.ts` — 7 тестов.
- ✨ `ekcelo-site/tests/fixtures/sample.kmz` — реальный sample от парсера.
- ✨ `obsidian/Architecture/fe-2-graph-kmz-adapter.md` — снимок.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — FE-2 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live.

## Тесты
- **Frontend:** 50 vitest passed (29 FE-1 + 21 FE-2).
- **TypeScript strict:** 0 ошибок.
- **ESLint:** 0 warnings.
- **Backend:** 495 без изменений (фронт изолирован).

## Решения

- **fflate для ZIP**, не JSZip. fflate в 5× меньше (8KB vs 40KB),
  tree-shakeable, синхронный API (`unzipSync`). KMZ обычно <5MB — sync ок.
- **Нативный DOMParser**, не xml-парсер-библиотека. KML — XML, браузер
  парсит нативно. Адаптер кросс-средовой: работает в браузере И в happy-dom.
- **Кросс-средовые quirks happy-dom обойдены** (важно для CI):
  - CDATA → comment-node (type 8): `cdataText` собирает text/cdata/comment.
  - `.children` обрывается на `atom:author`: extract_date ищется глобально.
  - tagName UPPERCASE: все сравнения case-insensitive.
  - getElementsByTagName (не NS-вариант, который happy-dom не поддерживает).
  В реальном браузере всё это работает штатно; обходы безвредны.
- **geo — главная ценность KMZ-адаптера.** api не отдаёт geometry до C3.3,
  а KMZ несёт координаты. Так офлайн-режим показывает геометрию там, где
  online ещё пусто. Это оправдывает «два адаптера» из SPEC.
- **graph_node_id = node.id инвариант.** KMZ узлы и backend-граф используют
  один ключ → клик/навигация работают в обоих режимах.
- **SVG-граф без D3/cytoscape.** Радиальный layout детерминированный (по
  слоям), достаточно для FE-2. Тяжёлые граф-библиотеки — overkill пока
  графы небольшие. Можно ввести позже без смены контракта данных.
- **Реальный sample KMZ в фикстурах.** Тесты парсят настоящий вывод парсера
  (`demo-multi-extract_2026-01-15.kmz`), не синтетику — ловит расхождения
  формата раньше.
- **graph.ts (текстовый) оставлен.** Не используется в main, но его тесты
  (FE-1) проходят. Удалять не стал — безвреден, может пригодиться как
  print-friendly fallback.

## Канал доставки
- Sandbox-proxy блокирует push — zip-handoff (после merge #121).
- npm install (fflate) воспроизводим — package-lock закоммичен.

## Следующий шаг (FE-3)
1. **Карта** — Leaflet/MapLibre или Google Earth embed. Рендер geo.geometry
   (Polygon) + center на карте.
2. **3D extrude** — z_meters_top для зданий.
3. **UI грантов** — `GET /grants/me` + формы делегирования/шеринга (C6).
4. **Multi-KMZ timeline** — переключение дат выписок.
