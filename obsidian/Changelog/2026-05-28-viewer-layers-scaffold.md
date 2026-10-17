# 2026-05-28 — Viewer layers scaffold + ТЗ-01/02 артефакты

PR: claude/magical-mccarthy-3ZyU4 → main (TBD #).
Тип: архитектурная подготовка (без изменения поведения).

## Что сделано

### ADR / справки

- `obsidian/Decisions/ADR-002-db-portability.md` — SQLite (dev/export) ↔ PostgreSQL (prod) через SA Core 2.x + alembic.
- `obsidian/Decisions/ADR-003-viewer-layers.md` — core/adapters/ui разделение, метрика `document.*` (старт 443), follow-up PR карта.
- `obsidian/Database/dialect-portability.md` — запрещённые SQL-конструкции и SA-эквиваленты.
- `obsidian/Architecture/viewer-layers.md` — описание слоёв и acceptance.

### Skills + subagent

- `.claude/skills/db-portability/SKILL.md` — активируется на правках `schema/`, `parser/**/db*`.
- `.claude/skills/viewer-layers/SKILL.md` — активируется на правках `viewer/` (кроме `v2961.html`).
- `.claude/agents/viewer-extract.md` — subagent для пошагового выноса функций из `index.html` (Read, Edit, Write, Bash, Grep).

### Viewer-скелет

- `viewer/package.json` — `{"type":"module"}`, маркер для Node-резолва.
- `viewer/core/`, `viewer/adapters/`, `viewer/ui/` — структура папок с README в каждой.
- `viewer/core/hashing.js` — `sha256Hex(text)`, перенесено из `__ekceloSha256Hex`.
- `viewer/core/escape.js` — `escapeHtml(s)` + `escapeXml(s)`, перенесены из `_escapeHtml`/`_escapeXml`.
- `viewer/ui/bridge.js` — временный мост: `window.__ekceloSha256Hex`/`window._escapeHtml`/`window._escapeXml` для совместимости с оставшимися классическими `<script>`-вызывающими в `index.html`.

### ESLint

- Корневой `.eslintrc.json` дополнен секцией `overrides`:
  - `viewer/{core,ui,adapters}/**/*.js` — `sourceType: "module"`;
  - `viewer/core/**/*.js` — `no-restricted-globals` запрещает `document`/`window`/`navigator`/`location`/`localStorage`/`sessionStorage`/`fetch`/`XMLHttpRequest`/`alert`/`confirm`/`prompt`.
- `dev/package.json` — lint-скрипт расширен на `viewer/core`, `viewer/ui`, `viewer/adapters` через `--ext .html,.js`.

### Тесты + CI

- `tests/viewer/hashing.test.mjs` — 4 теста `sha256Hex` (включая UTF-8 vector).
- `tests/viewer/escape.test.mjs` — 6 тестов `escapeHtml`/`escapeXml`.
- `tests/viewer/README.md` — инструкция запуска.
- `.github/workflows/tests.yml` — Node 20, `node --test tests/viewer/*.test.mjs`, триггер на PR + push с правками `viewer/**` или `tests/viewer/**`.
- Локальный прогон: **10 passed, 0 failed**.

### index.html

- Удалены 3 inline-объявления функций (`__ekceloSha256Hex`, `_escapeHtml`, `_escapeXml`), на их местах — комментарии-якоря.
- В конце `<body>` добавлен `<script type="module" src="./ui/bridge.js"></script>`.
- Все остальные 14 вызовов `_escapeHtml`/`_escapeXml` и 1 вызов `__ekceloSha256Hex` остались без изменений — резолвятся через `window.*`-регистрацию из bridge.js.
- Метрика `grep -c "document\." viewer/index.html` = **443** (не изменилась, как и планировалось — pure-функции без DOM не уменьшают счётчик).

### Correspondence

- `docs/CORRESPONDENCE/029-owner-viewer-layers-scaffold.md` — пост от owner к parser+viewer (027 занят parser-EXIF; перенумеровано после rebase на main с PR #65–77).
- `docs/CORRESPONDENCE/028-viewer-ack-exif-v1-2.md` — ack viewer-team по EXIF v1.2 (027 parser).
- `INDEX.md` обновлён строками 028 + 029.

## Карта follow-up PR (зафиксирована в ADR-003)

| PR | Что | Куда |
|---|---|---|
| N+1 | `tokens.js` реализация | `viewer/core/tokens-core.js`; `viewer/tokens.js` — фасад |
| N+2 | `admin-encode.html` inline | `viewer/ui/admin-encode.js` |
| N+3 | `token-gate.html` inline | `viewer/ui/token-gate.js` |
| N+4 | `sw.js` cache-логика | `viewer/core/sw-cache.js` |
| N+5+ | волны выноса из `index.html` через subagent `viewer-extract` | core/adapters/ui |

## Verification

- `node --test tests/viewer/*.test.mjs` → 10/10 passed локально.
- Браузерная проверка (планируется после мержа owner'ом):
  - открыть `viewer/index.html` через `python -m http.server` из корня репо;
  - Network: `viewer/ui/bridge.js`, `viewer/core/hashing.js`, `viewer/core/escape.js` — HTTP 200;
  - Console: `window._escapeHtml('<b>')` → `&lt;b&gt;`; `window.__ekceloSha256Hex('test').then(console.log)` → 64 hex chars;
  - визуально: карта, ЭТП-блок, кадастр, EXIF — без регрессий.

## Связанные файлы

- ADR-001 (etp-profile-extension) — параллельный, не пересекается.
- CLAUDE.md — не трогаем, правила слоёв активируются через skills.
- `docs/CORRESPONDENCE/INDEX.md`, `docs/CORRESPONDENCE/028-*.md`, `docs/CORRESPONDENCE/029-*.md`.
