---
type: architecture
status: active
date: 2026-06-03
scope: ekcelo-site (отдельный репозиторий)
---

# ekcelo-site: декомпозиция viewer'а / лендинга / admin'а

> **Контекст.** Этот документ описывает архитектурные механизмы статического сайта `ekcelo.ru`
> (репо `romanbabenkorostov-ux/ekcelo-site`), которые были введены в ходе декомпозиции
> монолитного `viewer/index.html` (12k строк) под будущую React-миграцию. Документ написан
> для программистов по эксплуатации и ремонту: каждый механизм должен быть ментально
> воспроизводим — от того, что во что грузится, до того, как порядок скриптов на странице
> гарантирует корректное состояние.
>
> Эта документация **не дублирует** `ekcelo-site/docs/ARCHITECT_HANDOFF.md` (formal hand-off
> spec), а описывает, **что реально лежит в `dev`** после серии PR #3–12. Лежит — значит
> работает в проде после очередного `dev→main` мерджа.

## 1. Структура репозитория `ekcelo-site` (после декомпозиции)

```
ekcelo-site/
├── index.html              # Лендинг (scrollytelling)
├── app.js                  # Контроллер лендинга — ES-модуль (PR #7)
├── styles.css              # Стили лендинга
├── token-gate.html         # Резервная redirect-страница (минимум)
├── tokens.js               # Token API (window.Ekcelo, классический <script>)
├── admin-encode.html       # Генератор токенов (+ inline qrcode lib)
├── viewer/
│   ├── index.html          # EGRN-просмотрщик (монолит ~12k строк)
│   ├── sw.js               # Service Worker (кэширует только nspd.gov.ru tile'ы)
│   └── core/               # Pure ES-модули viewer'а
│       ├── hashing.js          # sha256Hex (PR #5)
│       ├── escape.js           # escapeHtml/escapeXml (PR #5)
│       ├── format.js           # rulerFormatDist (PR #5)
│       ├── nspd-url.js         # nspdWmsUrl(id, coords, crs, pointFn) (PR #6)
│       ├── kml-build.js        # pmToKMLXml, synthStyleXmlFromParsedStyle (PR #9)
│       ├── geo.js              # pointInRing, computeCentroid, formatCentroid (PR #10)
│       └── desc.js             # extractCadNum, normalizeDesc, markerDescFromLines (PR #11)
├── viewer/ui/
│   └── bridge.js           # ES-модуль: импортирует viewer/core/, регистрирует
│                           # на window под легаси-именами (_escapeHtml и т.д.)
├── core/                   # Pure ES-модули лендинга (общие с viewer в перспективе)
│   ├── escape.js           # escapeHtml/escapeAttr (PR #7)
│   ├── slug.js             # asciiSlug (PR #7)
│   ├── csv.js              # parseCSV (PR #7)
│   ├── vcard.js            # vcEscape, buildVCard (PR #7)
│   ├── phases.js           # getPhase (PR #7)
│   └── frame-math.js       # frameLerp (PR #7)
├── ui/
│   └── admin-encode.js     # UI-контроллер admin-encode.html (PR #8)
├── tests/
│   ├── viewer/             # Unit-тесты viewer/core/* (39 тестов)
│   └── landing/            # Unit-тесты core/* (32 теста)
├── package.json            # type:module, devDeps только
├── eslint.config.mjs       # ESLint 9 flat config (ADR-001 граница)
├── .github/workflows/
│   ├── deploy.yml          # actions/deploy-pages@v4 (main → GitHub Pages)
│   └── tests.yml           # node --test + eslint@9 на PR/push
├── worker.js               # Cloudflare Worker (отдельный деплой, в задаче не трогаем)
├── infra/cloudflare-worker/worker.js   # ← идентичная копия
└── deck-stage.js           # УДАЛЁН в PR #3 (dead code)
```

## 2. Слои `core / adapters / ui` (ADR-001 ekcelo-site)

> Это не код-стандарт «для красоты», а машинно-проверяемая граница. Несоблюдение
> ловит CI через ESLint `no-restricted-globals`.

