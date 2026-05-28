---
name: viewer-layers
version: 1.0
description: |
  Применяется при любых правках в viewer/ (кроме v2961.html — заморожен).
  Обеспечивает разделение слоёв core/adapters/ui согласно ADR-003. Запрещает
  document/window/fetch в viewer/core/. Требует юнит-тесты для новых
  core-функций на node:test. См. ADR-003.
tags: [viewer, frontend, layers, refactor, react-prep]
---

## Когда срабатывать

- Любая правка `viewer/index.html`, `viewer/sw.js`, `viewer/tokens.js`, `viewer/admin-encode.html`, `viewer/token-gate.html`.
- Создание новых файлов в `viewer/core/`, `viewer/adapters/`, `viewer/ui/`.
- Любые правки `tests/viewer/`.
- **НЕ срабатывать** для `viewer/v2961.html` — это frozen legacy.

## Жёсткие правила (ADR-003)

1. **`viewer/core/` — чистые функции.** Запрещены: `document`, `window`, `navigator`, `location`, `localStorage`, `sessionStorage`, `fetch`, `XMLHttpRequest`, `alert`/`confirm`/`prompt`. Разрешено: `globalThis.crypto`. Ловится ESLint `no-restricted-globals` в корневой `.eslintrc.json` (секция `overrides`).
2. **`viewer/adapters/` — мост к миру.** Никакой бизнес-логики, никакого UI. fetch/storage/FS API — здесь.
3. **`viewer/ui/` — тонкий DOM-слой.** Обработчики кликов, Leaflet-обёртка, рендер. Никакой бизнес-логики (она в core).
4. **Каждая публичная core-функция — юнит-тест в `tests/viewer/*.test.mjs`** через `node:test`. Запуск: `node --test tests/viewer/*.test.mjs`.
5. **Новый inline-`<script>` в `viewer/*.html`** (кроме `v2961.html`) — **запрещён**. Только `<script type="module" src="./ui/...">` или подобные.
6. **Метрика прогресса:** `grep -c "document\." viewer/index.html` — стартовое 443. Каждый PR-вынос уменьшает. Фиксируется в описании PR.

## Куда что класть

| Что | Куда |
|---|---|
| Чистый форматтер, конвертор, фильтр | `viewer/core/` + тест |
| fetch к API, storage, FS API | `viewer/adapters/` |
| DOM-обработчик, Leaflet-связка | `viewer/ui/` |
| Состояние UI (роль, режим, фильтры) | store в `viewer/core/` (наблюдаемый объект, ноль DOM) |

## Шаги при выносе функции из `index.html` в `core/`

1. Найти функцию, прочитать тело.
2. Классифицировать зависимости: pure (→core), io (→adapters), dom (→ui).
3. Создать модуль в нужной папке, `export function ...`.
4. В `index.html` заменить тело старой функции на присваивание `window.<oldName> = <newName>` после `<script type="module">` с импортом. ИЛИ удалить тело полностью, если ничего не зависит от глобала.
5. Добавить тест в `tests/viewer/`.
6. Запустить `node --test tests/viewer/*.test.mjs` — зелёно.
7. Зафиксировать новое значение метрики `grep -c "document\." viewer/index.html` в описании PR.

Для пошагового выполнения — subagent `viewer-extract`.

## Acceptance check

Перед сдачей PR:
- [ ] Новые `core/`-файлы не используют запрещённые глобалы.
- [ ] Каждая публичная core-функция покрыта тестом.
- [ ] Inline-`<script>` в HTML не добавлен.
- [ ] Метрика `document.*` в `index.html` не выросла.
- [ ] `node --test tests/viewer/*.test.mjs` — зелёно.
- [ ] ESLint (`cd dev && npm run lint`) — зелёно.

## Справки

- `obsidian/Decisions/ADR-003-viewer-layers.md`
- `obsidian/Architecture/viewer-layers.md`
- `viewer/core/README.md`, `viewer/adapters/README.md`, `viewer/ui/README.md`
- `.claude/agents/viewer-extract.md` — subagent для пошагового выноса
