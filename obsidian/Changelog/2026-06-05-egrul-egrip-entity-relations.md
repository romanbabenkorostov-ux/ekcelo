# 2026-06-05 — Директора/управляющие/реорг → entity_relations

## Суть
По решению заказчика добавлены не-владельческие связи субъекта в граф.
Чтобы не ломать контракт `ownership_chain` (только доли владения), заведена
отдельная таблица **`entity_relations`**.

## Сделано
- **`entity_relations`** (новая, в `egrn_parser/db/schema.sql` + авто-создание в
  модуле): `source_entity_id → target_entity_id`, `relation_type`
  (`director|managing_org|predecessor|successor`), `post`, `source`, `is_active`,
  `UNIQUE(source,target,type)`.
- **`upsert_relations(conn, record)`** (`egrul_egrip_db.py`): пишет директоров
  (target=физлицо, post), управляющие организации, право-предшественников/
  преемников (реорганизация). source = субъект записи. Идемпотентно; цель без
  ИНН → `skipped_edge`; на корневой схеме без `entity_id` → `skipped_graph`.
- `upsert_records(graph=True)` теперь пишет subject + ownership + relations;
  CLI `--db` задействует всё.
- Рефактор: `_fio_name` для отображаемого имени физлица.
- Тесты `tests/test_egrul_egrip_db.py` (+4): типы рёбер, идемпотентность,
  цель без ИНН, skip на корневой схеме. Итого по ЕГРЮЛ/ЕГРИП — **42/42**.

## Проверено e2e
АНТАРЕС: `ownership_chain` (МЕГАТЭК→АНТАРЕС 100%) + `entity_relations`
(director Оборин · ДИРЕКТОР; successor АО ПОБЕДА).

## Файлы под нож
- `parser/egrn_parser/parsers/egrul_egrip_db.py` (upsert_relations)
- `parser/egrn_parser/db/schema.sql` (+entity_relations)
- `parser/tests/test_egrul_egrip_db.py` (+4 теста)

## Дальше
- Рендер `entity_relations`/`ownership_chain` в graph_json (viewer) — отдельно.
- Реорг-рёбра предшественник/преемник теперь пишутся; статус «прекращение:
  способ» из PDF иногда null (перенос строки в pdfplumber) — мелкое улучшение
  извлечения по запросу.
