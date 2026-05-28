# ADR-003: viewer/core/adapters/ui — разделение слоёв

**Date:** 2026-05-28
**Status:** accepted
**Supersedes:** —
**Related:** ADR-002 (db-portability), `obsidian/Architecture/viewer-layers.md`

## Контекст

`viewer/index.html` — монолит 12K строк / 668 KB:
- 443 обращения к `document.*`
- 292 `getElementById`
- 80 `addEventListener`
- 52 `innerHTML`
- 366 функций

Бизнес-логика, рендер, подписка на события и внешние вызовы (Leaflet, JSZip, XLSX, exifr, piexif, fetch к NSPD) перемешаны в одних и тех же функциях. Состояние — в DOM и глобалах (`window.__ekceloRole` и т.п.).

Запланирован порт UI на React после отладки. При текущей структуре порт = новая разработка: восстанавливать логику из перемешанного кода будет дольше, чем написать с нуля.

## Решение

Ввести слои:

| Слой | Папка | Что внутри | Что запрещено |
|---|---|---|---|
| **core** | `viewer/core/` | Чистые функции и иммутабельные структуры. Принимают данные, возвращают данные. | `document`, `window`, `navigator`, `location`, `localStorage`, `sessionStorage`, `fetch`, `XMLHttpRequest`, `alert`/`confirm`/`prompt` |
| **adapters** | `viewer/adapters/` | Мост к внешнему миру: fetch к API, чтение/запись localStorage, File System Access API. | UI-логика, рендер |
| **ui** | `viewer/ui/` | Тонкая DOM-обёртка. Подписывается на core-state, рендерит. Содержит обработчики кликов. | Бизнес-логика, нормализация данных, форматирование экспорта |

Ограничение `core/` — машинно-проверяемое: ESLint-правило `no-restricted-globals` в корневой `.eslintrc.json` (секция `overrides` для `viewer/core/**/*.js`).

Тесты `core/` — на встроенном `node:test` (Node 20, без сборщика и npm-зависимостей).

## Область применения

Активные файлы `viewer/`, подчиняющиеся ADR-003:

1. `viewer/index.html` — главный target, постепенно худеет.
2. `viewer/sw.js` — service worker (139 строк). Cache-логика → `viewer/core/sw-cache.js`, обработчики событий остаются в `sw.js`.
3. `viewer/tokens.js` — уже соответствует core-паттерну (pure ES-module). Физическая реализация → `viewer/core/tokens-core.js`, `viewer/tokens.js` остаётся фасадом для совместимости с production-URL `https://romanbabenkorostov-ux.github.io/ekcelo/viewer/tokens.js` (см. `token-gate.html`).
4. `viewer/admin-encode.html` — inline-скрипт → `viewer/ui/admin-encode.js`.
5. `viewer/token-gate.html` — inline-скрипт → `viewer/ui/token-gate.js`.

**Исключён:** `viewer/v2961.html` — frozen legacy snapshot версии 2.9.61, не развивается.

## Обязательная последовательность PR

1. **PR-скелет** *(текущий)*: создать структуру + ESLint + тесты + CI + 3 безопасных выноса из `index.html` (`sha256Hex`, `escapeHtml`, `escapeXml`).
2. **PR `tokens.js` → фасад**: вынести реализацию в `core/tokens-core.js`, `viewer/tokens.js` ре-экспортирует.
3. **PR `admin-encode.html`**: вынести inline-скрипт в `ui/admin-encode.js`.
4. **PR `token-gate.html`**: вынести inline-скрипт в `ui/token-gate.js`.
5. **PR `sw.js`**: вынести cache-логику в `core/sw-cache.js`.
6. **Дальше — волны рефакторинга `index.html`**: subagent `viewer-extract` берёт по одной функции за раз, перемещает, добавляет тест.

## Метрика прогресса

- **Стартовое значение** (на момент мерджа PR-скелета): `grep -c "document\." viewer/index.html` = **443**.
- **Цель**: каждый последующий PR-вынос уменьшает это число. Метрика фиксируется в описании PR.
- **Ноль не достижим**: остаточный DOM-код в `index.html` — это `ui/`-слой по сути, который рано или поздно переедет в отдельные `ui/*.js`.

## Acceptance

PR отклоняется reviewerом, если:
- содержит `document.*`, `window.*` (кроме `globalThis.crypto`) внутри `viewer/core/**`;
- core-функция написана без юнит-теста в `tests/viewer/`;
- inline-скрипт в `viewer/*.html` добавляется без переноса в `viewer/ui/`;
- стартовая метрика `document.*` в `index.html` выросла без явного обоснования.

Автоматические гарантии:
- ESLint `no-restricted-globals` (см. корневой `.eslintrc.json` (секция `overrides` для `viewer/core/**/*.js`)).
- `.github/workflows/tests.yml` гоняет `node --test tests/viewer/*.test.mjs` на каждом PR.

## Сборщик и React

Не вводятся в рамках ADR-003. ES-модули нативно через `<script type=module>`. React — отдельным ADR после того, как `ui/` будет вычленен из `index.html` в самостоятельные модули.

## Связь с ADR-002

ADR-002 (db-portability) живёт параллельно, не зависит от viewer-слоёв. Их объединяет общий принцип: фиксировать архитектурные ограничения **до** написания основного кода, чтобы потом не переписывать.
