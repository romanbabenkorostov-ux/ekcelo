---
type: changelog
status: done
date: 2026-06-03
scope: ekcelo-site (внешний репозиторий)
session: claude-session viewer-decomposition
---

# 2026-06-03 · ekcelo-site: декомпозиция viewer'а + YB tile-seam fix

## TL;DR

В репозитории `romanbabenkorostov-ux/ekcelo-site` смерджено в `dev` **10 PR**
поэтапной декомпозиции монолита `viewer/index.html` (12k строк) под будущую
React-миграцию, плюс PR с фиксом белой сетки в YaBrowser.

| PR | Фаза | Что |
|----|------|-----|
| #3 | 0A | удалён `deck-stage.js` (1748 строк dead-кода) |
| #4 | 0B | тулинг: `package.json`, ESLint 9 flat, `tests.yml` CI, папки-якоря |
| #5 | 1 | `viewer/core/`: sha256Hex, escapeHtml, escapeXml, rulerFormatDist + `ui/bridge.js` + 13 тестов |
| #6 | 2 | `viewer/core/nspd-url.js` (DI на Leaflet) + 3 теста |
| #7 | 4 (pure) | `app.js` IIFE→ES-модуль, `core/`: escape/slug/csv/vcard/phases/frame-math + 32 теста |
| #8 | 5 | `admin-encode.html`: inline → `ui/admin-encode.js` (ESM). `document.*` 6→0 |
| #9 | 3 (KMZ-export) | `viewer/core/kml-build.js`: pmToKMLXml, synthStyleXmlFromParsedStyle + 12 тестов |
| #10 | 3 (geo) | `viewer/core/geo.js`: pointInRing, computeCentroid, formatCentroid + 10 тестов |
| #11 | 3 (desc) | `viewer/core/desc.js`: extractCadNum, normalizeDesc, markerDescFromLines + 10 тестов |
| #12 | fix | YB white-grid v2.9.62c: outline-color:var(--map-bg) для `.tile-seam-yandex` |
| #13 | 4 (ui/adapter) | DOM-хелперы: `ui/notifications.js` (showNotice/Chain) + `ui/copy-toast.js` (showCopyToast) + `adapters/clipboard.js` (copyText/fallbackCopy). app.js 63→58 |
| #14 | 4 (ui/adapter) | vCard download + partners render + partners CSV fetch: `ui/vcard-download.js`, `ui/partners-render.js`, `adapters/partners-fetch.js`. app.js 58→51 |
| #15 | 4 (ui) | Contact-modal open/close + [data-close]/Escape bindings → `ui/contact-modal.js`. app.js 51→50 |
| #17 | **P0/2** | `viewer/core/viewmodel.js` — pure фабрика + валидатор по `contracts/api/viewmodel.schema.json` (C4) + 25 тестов |
| #18 | 4 (ui) | `ui/frame-render.js`: updateFrames + FRAME_STOPS из app.js. app.js 50→49. От старта –14 (–22%) |
| #19 | 4 (ui) | `ui/phase-render.js`: updatePhase + updateRail + 30 SVG-refs + $docs из app.js. app.js 49→19. От старта –44 (–70%). Самый крупный single-PR drop. |
| #20 | 4 (ui) | `ui/token-gate.js`: модалка + scroll-attempts + form-submit + header-token Enter. app.js 19→**14**. От старта **–49 (–78%)** |

**Итог:** 17 PR смерджено. **105 unit-тестов** зелёные, ESLint 9 чистый, CI workflow рабочий.

## Контекст-сдвиг (вечер 2026-06-03): ViewModel C4

