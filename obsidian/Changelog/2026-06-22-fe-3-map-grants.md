# 2026-06-22 — FE-3 карта (Leaflet) + UI грантов — ФРОНТ ЗАКРЫТ

## Что сделал

1. **Карта** (`ui/map.ts`) — Leaflet-рендер geo.geometry (Polygon/Point) из
   координат KMZ. Динамический импорт (code-split + тесты не падают).
2. **UI грантов** (`ui/grants.ts`) — список + форма выдачи + отзыв (C6 RBAC).
3. **API +3 метода** — getMyGrants/createGrant/revokeGrant.
4. **Роутинг** — `#/grants` страница + карта на странице объекта.

Frontend трек FE-0..FE-3 завершён.

## Файлы
- ✨ `ekcelo-site/src/ui/map.ts` — Leaflet карта + geometryToLatLngs.
- ✨ `ekcelo-site/src/ui/grants.ts` — таблица + форма грантов.
- ✏️ `ekcelo-site/src/adapters/api.ts` — getMyGrants/createGrant/revokeGrant
  + 204-обработка.
- ✏️ `ekcelo-site/src/core/viewmodel.ts` — типы Grant/GrantCreate/GrantAction.
- ✏️ `ekcelo-site/src/main.ts` — #/grants роут + карта на объекте + nav.
- ✏️ `ekcelo-site/src/styles.css` — стили карты + грантов.
- ✏️ `ekcelo-site/package.json` + `package-lock.json` — +leaflet/@types.
- ✨ `ekcelo-site/tests/map.test.ts` — 5 тестов.
- ✨ `ekcelo-site/tests/grants-ui.test.ts` — 7 тестов.
- ✏️ `ekcelo-site/tests/api-adapter.test.ts` — +4 grant-теста.
- ✨ `obsidian/Architecture/fe-3-map-grants.md` — снимок.
- ✏️ roadmap + CHECKPOINT.

## Тесты
- **Frontend:** 66 vitest (50 + 16 FE-3).
- **TypeScript strict:** 0 ошибок.
- **ESLint:** 0 warnings.
- **Build:** main 26KB (11KB gz) + leaflet chunk 150KB (44KB gz, lazy).
- **Backend:** 495 без изменений.

## Решения

- **Leaflet динамический импорт.** `await import("leaflet")` даёт: (а)
  code-split — 150KB Leaflet грузится только при показе карты, main bundle
  остаётся 26KB; (б) тесты в happy-dom (без canvas) не падают на import —
  тестируем только чистую `geometryToLatLngs`.
- **OpenStreetMap tiles.** Без API-ключа, бесплатно для dev/demo. Для
  production-нагрузки — свой tile-server или Mapbox/MapTiler с ключом.
- **geometryToLatLngs экспортирована для тестов.** Чистая функция
  ([lon,lat]→[lat,lon] переворот GeoJSON→Leaflet) тестируется без DOM.
- **UI грантов без RBAC-логики.** POST /grants backend сам решает
  delegate vs share по роли. UI не дублирует — single source of truth.
- **204 no-content в api.json().** DELETE /grants/{id} возвращает 204 без
  body; `resp.json()` упал бы. Добавлена ветка `status===204 → undefined`.
- **Карта между карточкой и графом.** Логичный порядок: что/чьё (карточка)
  → где (карта) → структура владения (граф).

## Канал доставки
- Sandbox-proxy блокирует push — zip-handoff (после merge #122).
- npm install (leaflet) воспроизводим — package-lock закоммичен.

## Frontend трек завершён

`ekcelo-site` покрывает полный SPEC_frontend DoD:
- каталог (api) + поиск
- объект: 4 характеристики + карта (geo) + интерактивный граф
- два адаптера (api + kmz), один UI — кросс-матч работает
- OAuth login (cycle 14 M2 cookie)
- управление доступом C6 (гранты)

## Следующий шаг (опц.)
- C3.3 geo materialization (backend, parser-зависимо) — чтобы api-режим
  тоже показывал карту без KMZ.
- Production deploy: vite build → static host (Cloudflare/nginx) +
  backend на timeweb + PostgreSQL.
- Деприкейт `viewer/index.html` (формально legacy).
