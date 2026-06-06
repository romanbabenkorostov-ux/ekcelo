---
№: 030
From: owner
To: parser, viewer, ekcelo-backend
Date: 2026-06-06
Re: PR #3..#23 в `ekcelo-site`; ветка `claude/magical-mccarthy-3ZyU4` в `ekcelo` (lab, не мерджена); `contracts/` v1.0.0
Status: open · информативный (status-post; ack не обязателен)
---

# Status: где мы находимся в декомпозиции viewer (на 2026-06-06)

Цель поста — дать любой следующей AI-сессии (parser / viewer / backend)
**одну точку входа**, чтобы не переоткрывать сделанное. Сводка на 2026-06-06.

## Сделано в ekcelo-site (PR #3..#23 смержены в dev)

Phase 0 — тулинг и удаление мёртвого кода:
- PR #3 — удалён `deck-stage.js` (1748 строк, 0 ссылок).
- PR #4 — `package.json` + ESLint flat config + `tests.yml` + папки-якоря `core/adapters/ui` для viewer и landing.

Phase 1 — pure-выносы из `viewer/index.html`:
- PR #5 — `sha256Hex`, `escapeHtml`, `escapeXml`, `rulerFormatDist` → `viewer/core/{hashing,escape,format}.js` + `viewer/ui/bridge.js` (модуль-мост на `window`).

Phase 2 — функции с лёгкими внешними зависимостями:
- PR #6 — `_nspdWmsUrl` → `viewer/core/nspd-url.js` с DI на Leaflet (`L.CRS.EPSG3857`).
- `resolveRole()` НЕ вынесен (DOM-coupled, ждёт фазу 3).

Phase 3 — частично, только pure-кластеры:
- PR #9 — KMZ-export pure builders → `viewer/core/kml-build.js` (`pmToKMLXml`, `synthStyleXmlFromParsedStyle`).
- PR #10 — геометрия → `viewer/core/geo.js` (`pointInRing`, `computeCentroid`, `formatCentroid`).
- PR #11 — описания → `viewer/core/desc.js` (`extractCadNum`, `normalizeDesc`, `markerDescFromLines`).

Phase 4 — лендинг (`app.js` IIFE → ES-модули):
- PR #7 — `app.js` IIFE → ES-модуль + pure-хелперы в `core/{csv,escape,frame-math,phases,slug,vcard}.js`.
- PR #13 — DOM-хелперы → `ui/notifications.js`, `ui/copy-toast.js`, `adapters/clipboard.js`.
- PR #14 — vCard + partners + CSV → `ui/vcard-download.js`, `ui/partners-render.js`, `adapters/partners-fetch.js`.
- PR #15 — `ui/contact-modal.js`.
- PR #18..#22 — frame-render, phase-render, token-gate UX, scroll-controller, text-reveal, click delegates, CTAs, preload.

Phase 5 — admin:
- PR #8 — `admin-encode.html` inline-скрипт → `ui/admin-encode.js` (ES-модуль).

Сверх плана (контракты и виртуальная модель):
- PR #16 — vendor `contracts/` v1.0.0 (Consistency Target) из `ekcelo@main` в `ekcelo-site` через `contracts/.sync` + sha256 pin. Покрыты C1..C6 (KMZ wire, DB §1–§6, Bundle, REST+ViewModel, Lot, Roles).
- PR #17 — `viewer/core/viewmodel.js` — фабрика + валидатор по C4 schema (`contracts/api/viewmodel.schema.json`).

Bug fixes:
- PR #12, #23 — Yandex Browser white-grid (v2.9.62c, v2.9.62d).

## Метрики сейчас (фактические)

| Файл | Строк | `document.*` | `getElementById` | `addEventListener` | `innerHTML` |
|---|---|---|---|---|---|
| `viewer/index.html` | 11 884 (было 11 992) | **442** (без изменений) | 291 | 78 | 53 |
| `app.js` (landing) | 221 (было 746) | **2** (было 74) | — | — | — |
| `admin-encode.html` | 118 (было 236) | **0** (было 15) | — | — | — |

