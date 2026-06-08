# 2026-06-08 — P0.3 ViewModel sub-stage C2

## Что сделал
Добавил `GET /lots/{lot_id}` (ViewModel лота) и `GET /objects/{cad}/graph`
(граф владения) — поверх C1 (один файл сервиса). Контракт C4 (paths из
`openapi.yaml` + `viewmodel.schema.json::$defs.graphNode/graphEdge`).

## Файлы
- ✏️ `backend/app/services/viewmodel.py` — +`LotNotFound`, `build_lot_viewmodel`,
  `build_object_graph`, `_OBJECT_TYPE_TO_NODE_KIND`. Обновил docstring модуля.
- ✨ `backend/tests/test_viewmodel_c2.py` — 16 service-тестов (9 lot + 7 graph).
- ✏️ `lot_orchestrator_web/main.py` — `+GET /lots/{lot_id}`,
  `+GET /objects/{cad}/graph`.
- ✨ `lot_orchestrator_web/tests/test_viewmodel_c2_endpoint.py` — 8 endpoint-тестов.
- ✏️ `obsidian/Architecture/p0-viewmodel.md` — обновлён под C1+C2.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — C2 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live-указатель.

## Тесты
- 24 новых (16 service + 8 endpoint), все зелёные.
- Полный suite в sandbox: **243 passed** (191 baseline + 28 C1 + 24 C2).
- Регрессий в `backend/`, `lot_orchestrator/`, `lot_orchestrator_web/` нет.

## Решения

- **graph_node_id формат**:
  - object: `<cad_number>` как есть (pattern в схеме допускает `:`).
  - right: `right:<rights.id>`. ID стабилен per-DB, что подходит для
    сценария «BD = слепок» (CLAUDE.md §3): rights.id переживает повторный
    `import_bundle` (мы делаем idempotent insert по содержимому).
  - beneficiary: `inn:<inn>`. ИНН глобально уникален, не зависит от БД.
  - Все три формы укладываются в pattern `^[A-Za-z0-9_:/-]{1,256}$`
    (C1-контракт).
- **node kind маппинг** `objects.object_type → $defs.graphNode.kind`:
  - `land→land`, `building→building`, `construction→structure`,
    `flat→room`, `room→room`. Fallback на `building` для будущих значений
    (открытость как у Bundle/Manifest).
- **beneficiary kind** — по `entity_registry.entity_type == "person"` →
  `beneficiary_person`, иначе `beneficiary_legal`. Соответствует enum в схеме.
- **Lot ViewModel — aggregation strategy**:
  - `members[]` = просто список cad из `lot_items` (фронт сам делает
    $ref на `/objects/{cad}` при необходимости).
  - 4 характеристики — берём с `primary_cad_number` (если задан). Это
    компромисс: SQL-агрегация по всем членам лота требует мердж-логики
    (что приоритетнее, как агрегировать ETP-блок?) — оставляю это для
    адаптера фронта или будущего sub-stage. В C2 — простая делегация.
  - Если primary отсутствует → пустые characteristics, но валидная
    структура. Полезно для лотов «в работе» без выбранного primary.
- **graph НЕ встроен в /objects/{cad}**: отдельный endpoint позволяет фронту
  лениво подгружать граф только при разворачивании ownership-секции.
  `ownership.graph` в основной ViewModel остаётся `None` (C1-поведение).
  В C3 может агрегироваться в один ответ через `?include=graph` query.

## Канал доставки
- ⚠️ Sandbox-proxy не пропускает `git push` — продолжаем zip-handoff.
- Архив C2 будет доставлен после подтверждения, что PR C1 (`#?`) смержен.

## Следующий шаг
1. Дождаться merge PR C1.
2. Применить архив C2 на свежей main, открыть PR C2, прислать номер.
3. Старт **sub-stage C3** (KMZ-storage + download + geo materialization).
