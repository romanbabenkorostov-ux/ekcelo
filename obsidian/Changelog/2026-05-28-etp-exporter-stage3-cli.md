# 2026-05-28 — ЭТП-экспортёр Stage 3: CLI + Markdown-приложение

## Итог
Финальный слой ЭТП-экспортёра — CLI и приложение к лоту. Полный путь от БД до файлов готов к подключению из golden path экономиста.

## Артефакты
- `parser/exporters/etp/appendix.py` — `build_lot_appendix(conn, lot_id) → str`. Markdown-приложение к лоту: параметры процедуры, состав КН, пометки экономиста, отсылка к отчёту оценщика. PDF-конверсия делегируется существующему пайплайну python-docx → LibreOffice (см. `dev/SPEC_TEMPORAL_REPORTS.md`).
- `parser/exporters/etp/cli.py` — argparse CLI: `python -m parser.exporters.etp.cli --lot <id> --db <path> --platforms ... --modes ... --out <dir>`.
- `parser/tests/test_etp_cli_integration.py` — 9 end-to-end тестов (реальная sqlite на диске + миграция + фикстура → запуск main() → проверка файлов).

## CLI usage
```bash
python -m parser.exporters.etp.cli \
  --lot lot:pirushin:001 \
  --db path/to/ekcelo.sqlite \
  --platforms torgi.gov.ru,sberbank-ast.ru \
  --modes short,full \
  --out out/etp/
```

Структура выхлопа:
```
out/etp/<lot_id_safe>/
  lot_appendix.md
  <platform>/
    long_description.json
    description.short.txt
    description.full.txt
```

`<lot_id_safe>` = `lot_id` с заменой `:` и `/` на `_` (для FS-совместимости).

Опции:
- `--target-cad` — переопределить КН-анкер для identity (по умолчанию `lots.primary_cad_number`).
- `--quiet` — не печатать пути созданных файлов.

## Тесты (9/9 pass)
- File tree: 3 платформы × 2 mode + JSON + appendix = 10 файлов.
- Description.txt матчит goldens из Stage 2.
- Appendix.md содержит lot_id / name / КН-членов / procedure_type.
- JSON содержит `meta.platform` соответствующий каталогу.
- Селективный экспорт (1 платформа, 1 mode).
- Errors: unknown platform/mode → SystemExit; missing db → rc=2; unknown lot → LookupError.

Полный прогон всех ЭТП-тестов: **54/54 pass** (schema 12 + context 15 + render 18 + cli 9).

## Что закрыто Stage'ами 1-3
- `build_lot_context` (читает БД → ctx)
- `render_lot_description` (ctx → текст через Jinja, 3 платформы × 2 mode)
- `build_lot_appendix` (Markdown-приложение)
- CLI обёртка с error handling
- 8 golden-файлов для регрессии
- 54 теста

## Что осталось (для будущих PR)
- `address_parser.py` — компонентный парсер `objects.address` → `location.region/.../room` (§10 SPEC gap).
- `encumbrance_mapper.py` — текст влияния обременения (`legal.encumbrances[].influence`).
- ETL ОСВ/XLSX → `object_etp_profile` (массовый импорт правок экономиста).
- EXIF UserComment → `object_etp_profile` (автозаполнение из фото).
- NSPD enrichment для `building.building_type/year_built/legal.use_type_permitted`.
- PDF-конверсия Markdown-приложения через существующий MD→DOCX→PDF пайплайн.
- Рефакторинг Jinja-шаблона (грамматические шероховатости — отдельный PR с обновлением `docs/etp_export/05_*.md` и регенерацией goldens).
- viewer Phase 1b: редактор `admin/etp-profile/<cad_number>` (когда в БД появятся production-данные).

## Связи
- PR #41, #48, #50, #52, #53, #54, #55, #56, #57, #58 (все merged).
- Этот PR замыкает базовый цикл «лот → артефакты для оператора ЭТП».
