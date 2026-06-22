# 2026-06-21 — FE-1 ekcelo-site scaffold

## Что сделал

Первый код frontend в монорепо subdir `ekcelo-site/`. Vite + TypeScript +
vitest + ESLint. Структура **core/adapters/ui** по `SPEC_frontend.md`.
Реализован api→ViewModel адаптер (C4 клиент) + базовый UI каталога/
карточки объекта (4 характеристики) / графа. Login через `/auth/login`
(cycle 14 M2 cookie-сессия).

## Файлы (32 новых)

Конфиги: `package.json`, `tsconfig.json`, `vite.config.ts`, `.eslintrc.cjs`,
`.gitignore`, `README.md`.

Код:
- `index.html` — SPA shell
- `src/main.ts` — координатор + hash-роутинг
- `src/styles.css` — базовая стилизация
- `src/core/viewmodel.ts` — TS-зеркало `viewmodel.schema.json`
- `src/adapters/api.ts` — `ApiClient` (C4 endpoints + 401 handler)
- `src/ui/catalog.ts`, `object-card.ts`, `graph.ts`, `render-utils.ts`

Тесты (29):
- `tests/viewmodel.test.ts` (5) — isViewModel sanity
- `tests/api-adapter.test.ts` (13) — fetch-моки, error handling, URL режимы
- `tests/render.test.ts` (11) — DOM-структура, XSS-защита

Docs: `obsidian/Architecture/fe-1-ekcelo-site-scaffold.md`,
обновлены `roadmap-2026-06.md`, `CHECKPOINT.md`, `SPEC_backend.md`.

## Тесты
- **Frontend:** 29 vitest passed.
- **TypeScript strict:** `tsc --noEmit` — 0 ошибок.
- **ESLint:** 0 warnings (включая no-restricted-imports guard ui ⊀ adapters).
- **Backend regression:** 495 passed как раньше.

## Решения

- **Vanilla TypeScript без React.** Следуя SPEC, React откладывается до
  P2-P3 после стабилизации core/adapters/ui. FE-1 — минимально достаточный
  набор без ceremony. React-миграция: компоненты будут импортировать тот же
  `core/` + `adapters/` без изменений.
- **`credentials: "include"` всегда.** Cookie `ekcelo_token` ходит
  автоматически — соответствует cycle 14 M2 cookie-сессии. SPA ничего не
  знает про токен (httponly на бэкенде).
- **ESLint `no-restricted-imports` guard.** `ui/*` НЕ может импортировать
  `adapters/*` — архитектурный invariant из SPEC_frontend §P0.1. Тест
  падает если кто-то нарушит.
- **`textContent` вместо `innerHTML`.** XSS-защита. Тест `renderCatalog`
  с `<script>alert(1)</script>` в title подтверждает: рендерится как
  текст, не выполняется.
- **vite proxy `/api` + `/auth`.** Dev-сервер пробрасывает на бэкенд,
  cookies passthrough. В prod — nginx с теми же путями.
- **`baseUrl` опционален.** Без baseUrl — относительные пути под vite
  proxy. С baseUrl — прямой fetch (TestClient или прямой деплой). Один
  ApiClient для обоих сценариев.
- **401 → redirectToLogin.** Любой API-запрос на защищённом эндпоинте
  при отсутствии cookie → редирект на `/auth/login`. SPA-side бесшовно.

## Канал доставки
- Sandbox-proxy блокирует git push — zip-handoff (после merge #120).
- npm install в sandbox прошёл — деплой воспроизводим.

## Следующий шаг (FE-2)
1. **Интерактивный граф** (D3.js / cytoscape) — замена текстового
   `renderGraph`.
2. **kmz→ViewModel адаптер** — порт парсера из `viewer/index.html`
   (12K строк) в `adapters/kmz.ts`. Поддержка drag-drop KMZ-файла.
3. **Cross-match тест**: один объект через `api` и через `kmz` рисуется
   идентично (DoD из SPEC_frontend).
