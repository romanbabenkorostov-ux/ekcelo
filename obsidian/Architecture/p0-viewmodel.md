# P0.3 — ViewModel REST (sub-stages C1 + C2)

> Реализация `SPEC_backend.md §P0.3` — веб-шов backend↔frontend (полный
> REST-рендеринг). Контракт C4: `contracts/api/openapi.yaml` +
> `viewmodel.schema.json`. Этот документ — снимок состояния после **C1 + C2**.

## Зачем

ViewModel — единая нормализованная форма объекта/лота, которую рендерит фронт
напрямую. KMZ/DB/JSON уходят только на скачивание. 4 канонические
характеристики EKCELO:

```
physical   ЧТО ЭТО      object_type, address, area, floors, ЭТП §6
ownership  ЧЬЁ ЭТО      rights, beneficiaries, граф владения
geo        ГДЕ ЭТО      center, geometry WGS84, z_meters_top (stub→C3)
temporal   КОГДА ЭТО    extract_date, as_of_date
```

Производят ViewModel два адаптера:
1. `kmz→ViewModel` (parser, C2-стрим, фронт-локаль для оффлайн-просмотра).
2. `api→ViewModel` (`backend/app/services/viewmodel.py`, этот подэтап).

## Слои (C1 + C2)

```
┌─ REST ──────────────────────────────────────────────────────┐
│ lot_orchestrator_web/main.py                                 │
│   GET  /catalog?q&kind        → [CatalogCard]        (C1)    │
│   GET  /objects/{cad}?as_of   → ViewModel            (C1)    │
│   GET  /lots/{lot_id}?as_of   → ViewModel (kind=lot) (C2)    │
│   GET  /objects/{cad}/graph   → {nodes[], edges[]}   (C2)    │
│   helper: _require_ekcelo_db (503 если не сконфиг.)          │
└───────────┬─────────────────────────────────────────────────┘
            │
┌─ Service (ядро) ────────────────────────────────────────────┐
│ backend/app/services/viewmodel.py                            │
│   Pydantic: Physical/Ownership/Geo/Temporal/ViewModel        │
│              CatalogCard + Beneficiary/RightItem (C1)        │
│   build_catalog(db, q?, kind?)           → list[CatalogCard] │
│   build_object_viewmodel(db, cad, as_of?)→ ViewModel    (C1) │
│   build_lot_viewmodel(db, lot_id, as_of?)→ ViewModel    (C2) │
│   build_object_graph(db, cad)            → {nodes,edges}(C2) │
└───────────┬─────────────────────────────────────────────────┘
            ▼
        ekcelo.sqlite (§1..§6 — слепок ЕГРН + ЭТП-профиль)
        путь: env EKCELO_DB или create_app(ekcelo_db=...)
```

## Поведение (C1)

### `build_catalog`
- Объединяет `objects` + `lots` в плоский список карточек.
- `extract_date` карточки object — `MAX(extract_date)` по `extracts.cad_number`.
- `title`: cad для object, `lots.name` для lot.
- `address` для lot — берётся с `objects.address` по `primary_cad_number`.
- Фильтры:
  - `q` — case-insensitive substring по `id|title|address`.
  - `kind ∈ {object, lot}` — типовой срез.
- Толерантна к БД без таблиц `lots`/`extracts`.

### `build_object_viewmodel`
- `objects.cad_number` отсутствует → `ObjectNotFound` (→ 404 в эндпоинте).
- `physical.etp` — JSON-блок из `object_etp_profile` (parsed).
- `ownership.rights` — все `rights` объекта, доля `num/den`.
- `ownership.beneficiaries` — `entity_registry` по уникальным ИНН, sort.
- `ownership.graph = None` — для запроса графа используется отдельный
  endpoint `/objects/{cad}/graph` (C2; см. ниже).
- `geo` — stub (C3).
- `temporal.extract_date` — последняя выписка по cad.
- `as_of` — фильтр `rights.registration_date <= as_of`.

## Поведение (C2)

### `build_lot_viewmodel`
- `lots` таблицы нет или `lot_id` нет → `LotNotFound`.
- `members[]` — все `lot_items.cad_number`, отсортированные по `(ord, cad)`.
- 4 характеристики берутся с `lots.primary_cad_number` (если задан и
  присутствует в `objects`):
  - `physical`/`ownership`/`temporal` — те же сборщики что и для object-VM,
    применённые к primary_cad.
  - `geo` — stub (как и для object-VM).
- Если primary отсутствует — характеристики пустые, но валидны (вложенные
  поля optional).

### `build_object_graph`
- `cad` нет в `objects` → `ObjectNotFound`.
- Возвращает `{nodes: [...], edges: [...]}` по контракту
  `viewmodel.schema.json::$defs.graphNode/graphEdge`.
