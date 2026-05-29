# 029 — Viewer layers scaffold + DB-portability rules (ТЗ-01/02)

- **From:** owner
- **To:** parser, viewer
- **Date:** 2026-05-29
- **Re:** ADR-002 (db-portability), ADR-003 (viewer-layers), `obsidian/Database/dialect-portability.md`, `obsidian/Architecture/viewer-layers.md`, skill `db-portability`, skill `viewer-layers`, subagent `viewer-extract`
- **Status:** open · awaiting ack от обеих команд

## Суть

Введены **два архитектурных правила** под будущий рост проекта (этап 2 — React-фронт + FastAPI на Timeweb, этап 3 — инсталлируемая обёртка). Текущий код не меняется существенно; меняются **правила для нового кода**.

### ТЗ-01 — DB-абстракция SQLite (dev / per-user export) ↔ PostgreSQL (prod)

Закреплено в **ADR-002**, справка — `obsidian/Database/dialect-portability.md`, активный skill `db-portability`.

- **Запросы к БД** в Python — только через SQLAlchemy Core 2.x. Raw SQL — отказ при review.
- **Миграции** — alembic; `DROP COLUMN`/`ALTER COLUMN` — через `op.batch_alter_table` (работает на обеих БД).
- **Запрещены** диалект-специфичные конструкции: `INSERT OR REPLACE/IGNORE`, `AUTOINCREMENT`, `PRAGMA`, `DATETIME('now')`, `VARCHAR(n)`, `JSON_EXTRACT(...)`, `1/0` для bool. Полный список — в справке.
- **Типы** — через SA: `Integer`, `Text`, `Float`, `JSON`, `Boolean`, `DateTime(timezone=False)`. Всё UTC.
- **Координаты** — WKT-строка в `Text`. **Без PostGIS** до отдельного ADR.
- **Тесты** на БД — пока на in-memory SQLite; после ввода Postgres-окружения добавится двойной прогон.
- **Per-object SQLite-export пользователю** — через тот же SA-слой, schema идентична prod (одна alembic-голова).

### ТЗ-02 — viewer/core/adapters/ui разделение

Закреплено в **ADR-003**, справка — `obsidian/Architecture/viewer-layers.md`, активный skill `viewer-layers`, subagent `viewer-extract`.

- Слои: `viewer/core/` (чистые функции, ноль DOM), `viewer/adapters/` (мост к миру), `viewer/ui/` (тонкая DOM-обёртка).
- ESLint-правило `no-restricted-globals` в корневом `.eslintrc.json` (секция `overrides`) запрещает `document`/`window`/`navigator`/`location`/`localStorage`/`sessionStorage`/`fetch`/`XMLHttpRequest`/`alert`/`confirm`/`prompt` в `viewer/core/**/*.js`.
- Юнит-тесты — встроенный `node:test` (Node 20). Без npm-зависимостей, без сборщика.
- CI-workflow `.github/workflows/tests.yml` гоняет тесты на каждом PR с правками `viewer/**` или `tests/viewer/**`.
- Зона применения: `viewer/index.html`, `viewer/sw.js`, `viewer/tokens.js`, `viewer/admin-encode.html`, `viewer/token-gate.html`. **Исключён** `viewer/v2961.html` (frozen legacy).
- Метрика прогресса: `grep -c "document\." viewer/index.html` — стартовое **443**. Каждый последующий PR-вынос уменьшает; фиксируется в описании PR.

## Что уже сделано в этом PR

1. Скелет `viewer/core/`, `viewer/adapters/`, `viewer/ui/` + `viewer/package.json` (`{"type":"module"}`).
2. ESLint `overrides` в корневом `.eslintrc.json`; lint-скрипт в `dev/package.json` расширен на новые папки.
3. CI workflow `.github/workflows/tests.yml`.
4. 3 безопасных выноса из `viewer/index.html` в `viewer/core/`:
   - `__ekceloSha256Hex` → `core/hashing.js` :: `sha256Hex` (pure, Web Crypto API);
   - `_escapeHtml` → `core/escape.js` :: `escapeHtml` (pure);
   - `_escapeXml` → `core/escape.js` :: `escapeXml` (pure).
