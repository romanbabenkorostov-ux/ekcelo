# 2026-06-04 — Хэндофф проектирования БД + конвенция fixtures/

## Суть
Зафиксированы два решения по подготовке к проектированию схем БД (соседний чат) и
доставлен хэндофф-промпт в основной репозиторий.

## Сделано
- **Граф = ЛОГИЧЕСКИЙ.** Графовая БД — вьюхи/таблицы рёбер поверх табличной модели
  (как сейчас graph.html), отдельный движок (Neo4j/Memgraph) НЕ вводим. Перенесено
  из «открытых развилок» в «жёсткие ограничения» хэндофф-промпта.
- **fixtures/ — конвенция образцов.** Образцы документов лежат в репо
  (`ekcelo/fixtures/`), без персданных; соседний чат берёт их через `git clone`
  (Claude в Drive не ходит). Заведён `fixtures/README.md` + подкаталоги по типам
  (egrn, svidetelstvo, tehpasport, egrul_egrip, osv, dogovory, photo, geo) с
  `.gitkeep` и чеклистом наполнения.
- Хэндофф-промпт положен в `obsidian/Prompts/db-schema-design-handoff.md`.

## Файлы под нож
- `obsidian/Prompts/db-schema-design-handoff.md` (новый)
- `fixtures/README.md` + подкаталоги (новые)

## Заметка о репозиториях
Прежние правки велись в отдельном клоне parser-репо (`/tmp/ekcelo-parser`) без
remote — туда push недоступен. Эта сессия привязана к `romanbabenkorostov-ux/ekcelo`,
поэтому канонический хэндофф и fixtures доставлены сюда. При необходимости —
зеркалировать в `ekcelo-parser`.

## Дальше
Заказчик наполняет `fixtures/` обезличенными образцами → соседний чат проектирует
`contracts/db/SCHEMA_SPEC.md`, `GRAPH_DB_PRINCIPLES.md`, `DOC_CLASSIFIER_SPEC.md`.