| Слой | Каталог | Что внутри | Что **запрещено** |
|---|---|---|---|
| **core** | `viewer/core/`, `core/` | Чистые функции / иммутабельные структуры. Принимают данные → возвращают данные. | `document`, `window`, `navigator`, `location`, `localStorage`, `sessionStorage`, `fetch`, `XMLHttpRequest`, `alert`, `confirm`, `prompt` |
| **adapters** | `viewer/adapters/`, `adapters/` | Мост к внешнему миру: fetch, storage, File System Access, Web Crypto, обёртки над CDN-библиотеками (exifr, piexifjs, XLSX, JSZip). | UI-логика, рендер |
| **ui** | `viewer/ui/`, `ui/` | Тонкая DOM-обёртка: подписывается на core-state, рендерит. Обработчики кликов, Leaflet-обвязка, bridge для совместимости. | Бизнес-логика, нормализация данных |

Запрет `core/` проверяется через `eslint.config.mjs`:

```js
{
  files: ['viewer/core/**/*.js', 'core/**/*.js'],
  rules: {
    'no-restricted-globals': ['error',
      'document','window','navigator','location',
      'localStorage','sessionStorage',
      'fetch','XMLHttpRequest','alert','confirm','prompt'],
  },
}
```

Тесты `core/` — на встроенном `node:test` (Node 20, без npm-зависимостей в рантайме).

## 3. Bridge-паттерн (как переехавшие функции работают в монолите)

> Это центральный механизм. Без понимания этого пункта поломать декомпозицию — дело
> двух минут.

Старый `viewer/index.html` использует классические объявления функций:

```js
function _escapeHtml(s){ … }   // → window._escapeHtml автоматически
```

В классическом `<script>`-блоке top-level `function NAME` создаёт **глобал** на `window`.
Когда мы переносим функцию в `viewer/core/escape.js`, объявление в монолите удаляется,
заменяется якорным комментарием. Внутри монолита остаются вызовы `_escapeHtml(...)` —
они продолжают резолвиться через `window`.

`viewer/ui/bridge.js` ставит эти имена обратно на `window` из ES-модулей:

```js
import { escapeHtml, escapeXml } from '../core/escape.js';
import { sha256Hex } from '../core/hashing.js';
// … и т.д.

window._escapeHtml = escapeHtml;
window._escapeXml = escapeXml;
window.__ekceloSha256Hex = sha256Hex;
// … для всех вынесенных функций
```

В конце `<body>` viewer/index.html стоит:

```html
<script type="module" src="./ui/bridge.js"></script>
```

### Когда bridge готов?

| Тип скрипта | Когда исполняется | Можно ли там вызывать `window._escapeHtml`? |
|---|---|---|
| Классический `<script>` в `<head>` (inline) | Сразу при парсинге | **НЕТ** (bridge ещё не загружен) |
| `<script defer>` в `<head>` | После парсинга HTML, в порядке HTML | **НЕТ** (bridge — модуль, может быть позже) |
| `<script type="module">` | После парсинга HTML, в порядке HTML | **ДА** (если bridge — раньше в DOM) |
| Внутри функции, вызываемой обработчиком клика | На user-action | **ДА** (load + bridge давно готовы) |
| Внутри `loadXLSX`, `loadKMZFromFile` и пр. | На user-action / async | **ДА** |

**Поэтому** при выборе кандидата на вынос в `core/` обязательно проверяем: **где** функция вызывается. Если только из user-action / post-load — bridge работает. Если есть immediate-call при парсинге — **нельзя выносить через bridge** (см. п.4 про role-state).

### Что НЕ через bridge

`tokens.js` использует свой паттерн: классический `<script src="tokens.js">` ставит `window.Ekcelo` напрямую (IIFE с `global.Ekcelo = {…}`). Этот файл **не трогается**, остаётся классическим.

## 4. Известные ограничения декомпозиции

### 4.1. `resolveRole` / `ROLE_CFG` — не bridge-совместимы

В `viewer/index.html` строка ~1624: `let __ekceloRole = resolveRole();`. Это вызов **во
время парсинга** классического `<script>` в `<head>`. Если перенести `resolveRole`
в `viewer/adapters/role.js` и подцепить через bridge — bridge ещё не загружен,
будет `ReferenceError`.

**Решение** (отложено): переписать инициализацию `__ekceloRole` так, чтобы её делал сам
bridge (т.е. bridge становится не пассивным регистратором глобалов, а bootstrap-инициатором
role-state). Это уже не «механическая декомпозиция», а **переустройство порядка инициализации**,
и его без браузерного smoke в проде делать нельзя.