Параллельно стартовал контракт-пакет `contracts/` в `romanbabenkorostov-ux/ekcelo`
(branch `claude/elegant-gates-eKTMC`, PR #98) — единый источник истины для трёх
команд: parser / backend / ekcelo-site. Ключевое для фронта:

- **C4 ViewModel** (`contracts/api/viewmodel.schema.json`) — единая нормализованная
  форма объекта/лота с 4 характеристиками EKCELO (physical/ownership/geo/temporal).
- **Два адаптера** к одной ViewModel: `kmz→ViewModel` (офлайн / Google Earth Pro)
  и `api→ViewModel` (веб / REST-рендеринг). Картинка идентична.
- **Кросс-матч KMZ↔API** — единый ключ `graph_node_id` (из C1 KMZ) = `node.id`
  (из C4 graph).
- **React-миграция (P2-P3)** — после фаз 0–5: `ui/*.js` → React-компоненты,
  импортирующие `core/`+`adapters/` без изменений. ViewModel-контракт не меняется.

PR #17 — первый кирпич P0/2: `viewer/core/viewmodel.js` готов как pure-канон.
Адаптеры `kmz→ViewModel` (P0/3) и `api→ViewModel` (P1/4) — следующие шаги, но
оба ломающие, нужен браузерный smoke после каждого.

`contracts/` уже vendored в `ekcelo-site` `dev` (кем-то в параллели), `.sync`
файл фиксирует версию 1.0.0 и sha256.

## Метрики `document.*`

| Файл | Старт | Сейчас |
|---|---|---|
| `viewer/index.html` | 442 | 442 (pure-выносы не снижают эту метрику by design) |
| `app.js` | 63 | **14** (–49, **–78%**; за PR #13/14/15/16/19/20 — DOM-подсистемы лендинга) |
| `admin-encode.html` | 6 | **0** (вся DOM-логика уехала в `ui/admin-encode.js`) |

> HANDOFF фиксировал `app.js=74` и `admin-encode.html=15` на дату передачи. На фактической
> ветке `dev` ekcelo-site эти значения = 63 и 6. Расхождение задокументировано в описании
> PR #7 как docs-discrepancy и принято как новый baseline.

## YB white-grid fix (PR #12)

**Проблема:** между плитками карты в Яндекс.Браузере появлялась белая сетка 1px.
Chrome / Firefox не затронуты. Существовавшая защита (v2.9.62/62b) — недостаточна
на отдельных сборках YB.

**Фикс:** одна CSS-строка, гейтированная **только** на YaBrowser:

```css
html.tile-seam-yandex .leaflet-tile { outline-color: var(--map-bg); }
```

**Механизм:** у `.leaflet-tile` уже есть прозрачный 1px-outline (закрывает остаточные
крэки в WebKit). Меняем его цвет на цвет фона карты — соседние плитки рисуют outline
поверх субпиксельной щели тем же цветом, что и pane → щель невидима.

**Гарантии:**
- Гейт `html.tile-seam-yandex` ставится **только** при `/YaBrowser/.test(navigator.userAgent)`.
- Chrome / Firefox байт-в-байт прежние. Нулевая регрессия.
- Геометрия не меняется (outline уже был) → нет катастрофы v2.9.33 с z>maxNativeZoom.

**Следующий уровень** (если щель всё ещё появится): JS-патч `L.GridLayer` с округлением
translate3d до целых пикселей. Это **ломающее** изменение, требует полного smoke по
протоколу.

Полная история подходов и почему остальные провалились — в
`obsidian/Architecture/ekcelo-site-decomposition.md §7`.

## Документация (этот же commit)

Добавлены / обновлены:

| Файл | Что |
|---|---|
| `obsidian/Architecture/ekcelo-site-decomposition.md` | Карта механизмов для devops/repair: слои core/adapters/ui, bridge-паттерн, ESLint flat config, CI, ограничения декомпозиции, TILE SEAM FIX история |
| `obsidian/UserGuide/ekcelo-site-user-flow.md` | Карта user-flow: лендинг → токен → viewer → KMZ/EXIF/XLSX → admin-encode |
| `obsidian/Changelog/2026-06-03-ekcelo-site-decomposition.md` | Этот журнал |

Эти три документа предназначены для ментальной воспроизводимости системы:
- архитектурный — программисту, который никогда не работал с проектом, после прочтения может
  поломать что угодно с пониманием последствий;
- user-guide — оператору / новому участнику, после прочтения может пройти любой UX-сценарий
  от ссылки до экспорта.

## Что осталось вне scope этой сессии

Высокорисковые DOM-подсистемы, требующие либо браузерного smoke после каждого PR,
либо переустройства порядка инициализации:

- **Фаза 3 (viewer):** role-state (immediate-call `let __ekceloRole = resolveRole()` не
  дружит с deferred-bridge), NSPD-tile-layer обвязка, KMZ-import (DOMParser),
  EXIF (exifr/piexif адаптеры), XLSX row-builders (цепочка `_classifyObjectType`,
  `_XLSX_TYPE_LABELS`, `_RE_CENTROID`), Leaflet map init / UI.
- **Фаза 4 (лендинг):** DOM-подсистемы app.js — notifications, clipboard, copy-toast,
  partners-render, vCard-download, frame/phase-render, scroll-controller, token-gate UX.
  Они снизят `app.js`'у метрику `document.*` с 63.

Для каждой из этих подсистем нужен либо браузерный smoke после merge в `dev`, либо
крупный preplanning (порядок инициализации, перестройка bridge'а в активный bootstrap).

## Артефакты

- Все 10 PR: <https://github.com/romanbabenkorostov-ux/ekcelo-site/pulls?q=is%3Apr+merged+>
- `dev` HEAD: `b57526e` (после PR #12).
- `main` отстаёт от `dev` на 10 коммитов — владелец делает `dev→main` merge вручную
  после прода-smoke по `ekcelo-site/docs/VERIFICATION_PROTOCOL.md`.

## Чек-листы перед `dev → main`

Минимум по `ekcelo-site/docs/VERIFICATION_PROTOCOL.md` §1.1–1.3:
- viewer: 12+ пунктов (Chrome + Firefox + YaBrowser),
- лендинг: 6 пунктов,
- admin-encode: 3 пункта.

Дополнительно, для PR #12:
- YaBrowser: открыть `/viewer/?t=<токен>` на светлой и тёмной теме, zoom 10/18/22 →
  убедиться, что белой сетки между тайлами нет.
- Chrome + Firefox: смок-проверка, что НИЧЕГО не изменилось (т.к. гейт `tile-seam-yandex`
  не ставится — должно быть полностью эквивалентно).

## Ссылки

- Reference-ветка `claude/site-decomposition-handoff` в `ekcelo-site`:
  `docs/ARCHITECT_HANDOFF.md`, `docs/VERIFICATION_PROTOCOL.md`,
  `docs/VIEWER_MONOLITH_INVENTORY.md`, `docs/decisions/ADR-001-viewer-layers.md`.
- ADR-001 (ekcelo): `obsidian/Decisions/ADR-001-etp-profile-extension.md` — соседний контекст.
- CONTRACT_KMZ: `obsidian/CONTRACT_KMZ.md` — формат KMZ-файлов viewer'а.
