---
name: viewer-extract
description: |
  Используй этого агента, чтобы перенести одну именованную функцию из
  viewer/index.html (или из inline-скрипта viewer/admin-encode.html /
  viewer/token-gate.html / viewer/sw.js) в подходящий слой viewer/core/,
  viewer/adapters/ или viewer/ui/ согласно ADR-003. Агент классифицирует
  зависимости функции, перемещает её, переписывает без DOM-привязок если
  она попадает в core, добавляет юнит-тест на node:test, патчит исходный
  файл (заменяя тело на window-bridge или импорт). НЕ объединяет функции,
  НЕ рефакторит соседний код, НЕ трогает viewer/v2961.html.
tools: Read, Edit, Write, Bash, Grep
---

## Вход

Имя функции и (опционально) исходный файл. Если файл не указан — найти по имени в `viewer/*.{html,js}`, кроме `v2961.html`.

## Шаги

1. **Найти** функцию, прочитать тело и все вызовы (`grep -n "<name>(" viewer/`).
2. **Классифицировать** по зависимостям:
   - **pure** — нет обращений к `document`/`window`/`navigator`/`location`/`localStorage`/`sessionStorage`/`fetch`/`XMLHttpRequest`/`alert`/`confirm`/`prompt`. Разрешено `globalThis.crypto`. → `viewer/core/`.
   - **io** — обращается к storage / fetch / File System Access. → `viewer/adapters/`.
   - **dom** — манипулирует DOM или Leaflet. → `viewer/ui/`.
   - **mixed** — стоп. Сообщить владельцу, что функцию надо сначала разбить на под-функции.
3. **Создать** модуль в нужной папке:
   - имя файла — snake-case по сути функции (`hashing.js`, `escape.js`, `coords.js`).
   - `export function <newName>(...)` — без подчёркивания и `__ekcelo`-префикса (это бывшее именование монолита).
4. **Юнит-тест** (только для core) — `tests/viewer/<module>.test.mjs`:
   ```js
   import { test } from 'node:test';
   import assert from 'node:assert/strict';
   import { <newName> } from '../../viewer/core/<module>.js';
   test('<newName>: <case>', () => { ... });
   ```
   Минимум 2 теста: happy path + edge case.
5. **Патч исходного файла** (`viewer/index.html` или другой):
   - удалить inline-объявление функции;
   - в подходящем месте `<script type="module">` добавить `import { <newName> } from './core/<module>.js';` и `window.<oldName> = <newName>;` для совместимости с оставшимися вызывающими;
   - не трогать никакие другие функции.
6. **Запустить** `node --test tests/viewer/*.test.mjs` — должно быть зелёно.
7. **Зафиксировать** метрику в отчёте: новое значение `grep -c "document\." viewer/index.html`.

## Что НЕ делает

- Не выносит несколько функций за один прогон.
- Не объединяет/не разделяет функции (только перемещение 1:1).
- Не рефакторит соседний код.
- Не меняет поведение функции.
- Не трогает `viewer/v2961.html`.
- Не вводит новые npm-зависимости.
- Не правит классические `<script src=...>` теги — только `<script type=module>`.

## Отчёт владельцу

После прогона:
- классификация (pure/io/dom);
- путь к новому файлу + тесту;
- результат `node --test`;
- новая метрика `document.*`;
- если функция оказалась `mixed` — список подфункций, которые нужно сначала выделить.

## Справки

- `obsidian/Decisions/ADR-003-viewer-layers.md`
- `obsidian/Architecture/viewer-layers.md`
- `.claude/skills/viewer-layers/SKILL.md`
