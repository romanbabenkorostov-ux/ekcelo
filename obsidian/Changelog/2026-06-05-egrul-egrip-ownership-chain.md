# 2026-06-05 — Учредители → граф владения ownership_chain

## Суть
Связи учредителей пишутся в существующую таблицу `ownership_chain`
(`egrn_parser/db/schema.sql`, её уже читает `graph_json.py`). Решение заказчика:
писать в граф сейчас. Директора/управляющие — НЕ владение, остаются в JSON.

## Сделано (`egrul_egrip_db.py`)
- **`upsert_ownership(conn, record)`**: учредитель → `parent_entity_id`,
  субъект → `child_entity_id`, доля % → `share_pct`, источник → `source`.
  Идемпотентно по `UNIQUE(child, parent)` (повтор → update ребра, без дублей).
  Учредитель без ИНН → `skipped_edge`. Авто-создание `ownership_chain` на
  свежей БД; на корневой схеме (без `entity_id`) — мягкий `skipped_graph`.
- **Рефактор**: общий `_write_entity(conn, values)` (запись identity по
  существующим колонкам) — используется и для субъекта, и для учредителей (DRY).
- `upsert_records(..., graph=True)` — пишет subject + рёбра владения; CLI `--db`
  задействует обе. В выводе CLI — `inserted/updated_edge`.
- Тесты `tests/test_egrul_egrip_db.py` (+3): рёбра, идемпотентность,
  skip на корневой схеме. Итого по ЕГРЮЛ/ЕГРИП — **38/38**.

## Проверено end-to-end
PDF (ООО ПРИМЕР, учредитель ООО МАТЕРИНСКАЯ 100%) → `ownership_chain`:
`parent 7700000000 → child 7707083893, share 100, source ФНС-ЕГРЮЛ-PDF`.

## Файлы под нож
- `parser/egrn_parser/parsers/egrul_egrip_db.py` (upsert_ownership + рефактор)
- `parser/tests/test_egrul_egrip_db.py` (+3 теста)

## Дальше
- Директора/управляющие — нет таблицы под менеджмент; при необходимости
  отдельное решение (management-таблица или роль в графе) — согласовать с
  `contracts/db`.
- Правопредшественники/правопреемники (реорганизация) — отдельный тип ребра
  (не владение); по запросу.
