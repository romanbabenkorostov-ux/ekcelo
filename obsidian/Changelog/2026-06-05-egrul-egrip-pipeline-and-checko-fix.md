# 2026-06-05 — End-to-end связка ЕГРЮЛ/ЕГРИП + фикс checko по живому ответу

## Суть
Заказчик прогнал `fetch_by_inn` с реальным ключом checko (ИНН 2312122992,
ООО «АНТАРЕС») — маппер сработал, но вскрылись две правки по живому ответу.
Плюс добавлена связка «PDF → ИНН → обогащение → merge» (CLI).

## Сделано
- **Фикс checko-маппера по реальному ответу** (`egrul_egrip_sources.py`):
  - имя ОКВЭД приходит под ключом `Наим` (было только `Наименование`) →
    раньше `okved_main.name=null`. Добавлен fallback `Наим|Наименование|Название`.
  - `Руковод` может быть объектом, не списком, и ключ `Руководитель` —
    добавлена нормализация (dict→[dict]) и альт-ключ.
- **Пайплайн** `egrul_egrip_pipeline.py`:
  - `parse_any(path)` — автоопределение XML ФНС / PDF / текст;
  - `enrich_record(rec, vendor)` — по ИНН тянет checko/dadata и сливает
    (`merge_records`, официальный XML/PDF приоритетнее); без ИНН/ключа не падает,
    пишет `source.enrich_error`, в сеть без ключа НЕ ходит;
  - CLI: `python -m egrn_parser.parsers.egrul_egrip_pipeline ВЫПИСКА.pdf [--enrich checko]`.
- **Тесты** `tests/test_egrul_egrip_pipeline.py` (7, сеть замокана). Итого по
  ЕГРЮЛ/ЕГРИП — **24/24 зелёных**.

## Файлы под нож
- `parser/egrn_parser/parsers/egrul_egrip_sources.py` (фикс ОКВЭД/Руковод)
- `parser/egrn_parser/parsers/egrul_egrip_pipeline.py` (новый)
- `parser/tests/test_egrul_egrip_pipeline.py` (новый)

## Дальше
- Враппер «запись → §6 legal-слой БД» (блокер: `contracts/db/SCHEMA_SPEC.md`).
- Точная сверка остальных полей checko (директора/статус) по сырому JSON, если
  понадобится больше, чем ИНН/ОГРН/учредители/ОКВЭД.
