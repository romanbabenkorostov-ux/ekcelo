# FE-3 — карта (Leaflet) + UI грантов

> Финальный frontend под-этап. (1) Карта объекта на Leaflet — рендер
> geo.geometry (Polygon/Point) из координат KMZ. (2) UI управления грантами
> (C6 RBAC) — список + выдача + отзыв через REST `/grants`. После FE-3 фронт
> функционально закрыт; `viewer/` можно деприкейтить.

## Что добавлено

### Карта (`ui/map.ts`)
- `renderMap(container, geo)` — Leaflet-карта geo.geometry.
- Polygon → `L.polygon` с fitBounds; Point/center → `L.marker`.
- OpenStreetMap tiles (без API-ключа).
- **Leaflet импортируется динамически** (`await import("leaflet")`):
  - code-split — Leaflet (150KB) в отдельном чанке, грузится только при
    открытии объекта с геометрией;
  - тесты (happy-dom без canvas) не падают на import.
- Если geo пустой (api до C3.3) — сообщение «геометрия недоступна».
- z_meters_top подпись (3D-extrude — будущее).
- Чистая `geometryToLatLngs` экспортирована для unit-тестов (без Leaflet).

**Ценность**: geo приходит из kmz-адаптера (FE-2) — координаты есть в KMZ,
но api не отдаёт до backend C3.3. Так офлайн-режим показывает объект на
карте мира.

### UI грантов (`ui/grants.ts`)
- `renderGrants(container, grants, {onCreate, onRevoke})`:
  - таблица «мои гранты»: действие / ресурс / кем выдан / срок / отзыв;
  - revocable грант → кнопка «Отозвать»; non-revocable → «—»;
  - форма выдачи: subject_sub + action + resource_type + resource_id.
- Не знает про HTTP — принимает данные + колбэки.

### API клиент (`adapters/api.ts` +3 метода)
- `getMyGrants()` → `GET /grants/me`.
- `createGrant(body)` → `POST /grants` (201).
- `revokeGrant(id)` → `DELETE /grants/{id}` (204, обработка no-content).

### Роутинг (`main.ts`)
- `#/grants` → страница управления грантами (auto-reload после create/revoke).
- Карта добавлена на страницу объекта (между карточкой и графом).
- Ссылка «Гранты» в nav.

## C6 семантика (UI ↔ backend)

UI просто отправляет `POST /grants` — backend (cycle 15 M3) сам
диспетчеризует по роли вызывающего:
- assessor + action → `delegate` (передача права другому assessor);
- client + view → `share` (view-only третьему лицу);
- иначе → 403.

Так UI не дублирует RBAC-логику — единственный источник правды backend.

## Тесты

- **66 vitest всего** (50 + 16 FE-3):
  - `map.test.ts` (5) — `geometryToLatLngs`: Polygon/Point переворот
    [lon,lat]→[lat,lon], null/unknown geometry.
  - `grants-ui.test.ts` (7) — таблица, revocable-кнопка, onRevoke,
    expires_at, форма submit/empty.
  - `api-adapter.test.ts` (+4) — getMyGrants, createGrant POST+JSON,
    revokeGrant DELETE+204, 403.
- **TypeScript strict**: 0 ошибок.
- **ESLint**: 0 warnings (ui ⊀ adapters guard соблюдён).
- **Build**: main 26KB (11KB gzip) + leaflet chunk 150KB (44KB gzip,
  lazy). Backend 495 без изменений.

## Зависимости

- `leaflet@^1.9` (runtime) + `@types/leaflet` (dev). Динамический импорт →
  не в main bundle.

## Что НЕ в FE-3 (опц. будущее)

- **3D extrude зданий** — z_meters_top рендерится текстом; настоящий 3D
  требует CesiumJS / MapLibre GL (тяжелее Leaflet).
- **Multi-KMZ timeline** — переключение дат выписок (sample multi-extract
  есть). UI слайдер дат.
- **Граф на карте** — наложение графа владения на геопозиции.
- **Деприкейт `viewer/`** — формально пометить legacy после стабилизации.

## Frontend трек — итог

| Этап | Что | Статус |
|---|---|---|
| FE-0 | OAuth M2 browser flow | ✅ #120 |
| FE-1 | scaffold + api-adapter + UI | ✅ #121 |
| FE-2 | интерактивный граф + kmz-адаптер | ✅ #122 |
| FE-3 | карта + UI грантов | ✅ (этот) |

После FE-3 `ekcelo-site` покрывает: каталог, объект (4 характеристики),
граф владения (интерактивный), карта (geo), офлайн KMZ, OAuth login,
управление доступом (C6). DoD SPEC_frontend выполнен.

## Связи

- Geo источник: `adapters/kmz.ts` (FE-2), backend C3.3 (будущее).
- Гранты backend: `cycle-15-rbac.md` (M3 REST `/grants`).
- Auth: `cycle-14-m2-browser-flow.md` (session cookie).
- Карты: OpenStreetMap (tiles), Leaflet.
- Спека: `docs/specs/SPEC_frontend.md`.
