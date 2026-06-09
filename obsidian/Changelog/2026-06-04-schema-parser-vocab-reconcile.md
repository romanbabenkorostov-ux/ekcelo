# 2026-06-04 — Схема C2 ↔ реальные механизмы парсеров (сверка)

## Суть
Продолжение схемы БД дата-инженера, **грунтованное кодом парсеров** (а не описанием).
Прочитаны два графовых эмиттера + физическая Block-2 БД; найдены расхождения словарей
узлов/рёбер с черновиком C2; выпущена сверка + сид типов рёбер.

## Сделано
- **`contracts/db/PARSER_VOCAB_MAP.md`** — карта parser-kind/edge → `entities.kind`/
  `relation_types`. Источники: `egrn_parser/exporters/graph_json.py` (v1.1:
  land/building/accessory/holder; contains/owns/leases/controls) и
  `scripts/04_nspd_graph_v14.py` (object/stub/right/enc/beneficiary/business_unit/
  level/equipment/category; level_in_building/equipment_*).
- **`contracts/db/relation_types_seed.py`** — 30 стартовых типов рёбер, все рёбра
  обоих парсеров замаплены (`PARSER_EDGE_TO_CODE`), домены в пределах 5-enum. Валидирован.

## Найденные расхождения (вынесены в PARSER_VOCAB_MAP)
1. `accessory` (узел v1.1, питает `accessories`) **отсутствует** в `EntityKind` → +1 строка.
2. `controls`/EGRUL-цепочки не влезают в 5 категорий → предложена category **`corporate`** (домен legal).
3. v14 реифицирует право в **узел**, C2/v1.1 — в **ребро**; канон = ребро, right-node = render-time.
4. Канон `objects` (единая) vs Block-2 `land_objects`/`building_objects`/`accessories` →
   нужен импорт-маппинг (§5 документа).

## Файлы под нож
- `contracts/db/PARSER_VOCAB_MAP.md` (новый)
- `contracts/db/relation_types_seed.py` (новый)
- патч `models.py`: `EntityKind += accessory` (1 строка, см. §6 документа)

## Решение заказчика нужно
- Вариант §3: `corporate` как category (по умолчанию беру A).

## Дальше
Alembic-baseline из `models.py` + стадия импорта Block-2 БД → §1–§5 `objects` + граф-таблицы;
сведение graph v1.1/v14 к одному эмиттеру поверх `relations`.
