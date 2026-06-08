# P0.3 — ViewModel REST (sub-stage C1)

> Реализация `SPEC_backend.md §P0.3` — веб-шов backend↔frontend (полный
> REST-рендеринг). Контракт C4: `contracts/api/openapi.yaml` +
> `viewmodel.schema.json`. Этот документ — снимок состояния после **C1**.

## Зачем

ViewModel — единая нормализованная форма объекта/лота, которую рендерит фронт
напрямую. KMZ/DB/JSON уходят только на скачивание. 4 канонические
характеристики EKCELO:

```
physical   ЧТО ЭТО      object_type, address, area, floors, ЭТП §6
ownership  ЧЬЁ ЭТО      rights, beneficiaries, граф владения (C2)
geo        ГДЕ ЭТО      center, geometry WGS84, z_meters_top (stub→C3)
temporal   КОГДА ЭТО    extract_date, as_of_date
```

Производят ViewModel два адаптера:
1. `kmz→ViewModel` (parser, C2-стрим, фронт-локаль для оффлайн-просмотра).
2. `api→ViewModel` (`backend/app/services/viewmodel.py`, этот подэтап).

## Слои (C1)

```
┌─ REST ────────────────────────────────────────────────┐
│ lot_orchestrator_web/main.py                           │
│   GET  /catalog?q&kind         → [CatalogCard]         │
│   GET  /objects/{cad}?as_of    → ViewModel             │
│   helper: _require_ekcelo_db (503 если не сконфиг.)    │
└───────────┬───────────────────────────────────────────┘
            │
┌─ Service (ядро) ──────────────────────────────────────┐
│ backend/app/services/viewmodel.py                      │
│   Pydantic: Physical/Ownership/Geo/Temporal/ViewModel  │
│              CatalogCard + Beneficiary/RightItem       │
│   build_catalog(db, q?, kind?) → list[CatalogCard]     │
│   build_object_viewmodel(db, cad, as_of?) → ViewModel  │
└───────────┬───────────────────────────────────────────┘
            ▼
        ekcelo.sqlite (§1..§6 — слепок ЕГРН + ЭТП-профиль)
        путь: env EKCELO_DB или create_app(ekcelo_db=...)
```

## Поведение

### `build_catalog`

- Объединяет `objects` + `lots` в плоский список карточек.
- `extract_date` карточки object — `MAX(extract_date)` по `extracts.cad_number`.
- `title`: cad для object, `lots.name` для lot.
- `address` для lot — берётся с `objects.address` по `primary_cad_number`.
- Фильтры:
  - `q` — case-insensitive substring по `id|title|address` (in-memory после
    выборки; объём каталога умеренный).
  - `kind ∈ {object, lot}` — типовой срез.
- Толерантна к БД без таблиц `lots`/`extracts` (старые ЕГРН-слепки).

### `build_object_viewmodel`

- `objects.cad_number` отсутствует → `ObjectNotFound` (→ 404 в эндпоинте).
- `physical.etp` — JSON-блок из `object_etp_profile` (`location_extra`,
  `building_extra`, `layout`, `legal_extra`, `risks`, `extras` + `source`,
  `confidence`). Парсится через `json.loads` с защитой от битого JSON.
- `ownership.rights` — все `rights` объекта, доля форматируется `"num/den"`.
- `ownership.beneficiaries` — `entity_registry` по уникальным ИНН из `rights`,
  отсортированы по ИНН.
- `ownership.graph = None` — будет заполнено в **C2**.
- `geo` — stub (`Geo()` default). Геометрия материализуется в БД в **C3**
  (после регистрации KMZ-парсера).
- `temporal.extract_date` — последняя выписка по cad.
- `temporal.as_of_date` — эхо параметра + фильтр `rights.registration_date
  <= as_of` (примитивный снапшоттинг; полный snapshot — C2/C3).

## REST: эндпоинты

| Метод | Путь | Параметры | Тело ответа |
|---|---|---|---|
| GET | `/catalog` | `q?`, `kind? ∈ {object,lot}` | `200` JSON-массив CatalogCard |
| GET | `/objects/{cad}` | `as_of? (YYYY-MM-DD)` | `200` ViewModel \| `404` если нет |

Общее: `503` если `ekcelo_db` не сконфигурирован (env `EKCELO_DB` пуст и в
`create_app(ekcelo_db=)` не передан).

## Конфигурация

- `create_app(ekcelo_db=Path("/path/to/ekcelo.sqlite"))` — явно.
- ИЛИ env `EKCELO_DB=/path/to/ekcelo.sqlite` — для деплоя.
- Если ничего — эндпоинты `/catalog` + `/objects/{cad}` отвечают 503.
- Эндпоинт `/bundles/import` (sub-stage B) использует `target_db` из формы,
  поэтому НЕ зависит от этой настройки.

## Что НЕ в этом подэтапе (плановое разделение)

Будет в **sub-stage C2**:
- `GET /lots/{lot_id}` — ViewModel лота (kind=lot, members[], lot-уровневая
  ownership-агрегация).
- `GET /objects/{cad}/graph` — узлы/рёбра графа владения (`graph_node_id` из
  C1-контракта, `ownership.graph` в ViewModel).

Будет в **sub-stage C3**:
- KMZ-storage (`bundles/<id>.kmz` + sidecar-таблица `bundles`) — приём
  привязан к `POST /bundles/import` (расширение).
- `GET /bundles/{id}/download?fmt={kmz|db|json|zip}` — реверс-экспорт Bundle
  из БД (идемпотентный round-trip).
- `geo` populating: центр/геометрия из KMZ → колонки `objects.geo_*` или
  sidecar-таблица.

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `backend/app/services/viewmodel.py` | ~340 | Pydantic + build_catalog + build_object_viewmodel |
| `backend/tests/test_viewmodel.py` | ~250 | 18 service-тестов |
| `lot_orchestrator_web/main.py` | +60 | `+GET /catalog`, `+GET /objects/{cad}`, `+_require_ekcelo_db`, `+ekcelo_db` parameter |
| `lot_orchestrator_web/tests/test_viewmodel_endpoint.py` | ~170 | 10 endpoint-тестов |

**Тесты:** 28 viewmodel (18 + 10); полный suite в sandbox **219 pass**
(191 baseline + 28 C1).

Покрытие:
- Service catalog: objects+lots, latest extract_date, kind-фильтр, q-фильтр
  (case-insensitive), пустой результат, БД без lots-таблицы.
- Service object-VM: базовые поля, ETP-блок (parsed), отсутствие ETP, отсутствие
  ETP-таблицы, rights+beneficiaries, dedup beneficiaries, latest extract,
  as_of-фильтр прав, geo-stub, not-found, serialize-to-dict (структурный
  smoke против `viewmodel.schema.json`).
- Endpoint catalog: 200+карточки, kind-фильтр, q-фильтр, 422 на bad kind,
  503 без БД.
- Endpoint object: 4 характеристики в ответе, rights resolved, 404, as_of
  round-trip, 503 без БД.

## Связи

- Контракт: `contracts/api/viewmodel.schema.json` + `contracts/api/openapi.yaml`
  (paths `/catalog`, `/objects/{cad}`).
- Спека: `docs/specs/SPEC_backend.md` §P0.3.
- Предшественник: `obsidian/Architecture/p0-bundle-importer.md` (A+B).
- ADR-001 §6: ЭТП-слой `manual/osv` приоритет — соблюдается на этапе ИМПОРТА
  (`bundle.py`); этот модуль только читает финальное состояние.
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md`.
