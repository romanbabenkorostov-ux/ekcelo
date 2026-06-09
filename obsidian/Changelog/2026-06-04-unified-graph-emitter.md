# 2026-06-04 — Единый граф-эмиттер (relations → graph.json)

## Суть
Последний пункт плана: один эмиттер графа поверх C2 `relations`, снимающий дубль
словарей graph_json v1.1 (Block-2) и v14 (KMZ). Узлы и рёбра выводятся ИЗ табличной
модели, а не из параллельных SQL-запросов по сырым таблицам.

## Сделано
- `contracts/db/graph_emit.py` — `emit_graph(session) -> dict` + CLI. Выход совместим
  с вьювером (C1 `graph_node_id`, C4 graphNode/graphEdge): nodes/edges/groups/metadata.
  Ребро несёт `kind` (нижний регистр, как v1.1), `code` (C2), `domain`, **`confidence`**
  (из активного assertion). Уровни узлов — по топологии CONTAINS.
- `contracts/db/tests/test_graph_emit.py` — замок.

## Проверено (SQLite)
На импортированной synthetic Block-2: 6 узлов / 4 ребра; рёбра
`building --contains--> accessory`, `subj --owns/leases--> объект` (conf 1.0 ЕГРН),
`subj --controls--> subj` (conf 0.4 checko→LLM). `pytest contracts/db/tests` — 2 passed.

## Итог: план C2 закрыт
- [x] 0001 baseline §7–§12
- [x] 0002 порт §1–§6
- [x] 0003 + импортёр Block-2 (узел accessory)
- [x] единый граф-эмиттер

## Дальше (новые направления)
- Классификатор документов (`DOC_CLASSIFIER_SPEC`) — стадия `classify.py` в parser.
- Импорт остатка Block-2: company_groups/business_units/valuations/object_events.
- PR в C4 `viewmodel.schema.json` (kind += accessory и др.).
