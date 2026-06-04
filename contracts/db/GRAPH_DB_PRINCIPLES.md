# GRAPH_DB_PRINCIPLES — принципы графовой БД EKCELO

> Логический граф поверх табличной C2 (ответ 2). Узлы/рёбра **выводимы** из таблиц,
> рендерятся graph.html (C1, `graph_node_id`) и ViewModel (C4, `graphNode/graphEdge`).
> Реальный движок (Neo4j) НЕ вводим. Применено `разделение графовых доменов.md`.
> Версия: 0.1 · 2026-06-04.

## 1. Базовая триада

```
Entity  →  Relation (+domain)  →  Assertion  →  Evidence
узел       ребро модели мира      утверждение    доказательство (source+weight)
```

- **Relation ≠ Assertion.** Relation — факт связи в модели мира; Assertion — утверждение
  о её существовании с `confidence`; Evidence — доказательство (документ/источник).
  Это снимает перегрузку единой таблицы рёбер (проблема §2 вложения).
- **Узел = `entities`** (адресная строка над таблицей-владельцем). Любая сущность
  (объект, субъект, документ, КИП, лот, БА, точка разграничения) может быть узлом.
- **Ребро = `relations`** + 1:1 доменное расширение (`legal_/tech_/spatial_/accounting_relation`).

## 2. Доменное разделение (5 сегментов)

| Домен | Что моделирует | Типы рёбер | Расширение |
|-------|----------------|-----------|------------|
| **legal** | права/обременения/ограничения | OWNS, LEASES, OPERATES, SERVITUDE, MORTGAGED_BY, ARRESTED_BY, RESTRICTED_BY | `legal_relation` |
| **spatial** | топология объектов | LOCATED_ON, INSIDE, INTERSECTS, ADJACENT_TO | `spatial_relation` |
| **tech** | потоки/инфраструктура | MOVED_TO, FEEDS, TRANSFORMS_TO, CONNECTED_TO | `tech_relation` |
| **accounting** | балансовая принадлежность (ОСВ) | ON_BALANCE_OF, LEASED_IN_BALANCE, CAPITALIZED_BY | `accounting_relation` |
| **commercial** | лоты/заказы/группировки | INCLUDED_IN_LOT, SUBJECT_OF_ORDER, GROUPS | — |

**Правила (из §15 вложения):**
1. НЕ смешивать ownership (legal) и topology (spatial) в одном ребре.
2. НЕ хранить telemetry в графе — только `flow_events`-агрегаты (tech).
3. НЕ хранить геометрию в графе — только `geometries.bbox` по ссылке.
4. Assertion НЕ используется как ребро напрямую — ребро это Relation.
5. `legal_owner` может ≠ `accounting_balance_holder` (две разные связи, оба валидны).

## 3. Битемпоральность рёбер

Каждый Relation и Assertion: `valid_from/valid_to` (Since/Until — реальное время связи) +
`recorded_at/superseded_at` (KnownSince/KnownUntil — системное). Срез графа «на дату» =
фильтр `valid_from <= D < valid_to AND superseded_at IS NULL`. Лот берёт `as_of_date`.

## 4. Вероятностная истина

- `assertion.confidence_score = 1 - Π(1 - wᵢ)` по согласным Evidence (`SOURCE_WEIGHTS`).
- Competing assertions на один Relation хранятся все; **активная = max(confidence)**,
  tie-break по `recorded_at`; ручной override асесора → `status` + пометка `asserted_by`.
- Совместимо с ADR-003 темой 3 (ranked-list резолвер) — без слома v1.

## 5. Согласование с C1/C4

- `entity.graph_node_id` ⟷ KMZ `ExtendedData/graph_node_id` (C1). UUID удовлетворяет паттерну.
- `entity.kind` ⊇ `viewmodel.schema.json#/$defs/graphNode.kind` (добавлены `device, state_body,
  flow_node, demarcation_point, business_asset, lot, order`) — **PR в C4 нужен**.
- `relation` → `graphEdge{from,to,kind}`; `kind = relation_types.code`.
- ViewModel facets: legal-рёбра → `ownership.graph`; объекты → `physical`; `geometries` → `geo`;
  битемпоральные поля → `temporal`.

## 6. Узлы-выводимость (как граф строится из таблиц)

| Узел (`kind`) | Источник строки | graph_node_id (пример) |
|---------------|-----------------|------------------------|
| land/building/room/structure/ons | `objects` | `<kind>:<cad_number>` |
| beneficiary_legal/person, state_body | `subjects` | `subj:<inn>` |
| equipment/device | `devices` | `dev:<serial>` |
| flow_node | `entities`(infra) | `node:<slug>` |
| demarcation_point | `entities` | `demarc:<slug>` |
| doc | `documents` | `doc:<hash8>` |
| lot / order / business_asset | `lots`/`orders`/БА | `lot:<lot_id>` |

Рёбра — `JOIN relations + relation_types`. Для обхода (цепочка прав, маршрут потока,
expansion лота) — рекурсивные CTE на PG / итеративно на SQLite. Материализация в
`graph.json` (v14) остаётся выходом парсера.

## 7. Спец-узлы

- **Точка разграничения баланса** (`demarcation_point`): отдельный узел на коммуникации,
  разрывает `CONNECTED_TO` между сетевой организацией и объектом. Импорт из договоров снабжения.
- **Поток-трансформатор**: узел-оборудование; вход/выход — `tech_relation.material_type_in/out`
  + `conversion_ratio`/`loss_factor` (семечка → масло+шрот+лузга).
- **Узел-накопитель**: `devices.max_capacity`; `current_level` считается из `flow_events`, не хранится.
- **Бизнес-актив (БА)**: группировочный узел, рёбра `GROUPS` → активы/НМА.
