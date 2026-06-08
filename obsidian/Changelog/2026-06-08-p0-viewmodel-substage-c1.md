# 2026-06-08 — P0.3 ViewModel sub-stage C1

## Что сделал
Реализовал ядро ViewModel-сервиса и два REST-эндпоинта `/catalog` +
`/objects/{cad}` по контракту C4 (`contracts/api/openapi.yaml` +
`viewmodel.schema.json`).

## Файлы
- ✨ `backend/app/services/viewmodel.py` — Pydantic ViewModel + CatalogCard,
  `build_catalog`, `build_object_viewmodel`.
- ✨ `backend/tests/test_viewmodel.py` — 18 тестов.
- ✏️ `lot_orchestrator_web/main.py` — `+GET /catalog`, `+GET /objects/{cad}`,
  `+_require_ekcelo_db`, `+ekcelo_db` параметр в `create_app` (env `EKCELO_DB`).
- ✨ `lot_orchestrator_web/tests/test_viewmodel_endpoint.py` — 10 тестов.
- ✨ `obsidian/Architecture/p0-viewmodel.md` — снимок C1.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — C1 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — обновлён live-указатель.

## Тесты
- 28 новых (18 service + 10 endpoint), все зелёные.
- Полный suite в sandbox: **219 passed** (191 baseline + 28 C1).
- Регрессий в `backend/`, `lot_orchestrator/`, `lot_orchestrator_web/` нет.

## Покрытие
- catalog: objects+lots, latest extract_date, kind/q фильтры, БД без `lots`.
- object-VM: 4 характеристики, ETP-блок (parsed/absent/no-table), rights
  с долей `num/den`, beneficiaries (dedup, sort), as_of-фильтр rights, geo-stub,
  ObjectNotFound, structural smoke vs `viewmodel.schema.json`.
- endpoints: 200 happy path, 422 на bad kind, 404 для несуществующего cad,
  503 если `EKCELO_DB` не сконфигурирован.

## Решения
- **ekcelo_db конфиг через env/factory, не form-param.** Контракт C4 в
  `openapi.yaml` не предусматривает `target_db` параметр для `/catalog`,
  `/objects/{cad}` — это деплой-уровень. Сделал: `create_app(ekcelo_db=)` или
  env `EKCELO_DB`, иначе 503. Симметрия с `/bundles/import` сохраняется (тот
  явно берёт `target_db` из формы — это его контракт).
- **geo — stub.** Не материализую центр/геометрию из rows-данных; реальная
  геометрия приходит из KMZ-парсера, который в БД её пока не пишет.
  Колонки `geo_*` или sidecar-таблица — задача sub-stage C3 после KMZ-storage.
- **graph — None.** `ownership.graph` оставлен `None` в C1. Построение узлов/
  рёбер (`graph_node_id` из C1-контракта) — отдельный эндпоинт
  `GET /objects/{cad}/graph` в C2, чтобы не раздувать `/objects/{cad}` ответ.
- **q-фильтр in-memory.** Поскольку каталог небольшой (десятки-сотни лотов),
  фильтрация в Python проще и портабельнее SQLite `LIKE` (case-insensitive
  кириллицу LIKE плохо обрабатывает без коллаций).
- **as_of**: примитивный snapshotting (фильтр по `registration_date <= as_of`)
  для прав. Полный snapshot (точечный JOIN на extract версии) — C2/C3.

## Канал доставки
- ⚠️ Sandbox-proxy не пропускает `git push` (auth fail), zip-handoff остаётся
  активным. Архив C1 → `SendUserFile`.
- См. `obsidian/UserGuide/local-handoff-workflow.md`.

## Следующий шаг
1. Пользователь применит архив C1, откроет PR `backend/p0-viewmodel`, сообщит
   номер.
2. Старт **sub-stage C2** — `GET /lots/{lot_id}` + `GET /objects/{cad}/graph`.