### 4.2. XLSX row-builders — цепочка зависимостей

`_xlsxRowFromCp`, `_xlsxRowFromParsedPm`, `_xlsxObjectType` тянут за собой
`_classifyObjectType`, `_XLSX_TYPE_LABELS`, `_RE_CENTROID`, `_stripCentroidFromDesc`.
Не получится вынести 1:1 без перетаскивания call-графа. Нужен отдельный refactor.

### 4.3. `_parseDescPairs` — читает runtime-глобал

`_parseDescPairs` (line ~6673) читает `_kmzAttachBlobs` — runtime-глобал, который наполняется
во время KMZ-импорта. Эта функция **не вынесена** в `core/desc.js`; она остаётся в
viewer/index.html и вызывает `normalizeDesc` через `window._normalizeDesc` (bridge).

## 5. ESLint flat config

ESLint 9 требует `eslint.config.mjs` (flat config), **не** `.eslintrc.json`. Структура:

```js
export default [
  { ignores: [/* node_modules, frames, uploads, tokens.js, worker.js, viewer/sw.js, *.html */] },
  { files: ['viewer/core/**/*.js', 'core/**/*.js'],
    languageOptions: { sourceType: 'module', /* ограниченные globals */ },
    rules: { 'no-restricted-globals': ['error', /* запрет document/window/etc */] } },
  { files: ['viewer/ui/**', 'viewer/adapters/**', 'ui/**', 'adapters/**'],
    languageOptions: { sourceType: 'module', globals: browserGlobals } },
  { files: ['tests/**/*.test.mjs'],
    languageOptions: { sourceType: 'module', globals: nodeGlobals } },
  { files: ['*.js'],  // app.js
    languageOptions: { sourceType: 'module', globals: browserGlobals } },
];
```

`tokens.js`, `worker.js`, `viewer/sw.js`, `deck-stage.js` (если кто-то его восстановит)
в `ignores` — это **классические скрипты** или **vendored**.

## 6. CI workflow

`.github/workflows/tests.yml`:
- Триггер: `pull_request: [dev, main]` + `push: branches: [main]`.
- Job: Node 20, `node --test tests/**/*.test.mjs` + `npx -y eslint@9 . --max-warnings 0`.
- Если тестов ещё нет — корректно скипается с сообщением.

Существующий `.github/workflows/deploy.yml` — **не трогается**. Он деплоит `main` →
GitHub Pages через `actions/deploy-pages@v4`. Триггер: push в `main`.

## 7. TILE SEAM FIX (белая сетка на карте)

> Двухлетняя история костылей. **Не трогать без понимания.**

### Проблема

При двух тайлах OSM/Esri, отрисованных рядом в Leaflet, между ними появляется белая
1px-сетка. Только на Blink-движках (Chrome / Yandex / Edge). Firefox чист.

### Краеугольные пять правил (v2.9.53/56/57)

```css
.leaflet-tile-pane {
  background: var(--map-bg);   /* tile-цвет → прячет subpixel-hairline */
  filter: var(--map-filter);   /* ОДИН композитный слой для всей панели */
  transform: translateZ(0);    /* свой 2D composite */
}
.leaflet-container img.leaflet-tile {
  mix-blend-mode: plus-lighter; /* Leaflet PR #8891, Chromium bug 600120 */
}
.leaflet-tile {
  filter: none !important;     /* убирает per-tile composite слои */
  outline: 1px solid transparent;  /* закрывает остаточные крэки в WebKit */
}
```

### YaBrowser branch (v2.9.62/62b/62c)

Старые сборки YB (без `mix-blend-mode: plus-lighter`):
```css
html.tile-seam-fallback .leaflet-tile-pane { isolation: isolate }
html.tile-seam-fallback .leaflet-tile { outline-color: var(--map-bg) }
```

Современные YB (plus-lighter поддерживается, но щель остаётся):
```css
html.tile-seam-yandex .leaflet-tile-pane { will-change: transform; isolation: isolate }
html.tile-seam-yandex .leaflet-tile { outline-color: var(--map-bg) }   /* PR #12 / v2.9.62c */
```

