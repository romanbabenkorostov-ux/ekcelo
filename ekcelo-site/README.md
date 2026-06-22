# ekcelo-site (FE-1 scaffold)

> Frontend EKCELO — потребляет ViewModel REST (C4 контракт) из бэкенд-репо.
> FE-1 этап: scaffold + api-adapter + базовый UI (каталог/объект/граф) +
> login через OAuth M2 cycle 14.

## Архитектура (по `docs/specs/SPEC_frontend.md` в основном репо)

```
src/
├── core/                  ← типы ViewModel (зеркало contracts/api/viewmodel.schema.json)
│   └── viewmodel.ts
├── adapters/              ← источники → ViewModel
│   ├── api.ts             ← api→ViewModel (C4 REST клиент)
│   └── kmz.ts             ← kmz→ViewModel (FE-2, ещё не реализован)
├── ui/                    ← рендер, не знает откуда данные (ESLint-границы)
│   ├── catalog.ts
│   ├── object-card.ts     ← 4 характеристики
│   ├── graph.ts
│   └── render-utils.ts
└── main.ts                ← SPA shell + роутинг (hash)
```

## Запуск (требуется Node.js 18+)

```bash
cd ekcelo-site
npm install
npm run dev                # vite dev server на http://localhost:5173
```

В отдельном терминале — backend:
```bash
cd ..                      # корень ekcelo
uvicorn lot_orchestrator_web.main:app --reload
# http://localhost:8000
```

Vite proxy в `vite.config.ts` пробрасывает:
- `/api/*` → `http://localhost:8000/*` (REST C4)
- `/auth/*` → `http://localhost:8000/auth/*` (OAuth M2 browser flow)

Cookie `ekcelo_token` ходит автоматически (credentials: include).

## Тесты

```bash
npm test                   # vitest run (один прогон)
npm run test:watch
npm run typecheck          # tsc --noEmit
npm run lint
```

## Конфиг

- `EKCELO_BACKEND_URL` (env) — backend URL для proxy. По умолчанию
  `http://localhost:8000`.
- Для production build (`npm run build`) — настройте reverse-proxy
  (nginx) с теми же путями `/api/*` и `/auth/*`.

## Что НЕ в FE-1

- **FE-2**: интерактивный граф (D3/cytoscape) + порт kmz-парсера из
  `viewer/index.html` в `adapters/kmz.ts` для офлайн-режима.
- **FE-3**: карта (Google Earth embed / Leaflet) + единый рендер обоих
  адаптеров (api+kmz).
- React-миграция (P2-P3 по SPEC, после стабилизации core/adapters/ui).

## Связи

- Backend: `docs/specs/SPEC_backend.md`, `contracts/api/openapi.yaml`.
- Контракт ViewModel: `contracts/api/viewmodel.schema.json` (источник истины).
- Auth: `obsidian/Architecture/cycle-14-oauth.md` + `cycle-14-m2-browser-flow.md`.
- ROLES (для UI делегирования и шеринга, FE-3+):
  `contracts/roles/ROLES_SPEC.md`.