Что это значит:
- **Лендинг и админ — закрыты.** Phase 4 и 5 практически выполнены, остатки `document.*` минимальны.
- **`viewer/index.html` 442 — без изменений** не потому что работа не велась, а потому что вынесены **только pure-функции** (которые `document.*` не использовали). Реальное снижение начнётся с Phase 3 DOM-coupled извлечений (см. ниже).

## Что НЕ сделано (план для следующих PR в ekcelo-site)

Phase 3 — DOM-coupled подсистемы `viewer/index.html`:

| Подсистема | Куда выносить | Прибл. количество `document.*` |
|---|---|---|
| Theme / role-state | `viewer/adapters/role.js` + `viewer/ui/role-toggle.js` | ~30 |
| NSPD-tiles слой | `viewer/adapters/nspd-tiles.js` + `viewer/ui/cadastre-controls.js` | ~60 |
| KMZ/KML импорт | `viewer/adapters/kmz-import.js` (JSZip) | ~80 |
| EXIF чтение/запись | `viewer/adapters/exif.js` (exifr, piexif) | ~50 |
| XLSX импорт/экспорт | `viewer/adapters/xlsx.js` (xlsx-js-style) | ~40 |
| Leaflet карта + tile-layers | `viewer/ui/map.js` | ~80 |
| Service worker cache | `viewer/core/sw-cache.js` + `viewer/sw.js` тонкий wrapper | ~10 |

Итого: ~350 `document.*` распределены по 7 подсистемам. После их выноса метрика
должна упасть с 442 до ~90 (остаточная UI-обвязка).

Phase 1b — параллельно: после вынесения функции тело старого определения
в `viewer/index.html` должно заменяться комментарием-якорем (паттерн уже
применяется, см. строки 1656, 1947 — `// Регистрируется на window через
viewer/ui/bridge.js`). Без этого старая функция шадоит bridge через function
declaration.

Phase 6 — React-port (НОВАЯ ФАЗА, после Phase 3):
- Когда `viewer/index.html` похудеет до ~5000 строк и почти весь код будет в
  `viewer/core/` + `viewer/adapters/` + `viewer/ui/` — открыть новый ADR
  (свободные номера в `ekcelo`: ADR-004 и далее) «viewer React migration»,
  предложить framework (React vs SolidJS), подготовить React-обёртки над
  текущими `ui/*.js`.

## Открытый долг по документации (важно)

На ветке `claude/magical-mccarthy-3ZyU4` (lab, **не мерджена**) подготовлены:
- `obsidian/Decisions/ADR-002-db-portability.md` (концепция).
- `obsidian/Decisions/ADR-003-viewer-layers.md` (концепция).
- `obsidian/Database/dialect-portability.md`.
- `obsidian/Architecture/viewer-layers.md`.
- `.claude/skills/db-portability/`, `.claude/skills/viewer-layers/`.

На `main` уже заняты ADR-002 (`parser-checko-integration-policy`) и ADR-003
(`temporal-v2-ownership`). Поэтому концепции из лаб-ветки должны
**пере-номероваться при мердже**:
- db-portability → **ADR-004**.
- viewer-layers → **ADR-005**.

Если кто-то возьмётся за это — отдельным PR `shared/adr-004-005-adoption`,
с переименованием файлов и обновлением скиллов. Не блокер декомпозиции.

## Что НЕ нужно делать

- Не нужно переоткрывать концепцию слоёв `viewer/core/adapters/ui` — она работает,
  ESLint `no-restricted-globals` в `viewer/core/**` уже проверяет границу
  (см. `eslint.config.mjs` в `ekcelo-site`).
- Не нужно менять `contracts/`-механизм. Он работает, sha256 pin держит
  консистентность трёх репо.
- Не нужно создавать `ekcelo-shared`. Существующий `contracts/` уже синкается
  во все три репо.
- Не нужно трогать `worker.js`, `infra/cloudflare-worker/` — отдельная инфра.
- Не нужно трогать SEO, CNAME, sitemap, yandex-verification.
- Не нужно повторять Phase 0, 1, 2, 4, 5 — закрыты.

## Что нужно от каждой команды СЛЕДУЮЩИЙ ШАГ

**viewer-team (или AI-сессия для ekcelo-site):**
- Взять одну из 7 оставшихся подсистем Phase 3 (рекомендую начать с **role-state**
  — самая компактная, блокирует токен-логику и нужна другими подсистемами).
