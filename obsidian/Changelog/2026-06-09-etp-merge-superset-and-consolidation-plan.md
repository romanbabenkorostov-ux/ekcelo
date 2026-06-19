# 2026-06-09 — ETP-merge суперсет-примитив + план консолидации ETL + item 3 синк

Направление: консолидация ETL (osv/exif/checko/nspd → единая точка `merge_profile`)
+ packaging-delta (item 3).

## Важное ограничение среды
ETL-тесты (`test_etl_osv/exif/checko`, `test_nspd_enricher`) **не собираются** в
среде парсера: нет `pymorphy3` и `parser.`-namespace; `pip` без сети. Поэтому
in-place рефактор 4 контрактных писателей здесь **не верифицируем** → не выполнен
вслепую. Вместо этого доведён примитив и составлен точный план.

## Сделано (верифицировано)
- **`etp_merge.merge_profile` — суперсет-примитив:** добавлены
  - `strategy='priority'|'gapfill'` (priority — приоритет-aware overwrite; gapfill —
    никогда не затирает существующее);
  - `append_keys={col:[keys]}` — аддитивное объединение списков/строк без дублей
    (семантика etl_exif advantages/notes), `_append_merge`.
  - Покрывает семантику всех 4 писателей: nspd/checko=gapfill, exif=gapfill+append,
    osv=priority.
- **Тесты** `tests/test_etp_merge.py` (+3 = 10): gapfill не затирает даже manual;
  append_keys union без дублей и идемпотентно; невалидная стратегия отклонена.
- **План консолидации** `obsidian/Architecture/etp-merge-consolidation.md`:
  маппинг каждого писателя → стратегия/вызов, нюансы (osv wholesale vs priority —
  решение заказчика; checko не ROW-источник; сохранение report-объектов), порядок
  рефактора.

## item 3 (packaging-delta) — синк
Проверено: уже готово — `pyproject.toml` (`egrn-parser` CLI v1.10, 9 команд),
`MIGRATION.md` (legacy→CLI), legacy `01_parsing_OS…`/`05_parse_egrn_folder…`
отсутствуют. SPEC item 3 → ✅ (остаток: сверка db/schema.sql с C2).

## Решение для заказчика (по osv)
`etl_osv` сейчас wholesale-перезаписывает все колонки (затирает `manual`). Переход
на `merge_profile(strategy='priority')` это чинит. Подтвердить: оставить wholesale
или priority (рекоменд.) — тогда применю рефактор там, где исполнимы ETL-тесты.

## Файлы
- `parser/egrn_parser/etp_merge.py` (+strategy/append_keys/_append_merge)
- `parser/tests/test_etp_merge.py` (+3 теста)
- `obsidian/Architecture/etp-merge-consolidation.md` (новый)
- `docs/specs/SPEC_parser.md` (item 3 ✅, item 5 дополнен)
