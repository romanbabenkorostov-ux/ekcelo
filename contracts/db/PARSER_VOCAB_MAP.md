# PARSER_VOCAB_MAP — сверка C2-схемы с реальными механизмами парсеров

> Архитекторская привязка: SCHEMA_SPEC/GRAPH_DB_PRINCIPLES (черновик дата-инженера)
> ↔ что **фактически** emit'ят парсеры в репозитории `ekcelo`. Цель — чтобы
> `entities.kind` / `relation_types.code` строились из реальных выходов, а не из
> предположений. Версия: 0.1 · 2026-06-04 · grounding для C2 v0.2.

## 0. Источники (что прочитано в коде)

| Механизм | Файл | Узлы | Рёбра |
|----------|------|------|-------|
| **Граф v1.1 (Block 2)** | `parser/egrn_parser/exporters/graph_json.py` | `land`, `building`(=object_type), `accessory`, `holder` | `contains`, `owns`, `leases`, `controls` |
| **Граф v14 (KMZ-ветка)** | `parser/scripts/04_nspd_graph_v14.py` | `object`, `stub`, `right`, `enc`, `beneficiary`, `business_unit`, `level`, `equipment`, `category` | `level_in_building`, `equipment_on_level`, `equipment_at_object`, `equipment_in_bu`, + right/enc/beneficiary |
| **Канон ЕГРН-DDL** | `schema/egrn_current_schema.sql` | таблица `objects` (единая) | — |
| **Block-2 физ. БД** | запросы в `graph_json.py` | `land_objects`, `building_objects`, `accessories`, `rights`+`right_holders`, `object_geometries`, `object_events`, `company_groups`, `entity_registry`, `ownership_chain` | — |

## 1. Узлы: parser kind → `entities.kind` (C2)

| Parser kind | Ветка | C2 `entities.kind` | Статус |
|-------------|-------|--------------------|--------|
| `land` | v1.1 | `land` | ✅ |
| `building` (object_type) | v1.1/v14 `object` | `building`/`room`/`structure`/`ons` | ✅ (object_type решает) |
| `accessory` | v1.1 | — | ❌ **НЕТ в EntityKind** → добавить `accessory` |
| `holder` / `beneficiary` | v1.1/v14 | `beneficiary_legal`/`beneficiary_person` | ✅ (по `holder_type`) |
| `right` | v14 | (ребро `relations[legal]`, не узел) | ⚠️ см. §4 |
| `enc` (обременение) | v14 | (ребро `relations[legal/encumbrance]`) | ⚠️ см. §4 |
| `business_unit` | v14 | `bu` | ✅ |
| `level` (этаж) | v14 | `level` | ✅ |
| `equipment` | v14 | `equipment` | ✅ |
| `stub` (объект упомянут, выписки нет) | v1.1/v14 | (его реальный kind) + `meta.stub=true` | ⚠️ не новый kind — флаг |
| `category` (группировка) | v14 | — (это `groups[]`, не `entities`) | ✅ render-only, в граф-таблицы не пишем |

**Вывод C2 v0.2:** в `EntityKind` добавить **`accessory`**. `stub` — не kind, а `meta.stub`.
`category` — это `groups`, не узел графа (правило §3.3 GRAPH_DB_PRINCIPLES — группировки вне `relations`).

## 2. Рёбра: parser edge → `relation_types` (code/domain/category)

| Parser edge | Ветка | code | domain | category | Статус |
|-------------|-------|------|--------|----------|--------|
| `contains` (ЗУ→ОКС, ОКС→помещ., →accessory) | v1.1 | `CONTAINS` | spatial | topology | ❌ **добавить** (обратное к `INSIDE`) |
| `owns` | v1.1 | `OWNS` | legal | right | ✅ |
| `leases` | v1.1 | `LEASES` | legal | right | ✅ |
| `controls` (доля ЮЛ→ЮЛ, `share_pct`) | v1.1 | `CONTROLS` | legal | **corporate** | ❌ см. §3 (новая category) |
| `level_in_building` | v14 | `INSIDE` | spatial | topology | ✅ (level внутри building) |
| `equipment_on_level` | v14 | `LOCATED_ON` | spatial | topology | ✅ |
| `equipment_at_object` | v14 | `LOCATED_ON` | spatial | topology | ✅ |
| `equipment_in_bu` | v14 | `GROUPS` | commercial | commercial | ⚠️ группировка БА, не топология |
| right/enc edges | v14 | `OWNS`/`MORTGAGED_BY`/… | legal | right/encumbrance | ⚠️ см. §4 (right как ребро) |