- Открыть PR `arch/phase-3-role` от `dev`.
- Smoke по чеклисту (`docs/VERIFICATION_PROTOCOL.md` в `ekcelo-site` — если ещё
  не создан, создать со списком 12 пунктов viewer + 6 landing + 3 admin).
- Метрика `document.*` в `viewer/index.html` должна снизиться.

**parser-team:**
- Никаких блокеров, продолжает по spec-PR-first.
- Если эмитятся новые поля в C1/C4 — bump `contracts/CHANGELOG.md` + sha256 в
  `.sync` всех трёх репо (через `contracts/PACKAGE.md` §Sync mechanism).

**owner:**
- Закрыть obsolete артефакты в `ekcelo-site`:
  - PR #2 (Draft handoff) — заменён реальной работой PR #3..#23. **Close без merge.**
  - Ветка `claude/site-decomposition-handoff` — удалить после close PR #2.
- В `ekcelo`:
  - Ветка `claude/magical-mccarthy-3ZyU4` — рекомендую **оставить** как историческую
    (lab-прототип; в main не мерджилась; концептуальное содержание зарегистрировано
    в этом посте). Если беспокоит шум в `git branch -a` — можно удалить, концепции
    перенесены в раздел «Открытый долг по документации» выше.

## Smoke checklist (рекомендация для `ekcelo-site/docs/VERIFICATION_PROTOCOL.md`)

Viewer (главный, обязательный, 12+ пунктов):
- `/viewer/` без параметров → `view`-режим, карта рендерится.
- `/viewer/?t=<тестовый_токен>` → токен декодируется, проект загружается.
- NSPD-кадастр включается, тайлы накладываются.
- KMZ-импорт работает, маркеры на карте.
- EXIF-фото в popup'е.
- `view` → кнопки экспорта скрыты.
- `pro` через невидимую зону + пароль `редактировать` → экспорт активен.
- KMZ-экспорт → файл скачивается и открывается обратно.
- XLSX-экспорт → стили строк 1/2/3.
- DevTools Console: без ошибок.
- Service worker зарегистрирован (DevTools → Application).
- Кэш NSPD-тайлов работает.

Лендинг (6+ пунктов): scroll-анимация 5 фаз; контакт-модалка после 5 wheel-попыток на дне; copy email/phone → toast; vCard download; token-input → редирект в viewer.

Admin (3+ пункта): форма; URL → 3 токена + 3 QR; copy token.

## Метрики, которые должны падать в каждом следующем PR

- `viewer/index.html`: 442 → ... (цель к концу Phase 3: ~90).
- `app.js`: 2 (уже).
- `admin-encode.html`: 0 (уже).

## Где живут постоянные источники истины

- **Контракты** (C1–C6): `contracts/` (vendored, sha256 pin). Источник: `ekcelo/contracts/`.
- **CORRESPONDENCE** (этот журнал): только `ekcelo/docs/CORRESPONDENCE/`. **Не** синхронизирован в `ekcelo-site` / `ekcelo-parser`. Sessions других репо должны клонировать `ekcelo` в боковую папку, либо дождаться расширения `.sync`-механизма под correspondence/.
- **Obsidian KB**: только `ekcelo/obsidian/`.
- **ADR** (формальные): `ekcelo/obsidian/Decisions/`. Текущие номера: ADR-001 (etp-profile-extension), ADR-002 (parser-checko-integration-policy), ADR-003 (temporal-v2-ownership). Свободные: ADR-004+.

## Открытое предложение (опционально, не блокер)

Расширить `contracts/.sync` под **mirror последних N постов CORRESPONDENCE** в каждый из синкаемых репо. Тогда любая AI-сессия любой команды видит свежие посты автоматически. Требует:
- v1.1.0 bump `contracts/`.
- GitHub Action в `ekcelo`, который при merge нового поста CORRESPONDENCE собирает sha256-pin и пушит mirror в `ekcelo-site/contracts/correspondence/` + `ekcelo-parser/contracts/correspondence/`.

Не делать в этом PR. Открыть как 031 (proposal-пост) после ack на 030.

---

**END 030.**