- **graph_node_id** (C1-контракт, pattern `^[A-Za-z0-9_:/-]{1,256}$`):
  | Узел | id-формат | Пример |
  |---|---|---|
  | object | `<cad_number>` | `61:44:0050706:31` |
  | right | `right:<rights.id>` | `right:42` |
  | beneficiary (legal/person) | `inn:<inn>` | `inn:7707083893` |
- **node kind** (из `$defs.graphNode.kind` enum):
  - object: маппинг `objects.object_type` → `{land, building, room, structure}`
    (`land→land`, `building→building`, `construction→structure`,
    `flat→room`, `room→room`); неизвестное → fallback `building`.
  - right: `right`.
  - beneficiary: `beneficiary_person` если `entity_registry.entity_type ==
    "person"`, иначе `beneficiary_legal`.
- **edge kinds**:
  - `object → right`: `has_right`
  - `right → beneficiary`: `held_by`
- **Деградация**: если `rights.right_holder_inn` указан, но ИНН отсутствует
  в `entity_registry` — добавляется beneficiary-узел с `label=inn`,
  `kind=beneficiary_legal`. Связь `held_by` рисуется.

## REST: эндпоинты

| Метод | Путь | Параметры | Тело ответа |
|---|---|---|---|
| GET | `/catalog` | `q?`, `kind? ∈ {object,lot}` | `200` JSON-массив CatalogCard |
| GET | `/objects/{cad}` | `as_of? (YYYY-MM-DD)` | `200` ViewModel \| `404` |
| GET | `/lots/{lot_id}` | `as_of? (YYYY-MM-DD)` | `200` ViewModel (kind=lot) \| `404` |
| GET | `/objects/{cad}/graph` | — | `200` `{nodes,edges}` \| `404` |

Общее: `503` если `ekcelo_db` не сконфигурирован.

## Конфигурация

- `create_app(ekcelo_db=Path("/path/to/ekcelo.sqlite"))` — явно (тесты).
- ИЛИ env `EKCELO_DB=/path/to/ekcelo.sqlite` — для деплоя.
- Если ничего — ViewModel-эндпоинты отвечают 503.
- Эндпоинт `/bundles/import` (sub-stage B) использует `target_db` из формы,
  поэтому НЕ зависит от этой настройки.

## Что НЕ в этом подэтапе (плановое разделение)

Будет в **sub-stage C3**:
- KMZ-storage (`bundles/<id>.kmz` + sidecar-таблица `bundles`) — расширение
  `POST /bundles/import` сохраняет загруженный KMZ.
- `GET /bundles/{id}/download?fmt={kmz|db|json|zip}` — реверс-экспорт.
- Материализация `geo` (центр/геометрия из KMZ → колонки `objects.geo_*`
  или sidecar `object_geometry`).
- Заполнение `ownership.graph` в `build_object_viewmodel` (сейчас отдельный
  endpoint; в C3 может агрегироваться в основной ViewModel за один запрос).

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `backend/app/services/viewmodel.py` | ~570 | Pydantic + 4 builder-функции |
| `backend/tests/test_viewmodel.py` | ~250 | 18 service-тестов (C1) |
| `backend/tests/test_viewmodel_c2.py` | ~290 | 16 service-тестов (C2) |
| `lot_orchestrator_web/main.py` | +160 | 4 GET-эндпоинта + helper + `ekcelo_db` |
| `lot_orchestrator_web/tests/test_viewmodel_endpoint.py` | ~170 | 10 endpoint-тестов (C1) |
| `lot_orchestrator_web/tests/test_viewmodel_c2_endpoint.py` | ~170 | 8 endpoint-тестов (C2) |

**Тесты:** 52 viewmodel (28 C1 + 24 C2); полный suite в sandbox **243 pass**
(191 baseline + 28 C1 + 24 C2).

Покрытие C1: см. `obsidian/Changelog/2026-06-08-p0-viewmodel-substage-c1.md`.

Покрытие C2:
- Service lot-VM: базовый, ordering members по `ord`, агрегация с primary,
  no-primary fallback, пустой лот, as_of propagate, LotNotFound (включая
  отсутствие таблицы `lots`), пустая `lot_items`.
- Service graph: 4 типа узлов в одном графе, node_id формат (contract),
  edges has_right/held_by, объект без прав = одиночный узел, маппинг типа
  `construction → structure`, ObjectNotFound, уникальность узлов.
- Endpoint lot: 200+ViewModel, as_of round-trip, 404, 503 без БД.
- Endpoint graph: 200+nodes+edges, has_right/held_by, 404, 503 без БД.

## Связи

- Контракт: `contracts/api/viewmodel.schema.json` + `contracts/api/openapi.yaml`.
- Спека: `docs/specs/SPEC_backend.md` §P0.3.
- Предшественник: `obsidian/Architecture/p0-bundle-importer.md` (A+B).
- ADR-001 §6: ЭТП-слой `manual/osv` приоритет — соблюдается на этапе ИМПОРТА
  (`bundle.py`); этот модуль только читает финальное состояние.
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md`.