JS-детектор (внутри viewer/index.html, ~line 1819):
```js
const ua = navigator.userAgent || '';
const isBlink = /Chrome|Chromium|YaBrowser/.test(ua) && !/Firefox|FxiOS/.test(ua);
const hasPlusLighter = CSS.supports('mix-blend-mode', 'plus-lighter');
if (isBlink && !hasPlusLighter) html.classList.add('tile-seam-fallback');
if (/YaBrowser/.test(ua))       html.classList.add('tile-seam-yandex');
```

### Если щель ВСЁ ЕЩЁ появится на новом YB

**Следующий уровень — JS-патч на `L.GridLayer`** (округление translate3d до целых
пикселей). Это **ломающее** изменение: меняет геометрию плиток. Требует полного smoke
по `ekcelo-site/docs/VERIFICATION_PROTOCOL.md`: Chrome + Firefox + YaBrowser, zoom 10/18/22,
HiDPI, светлая+тёмная темы, маркеры + контуры + фото-пины.

**Не делать как первый шаг.** CSS-фикс v2.9.62c должен покрывать. Если не покрыл —
сначала собрать диагностику в YB (DevTools → screenshot, zoom level, DPR), потом
решать про JS-патч.

### Что **нельзя** делать (история провалов)

| Версия | Что пробовали | Почему сломало |
|---|---|---|
| v2.9.30 | `filter` на `.leaflet-div-icon` | Не тот target |
| v2.9.32 | `mergeOptions {iconUrl:''}` | Сломало фото-маркеры |
| v2.9.33 | `width:257px; margin:-1px; transform:scale(1.02)` на pane | На z>maxNativeZoom Leaflet upscale'ит до 2048×2048, а width:257px ужимает bitmap → **гигантские белые квадранты** на z22 |
| v2.9.50 | `will-change` / `backface-visibility` / `transform` на **плитках** | Создавало БОЛЬШЕ separate compositing layers, не меньше |

## 8. Тесты (как добавлять новые)

Каждый pure-вынос в `core/` сопровождается мин. 2 тестами в `tests/viewer/<name>.test.mjs`
или `tests/landing/<name>.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { myFn } from '../../viewer/core/my-module.js';

test('myFn: happy path', () => { /* … */ });
test('myFn: edge case (null/undefined)', () => { /* … */ });
```

Запуск локально:
```bash
node --test tests/**/*.test.mjs
```

CI прогоняет то же самое + ESLint. Если `node --test` не находит файлов —
корректно скипается (см. tests.yml).

## 9. Полный SOP «как делать новый PR на ekcelo-site»

Канон-источник — `ekcelo-site/docs/ARCHITECT_HANDOFF.md` и `VERIFICATION_PROTOCOL.md`
на reference-ветке `claude/site-decomposition-handoff` (не мерджится в dev).

Минимум:
1. Branch от `dev`: `arch/phase-N-<name>`.
2. Один логически связанный сдвиг (не смешивать фазы).
3. Локально: `npx -y eslint@9 . --max-warnings 0` + `node --test tests/**/*.test.mjs` зелёные.
4. Сверить метрики `document.*` в трёх файлах: `viewer/index.html` (старт 442), `app.js` (старт 63 на dev), `admin-encode.html` (после PR #8 = 0).
5. PR в `dev`, описание — по шаблону §A HANDOFF.
6. После merge в `dev`: владелец прогоняет smoke по `VERIFICATION_PROTOCOL.md` §1.1–1.3, мерджит `dev → main`. Прод-деплой через `actions/deploy-pages@v4`.

## 10. Связь с другими репозиториями

`ekcelo-site` живёт **отдельно** от:
- `romanbabenkorostov-ux/ekcelo` (parser + orchestrator + obsidian) — этот репозиторий.
  Обсидиан-документация лежит здесь, в `obsidian/`.
- Cloudflare Worker (`ekcelo-proxy.roman-babenko-rostov.workers.dev`) — деплоится
  вручную с Cloudflare Dashboard, исходник в `ekcelo-site/worker.js` +
  `ekcelo-site/infra/cloudflare-worker/worker.js` (идентичные копии).
  В рамках декомпозиции **не трогается**.

Контракт обмена данными между парсером и viewer'ом — `ekcelo-site/viewer/`
читает KMZ-файлы по `obsidian/CONTRACT_KMZ.md` (он же в `docs/` соответствующих
веток парсера).