5. Мост `viewer/ui/bridge.js` — присваивает старые имена `window.*` для совместимости с оставшимися классическими `<script>`-вызывающими в `index.html`. Убирается в волнах рефакторинга по мере переезда вызывающих в модули.
6. Тесты `tests/viewer/hashing.test.mjs` (4 теста) + `tests/viewer/escape.test.mjs` (6 тестов). Все 10 — зелёные.
7. ADR-002, ADR-003, 2 справки в `obsidian/`, 2 skill, 1 subagent.

**Метрика после PR:** `document.*` в `index.html` = 443 (не изменилась — мы вынесли pure-функции без DOM-обращений). Снижение начнётся со следующих PR.

## Дорожная карта (зафиксирована в ADR-003)

| PR | Что выносится | Куда | Риск |
|---|---|---|---|
| **N+1** | `tokens.js` (реализация) | `viewer/core/tokens-core.js`; `viewer/tokens.js` остаётся фасадом из-за production-URL в `token-gate.html` | низкий |
| **N+2** | `admin-encode.html` inline-скрипт | `viewer/ui/admin-encode.js` | минимальный |
| **N+3** | `token-gate.html` inline-скрипт | `viewer/ui/token-gate.js` | минимальный |
| **N+4** | `sw.js` cache-логика | `viewer/core/sw-cache.js`; `sw.js` — тонкий handler | средний (module-SW поддержка в старых браузерах) |
| **N+5..** | волны выноса из `index.html` через subagent `viewer-extract` | `core/`, `adapters/`, `ui/` | по одной функции за PR |

## Что ждётся от команд

### parser-team

- Соблюдать **ADR-002** в новых правках БД (новый запрос/миграция/таблица).
- Skill `db-portability` подсасывается автоматически на правках `schema/`, `parser/**/db*`, `parser/**/models*`.
- Существующий код (`parser/egrn_parser/db/`) приводится в соответствие постепенно, по мере правок. Большой миграционный PR не нужен.
- Если возникает технический спор по конкретной SQL-конструкции — пинг в новом посте переписки.

### viewer-team

- Новые функции — **сразу** в нужный слой (`core` / `adapters` / `ui`).
- Inline-`<script>` в `viewer/*.html` (кроме `v2961.html`) — больше не добавляются. Используй `<script type="module" src="./ui/...">`.
- При выносе существующей функции из `index.html` — через subagent `viewer-extract` (берёт имя функции, классифицирует, переносит, добавляет тест, патчит `index.html`).
- Метрику `document.*` упоминать в описании PR (текущее значение).

### owner

- Веду карту follow-up PR (см. таблицу выше).
- Slip от плана (нарушение ADR без обновления ADR) — повод нового поста.

## Возражения / open-вопросы

**`viewer/sw.js` + ES-модули — открыто.** Регистрация service worker как `type: 'module'` поддерживается Chromium ≥80 / Firefox ≥111, но Яндекс.Браузер и старые сборки могут отставать. Окончательное решение по PR N+4 — позже, возможен вариант «оставить classic SW, core-логика в формате, совместимом с `importScripts`».

**Сборщик.** Не вводится. ES-модули нативно через `<script type="module">`. Vite/Webpack — отдельным ADR одновременно с React-портом.

**React.** Не вводится. Отдельным ADR, когда `ui/` достаточно вычленится из `index.html`.

## Просьба / next action

- **viewer-team:** ack новых правил (или возражения) в этом PR через `COMMENT`-review.
- **parser-team:** ack ADR-002 (или возражения) в этом PR через `COMMENT`-review.

Ратификация — мердж этого PR. После мержа этот пост = `ratified`.