## 3. Открытый вопрос: корпоративный контроль (`controls`)

`ownership_chain` даёт рёбра ЮЛ→ЮЛ с `share_pct` (бенефициарные цепочки), а EGRUL
(DOC_CLASSIFIER §3.2) — `FOUNDER_OF`/`MANAGES`. Это **не** право на недвижимость и
**не** одна из 5 доменных категорий (right/encumbrance/restriction/topology/flow/
accounting/commercial). Два варианта:

- **(A, рекомендую)** ввести category `corporate` в `relation_types.category`,
  domain=`legal`; коды `CONTROLS`(share_pct), `FOUNDER_OF`, `MANAGES`, `BRANCH_OF`.
  Граф бенефициаров — отдельный «срез» поверх legal-домена.
- (B) завести 6-й `relation_domain = corporate`. Дороже: ломает enum из 5 в C4/§5.

→ **решение заказчика/архитектора нужно** (по умолчанию беру A).

## 4. Открытый вопрос: право как РЕБРО vs УЗЕЛ

- **v1.1** и **C2** моделируют право как **ребро** `owns/leases` (holder → object). ✅ канон.
- **v14** реифицирует `right`/`enc` в **узлы** (для отрисовки атрибутов: №, дата, доля).

C2-канон: право = `relations[legal]` + `assertions/evidences`. Узлы `right`/`enc` в
v14 — это **render-time reification ребра** для viewer (показать карточку права), а
**не** доменная сущность. В `entities` их не материализуем; viewer строит их из
`relations`+`legal_relation`. Зафиксировать в GRAPH_DB_PRINCIPLES §5 (C4-рендер).

## 5. Открытый вопрос: `objects` vs `land_objects`/`building_objects`/`accessories`

Канон `egrn_current_schema.sql` — единая `objects`. Реальная Block-2 БД парсера —
раздельные `land_objects`, `building_objects`, `accessories`. C2 SCHEMA_SPEC §1–§5
наследует **единую** `objects`. Значит при интеграции нужен **импорт-маппинг**:

```
land_objects     → objects(object_type='land')        + geometries
building_objects → objects(object_type∈{building,room,structure,ons})
accessories      → entities(kind='accessory') + relations[spatial/CONTAINS] (+ geo point)
object_geometries→ geometries(WKT, original_srid=МСК-61 → srid=4326)
object_events    → assertions/evidences или temporal-поля rights
ownership_chain  → relations[legal/corporate CONTROLS] (share_pct → meta)
company_groups   → groups / entities(kind='business_asset' GROUPS)
```

`accessories` несут `lat/lon` напрямую (не WKT) — `geometries.geometry_type='POINT'`.

## 6. Что патчить в `models.py` (минимально, грунтовано кодом)

1. `EntityKind`: **+ `accessory = "accessory"`** (есть в v1.1, питает `accessories`).
2. `RelationType.category` — допустимое значение **`corporate`** (см. §3, вариант A).
3. Сид стартовых типов рёбер — `contracts/db/relation_types_seed.py` (этот пакет),
   покрывает все коды из §2 + DOC_CLASSIFIER. 

Остальное в `models.py` дата-инженера согласуется с механизмами парсеров — ✅.

## 7. Следующие шаги (для архитектора)

- [ ] Утвердить вариант §3 (corporate как category, домен legal).
- [ ] PR в C4 `viewmodel.schema.json`: `graphNode.kind` += `accessory` (+ ранее `device,
      state_body, flow_node, demarcation_point, business_asset, lot, order`).
- [ ] Alembic baseline из `models.py` + импорт-маппинг §5 (отдельная стадия parser).
- [ ] Свести graph v1.1 и v14 к одному эмиттеру поверх `relations` (убрать дубль словарей).
