# 2026-06-03 — Три spec команд + пакет contracts/ (Consistency Target v1.0)

## Задача

Свести три кодовые базы (parser локальный / ekcelo backend / ekcelo-site frontend)
к единой точке консистентности для веб-версии (фронт+бэк) + локальных парсеров и
идемпотентного экспорта-импорта данных по объекту/лоту. Только спеки, без кода.

## Что сделано

- Заведён пакет **`contracts/`** (Consistency Target v1.0, `contracts v1.0.0`):
  - `PACKAGE.md` — состав, версионирование, sync-правило, Definition of Convergence;
  - **C3** `bundle/BUNDLE_SPEC.md` + `bundle.schema.json` — каноническая единица обмена
    (kmz+db+json+manifest, идемпотентна);
  - **C4** `api/openapi.yaml` + `viewmodel.schema.json` — REST + нормализованная ViewModel
    (4 характеристики: physical/ownership/geo/temporal);
  - **C5** `lot/LOT_SPEC.md` — лот (include/exclude + as-of, активы∪права);
  - **C6** `roles/ROLES_SPEC.md` — роли/шеринг (контракт сейчас, реализация после).
- Три spec команд в `docs/specs/`: `SPEC_parser.md`, `SPEC_backend.md`, `SPEC_frontend.md`.

## Ключевые решения (развилки пользователя)

1. Репо раздельно + общий синкаемый пакет `contracts/`; `ekcelo/viewer` → deprecated в пользу ekcelo-site.
2. Веб-шов = **полный REST-рендеринг**: фронт рисует ViewModel из API; KMZ — для скачивания/GE Pro/локали.
3. Единица обмена = **Bundle** (kmz+db+json+manifest).
4. Роли — контракт зафиксирован, реализация отдельной итерацией.

## Связующая находка

Веб + локаль примиряются через **ViewModel** с двумя адаптерами: `kmz→ViewModel`
(C1) и `api→ViewModel` (C4) дают эквивалентную модель → ui (Leaflet/React) рисует
одинаково. Кросс-матч графа — `graph_node_id` (C1) == `node.id` (C4).

## Точка «стали консистентны» (M3)

На 1 реальном лоте: parser→Bundle vN → backend импорт+ViewModel+реэкспорт → фронт
рисует из REST И из локального KMZ идентично → round-trip по `sha256` стабилен.

## Канонические версии парсеров (дедуп)

enrich **v17** · nspd_graph **v15** · build_kmz **v2_5** · init_project **v4** · make_structure **v2_2**.

## Дальше

Реализация — отдельными итерациями под зафиксированные контракты (см. майлстоуны
M0–M5 в плане). Governance изменений контрактов — `CONTRACT_KMZ.md` §3.
