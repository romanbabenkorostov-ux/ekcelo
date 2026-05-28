# 2026-05-28 — Auto-export hook для ETL CLI

## Итог
Все три ETL CLI (`etl_osv_cli`, `nspd_enrich_cli`, `etl_exif_cli`) получили общий набор флагов `--export` / `--export-out` / `--export-project`. После успешного commit'а в БД CLI автоматически перегенерирует `parser/exports/etp/object_etp_profile.json` — viewer видит обновление при следующем заходе. Один шаг вместо двух.

## Артефакты
- `parser/exporters/etp/auto_export.py` — общий хелпер (`add_export_args` + `run_export_if_requested`).
- `parser/exporters/etp/etl_osv_cli.py` — добавлен импорт + вызов хелпера.
- `parser/exporters/etp/nspd_enrich_cli.py` — то же.
- `parser/exporters/etp/etl_exif_cli.py` — то же.
- `parser/tests/test_auto_export_hook.py` — 8 тестов на все 3 CLI.
- `obsidian/Architecture/etp-exporter.md` — обновлены секции «Этапы», «Использование», «Пайплайн».

## Поведение
- **`--export`** не указан → CLI работает как раньше (backward-compat).
- **`--export`** + commit → создаётся `<out>/object_etp_profile.json` после применения ETL. Печатается `[exported] <path>`.
- **`--export`** + `--dry-run` → экспорт пропускается, печатается `[skip-export]`.
- **`--export-out <dir>`** — переопределить корневой каталог (default: `parser/exports/etp/`).
- **`--export-project <slug>`** — фильтр по `lot:<slug>:*` (default: всё).

## Тесты (8/8 pass)
- 4 osv_cli (writes with export, no export → no file, dry-run skips, project filter).
- 2 nspd_cli (writes, dry-run skips).
- 2 exif_cli (writes, no-photos exits до подключения к БД → нет файла).

**Полный прогон ЭТП-набора: 124/124 pass.**

## Новый workflow (одна команда)

Вместо двух последовательных вызовов:
```bash
python -m parser.exporters.etp.etl_osv_cli --yaml ... --db ekcelo.sqlite
python -m parser.exporters.etp.export_json_cli --db ekcelo.sqlite
```

Теперь один:
```bash
python -m parser.exporters.etp.etl_osv_cli --yaml ... --db ekcelo.sqlite --export
```

Применимо к любому ETL CLI. После выполнения остаётся только закоммитить
свежий `parser/exports/etp/object_etp_profile.json`.

## Что осталось
- CI-hook для auto-commit JSON-экспорта (отдельная задача).
- Jinja-grammar refactor.

## Связи
- PR #62 (Stage 4), #64 (Stage 4b), #65 (Stage 5), #67 (Stage 6) — merged.
- Workflow: `parser/exports/etp/EXPORT_NOTES.md` обновится в следующем PR (или вместе с CI-hook).
