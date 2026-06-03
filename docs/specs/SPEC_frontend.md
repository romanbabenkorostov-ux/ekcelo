# SPEC — Команда ekcelo-site (фронтенд: вьюер → React)

> Консистентность — через пакет `contracts/`. Веб-шов = **полный REST-рендеринг**.
> **Кода в этой итерации — по плану распила (фазы 0–5); новые контракты — только
> ViewModel-форма и адаптеры под неё.**

## Роль и контрактная поверхность

Просмотрщик. Веб — рендерит **ViewModel** из REST (**C4**). Локаль/скачивание/
Google Earth — открывает **KMZ** (**C1**). Эмитит UI/UX-домен. Потребляет C4, C1.

## Текущее состояние

Монолит `viewer/index.html` (~12K строк) читает только KMZ; идёт распил на
`core/adapters/ui` (фазы 0–5, ADR-001 viewer-layers, bridge-паттерн, ESLint-границы);
React не начат; бэкенд-клиента нет; Cloudflare worker = CORS-прокси (NSPD/Yandex/Rosreestr).

## Целевое состояние

Единый вьюер с **двумя адаптерами-источниками** к общей **ViewModel**:
`kmz→ViewModel` (офлайн/локаль/GE Pro) и `api→ViewModel` (веб) — рисует одинаково.

## Рабочие треки

### P0
1. **Продолжить распил core/adapters/ui.** Фазы 1–5 по плану (ESLint-границы).
   ui-слой не должен знать, откуда данные.
2. **Канон ViewModel в `core/`.** `viewer/core/viewmodel.js` — чистая модель из
   `contracts/api/viewmodel.schema.json` (4 характеристики: physical/ownership/
   geo/temporal). Единственная форма, которую потребляет ui. **Точка стыковки с backend-3.**
3. **Адаптер `kmz→ViewModel`.** Рефакторинг текущего KMZ-парсера
   (`loadKMZFromFile`/`parseKML`) из ui в `adapters/`: отдаёт ViewModel, не дёргает
   DOM. Сохраняет офлайн/GE-Pro-сценарий.

### P1
4. **Адаптер `api→ViewModel` + API-клиент.** `adapters/api.js` под `openapi.yaml`:
   `catalog`/`objects/{cad}`/`lots/{id}`/`graph`/`download`. Рендерит ту же
   ViewModel — это и есть «полный REST-рендеринг».
5. **Граф и фото на ViewModel.** KMZ-режим: текущий `graph.html`-iframe + protocol
   (postMessage `ekcelo.graph.select` + `#node=`). REST-режим: граф из
   `objects/{cad}/graph`, рисуется нативно. `graph_node_id` (C1) = `node.id` (C4) —
   единый ключ кросс-матча.

### P2–P3
6. **React-миграция.** После фаз 0–5: `ui/*.js` → React-компоненты, импортирующие
   `core/`+`adapters/` как есть; вводится Vite. ViewModel-контракт не меняется.
7. **Роли/шеринг UI (под C6).** Каталог с фильтрацией по роли, экраны делегирования
   (assessor) и передачи просмотра (client) — после контракта C6 и backend-реализации.
   Наследует токен-гейт `tokens.js`.
8. **Замена легаси.** `ekcelo/viewer/index.html` → deprecated; прод-вьюер = ekcelo-site.

## Точки стыковки

| Потребляет | От кого | Через |
|------------|---------|-------|
| C4 REST/ViewModel | backend | `api→ViewModel` |
| C1 KMZ | parser (локаль/скачивание) | `kmz→ViewModel` |

## Definition of Done

один объект рисуется идентично из `api→ViewModel` (веб) и `kmz→ViewModel`
(локальный KMZ того же Bundle); ViewModel валидна по общей схеме; граф-кросс-матч
по `graph_node_id` работает в обоих режимах (smoke в `tests/*.mjs`).
