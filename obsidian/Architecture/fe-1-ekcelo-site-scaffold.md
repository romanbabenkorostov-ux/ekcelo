# FE-1 — ekcelo-site scaffold

> Первый код frontend репозитория. Vite + TypeScript, структура
> core/adapters/ui по `SPEC_frontend.md`. api-adapter (C4 клиент) + базовый
> UI каталога/объекта/графа + login через `/auth/login` (cycle 14 M2).
> Размещение — монорепо subdir `ekcelo-site/` (выбор пользователя).

## Архитектура

Принцип SPEC: **два адаптера → одна ViewModel → один UI**.

```
ekcelo-site/
├── package.json                vite + typescript + vitest + eslint
├── tsconfig.json               strict, path aliases @core/@adapters/@ui
├── vite.config.ts              proxy /api → backend, /auth → backend
├── index.html                  SPA shell
├── .eslintrc.cjs               архитектурный guard: ui ⊀ adapters
├── src/
│   ├── core/
│   │   └── viewmodel.ts        TypeScript-зеркало viewmodel.schema.json
│   ├── adapters/
│   │   └── api.ts              ApiClient: catalog/objects/lots/graph
│   ├── ui/                     рендеры (структура DOM, не знают про fetch)
│   │   ├── catalog.ts
│   │   ├── object-card.ts      4 характеристики
│   │   ├── graph.ts
│   │   └── render-utils.ts
│   ├── main.ts                 SPA shell + hash-роутинг
│   └── styles.css
└── tests/                      vitest + happy-dom (29 тестов)
    ├── viewmodel.test.ts
    ├── api-adapter.test.ts
    └── render.test.ts
```

## Ключевые решения

### 1. Монорепо подкаталог
`ekcelo/ekcelo-site/` (не отдельный репо). По вашему выбору. Плюсы:
- contracts/ доступны рядом — позже скриптом synсync будем держать
  `viewmodel.schema.json` ↔ `core/viewmodel.ts`
- handoff-workflow тот же (один клон, zip-распаковка)
- независимый deploy всё равно возможен (build → dist → отдельный bucket)

### 2. Vite + vanilla TypeScript (без React)
По SPEC React откладывается до P2-P3 после стабилизации core/adapters/ui.
FE-1 — минимально достаточный набор:
- TypeScript строгий (`strict`, `noUncheckedIndexedAccess`).
- vitest + happy-dom для DOM-тестов.
- ESLint `no-restricted-imports`: `ui/*` НЕ может импортировать `adapters/*`
  (архитектурный guard).
- Готов к миграции на React: компоненты будут импортировать тот же
  `core/` + `adapters/` без изменений.

### 3. API клиент с двумя режимами URL
- **Без `baseUrl`** (default) — пути идут как `/api/catalog` → vite proxy
  переписывает в `http://localhost:8000/catalog` (dev) или nginx (prod).
- **С `baseUrl`** — прямой fetch на абсолютный URL (тесты, прямой деплой
  фронта на другом домене).

`credentials: "include"` всегда — для cookie-сессии (cycle 14 M2).

### 4. Login через `/auth/login` (cycle 14 M2)
SPA не реализует OAuth логику — просто ссылка на `/auth/login`, бэкенд
сделает редирект на IdP. Возврат через `/auth/callback` → cookie. Все
последующие fetch-запросы автоматически несут cookie.

401 от любого API-запроса → `redirectToLogin()` → `/auth/login`. Бесшовно.

### 5. UI рендер через `textContent`, не `innerHTML`
Защита от XSS — никаких `innerHTML` с данными от бэкенда. Тест
`renderCatalog`: title `<script>alert(1)</script>` рендерится как **текст**,
не выполняется. SPA остаётся защищённой даже если бэкенд почему-то
пропустит вредоносный ввод.

### 6. 4 характеристики структурно разделены
По SPEC: physical/ownership/geo/temporal — 4 секции с h2-заголовками
ЧТО/ЧЬЁ/ГДЕ/КОГДА. Это и UX-разделение, и контракт для UI-тестов
(`.char-physical/.char-ownership/...`).

## Зависимости от бэкенда

| Что фронт читает | Откуда | Когда |
|---|---|---|
| `GET /catalog?q&kind` | бэкенд C4 (готов в main) | каждая загрузка каталога |
| `GET /objects/{cad}` | бэкенд C4 | открытие объекта |
| `GET /lots/{lot_id}` | бэкенд C4 | открытие лота |
| `GET /objects/{cad}/graph` | бэкенд C4 | открытие объекта (параллельно) |
| `GET /auth/login` | бэкенд cycle 14 M2 | клик "Войти" |
| cookie `ekcelo_token` | бэкенд cycle 14 M1+M2 | все fetch |

Backward-compat: если backend запущен с `enforce_rbac=False` и без
`EKCELO_OIDC_CLIENT_ID` — фронт работает без login UI (анонимный
доступ, все эндпоинты открыты).

## Тесты

- **29 vitest** (3 файла):
  - `viewmodel.test.ts` (5) — структурный sanity isViewModel.
  - `api-adapter.test.ts` (13) — fetch-моки для catalog/object/graph,
    обработка 401/403/500, query params, dev/prod URL-режимы.
  - `render.test.ts` (11) — DOM-структура catalog/object-card/graph,
    XSS-защита, повторный рендер очищает контейнер.
- **TypeScript strict** — `tsc --noEmit` без ошибок.
- **ESLint** — `no-restricted-imports` guard (ui ⊀ adapters) зелёный.
- **Backend regression** — 495 тестов как раньше (фронт изолирован).

## Запуск (dev)

```bash
# Терминал 1 — backend
cd ekcelo
uvicorn lot_orchestrator_web.main:app --reload

# Терминал 2 — frontend
cd ekcelo-site
npm install  # первый раз
npm run dev   # http://localhost:5173
```

## Что НЕ в FE-1

### FE-2 (следующий sub-stage)
- **Интерактивный граф** (D3.js или cytoscape) вместо текстового списка.
- **Порт kmz→ViewModel** из `viewer/index.html` (12K строк) в
  `adapters/kmz.ts`. Поддержка офлайн-режима (drag-drop KMZ файла).
- **Кросс-матч**: один объект, открытый через `api` и через `kmz` адаптер,
  рисуется идентично (DoD из SPEC).

### FE-3
- **Карта** — Google Earth embed (через KMZ) или Leaflet с tile-source.
- **Геометрия** ожидает C3.3 (parser-team) — пока `geo.center` пустой,
  показываем muted.
- **UI грантов** — таблица `GET /grants/me`, формы `POST /grants` для
  делегирования/шеринга.

## Связи

- Backend контракт: `contracts/api/openapi.yaml`, `viewmodel.schema.json`.
- Auth: `obsidian/Architecture/cycle-14-oauth.md` (M1),
  `cycle-14-m2-browser-flow.md` (M2).
- Спека: `docs/specs/SPEC_frontend.md` (фазы 0-5 распила).
- ROLES (для UI грантов в FE-3): `contracts/roles/ROLES_SPEC.md`.
- Предшественник на бэкенде: `cycle-15-rbac.md`.
