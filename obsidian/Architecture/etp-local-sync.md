# Локальная синхронизация ЭТП-пакета (Win10 / E:\Code\ekcelo\code)

> Как держать локальную рабочую копию в актуальном и **полном** состоянии.
> Записано после инцидента 2026-05-29: `ModuleNotFoundError: No module
> named 'parser.exporters.etp.auto_export'`.

## Что произошло

Локальная копия набиралась из **выборочных ZIP** (только изменённые в каждом
PR файлы). Модули `auto_export.py` и `appendix.py` мёржились в репо на GitHub
(PR #59 / #69 / #73), но в выборочные ZIP последующих PR не попадали — на
диске их не было. При запуске `python -m parser.exporters.etp.etl_pipeline_cli`
импорт `from parser.exporters.etp.auto_export import …` падал.

**Это НЕ проблема упаковки** (`pyproject.toml`). Запуск
`python -m parser.exporters.etp.<module>` из корня репо работает через
namespace-пакет без `pip install`. Ошибка была буквально про отсутствующий
файл на диске.

## Канонический способ синхронизации — `git pull`

После мёржа любого PR на GitHub:

```powershell
cd E:\Code\ekcelo\code
git fetch origin
git checkout main
git pull --ff-only origin main
```

`git pull` приносит **полное** состояние main, без риска пропустить
транзитивные зависимости между PR. Это надёжнее, чем распаковывать
выборочные ZIP.

## Когда всё-таки ZIP

Если push/pull недоступны (например, прокси 403 в части окружений) —
используйте **полный пакетный ZIP** `parser/exporters/etp/` целиком
(все ~20 модулей + `templates/`), а не diff-набор. Тогда пакет
самодостаточен.

## Проверка целостности пакета

```powershell
cd E:\Code\ekcelo\code
python -c "import parser.exporters.etp as e; import parser.exporters.etp.auto_export, parser.exporters.etp.appendix, parser.exporters.etp.md_convert, parser.exporters.etp.etl_pipeline_cli; print('OK: все модули на месте')"
```

Если печатает `OK` — пакет полный. Если `ModuleNotFoundError` — не хватает
файла, сделайте `git pull` или возьмите полный пакетный ZIP.

## Полный список модулей `parser/exporters/etp/` (на 2026-05-29)

| Модуль | Назначение | PR |
|---|---|---|
| `__init__.py` | Реэкспорты | #55+ |
| `build_lot_context.py` | БД → ctx dict | #55 |
| `text_render.py` | ctx → текст (Jinja) | #57 |
| `templates/torgi_long_description.j2` | Шаблон описания | #57 |
| `appendix.py` | Markdown-приложение лота | #59 |
| `cli.py` | CLI экспорта (+`--appendix-format`) | #59, #79 |
| `address_parser.py` | Компонентный адрес | #61 |
| `encumbrance_mapper.py` | Текст влияния обременения | #61 |
| `etl_osv.py` / `etl_osv_cli.py` | Импорт YAML survey-листа | #62 |
| `export_json.py` / `export_json_cli.py` | Экспорт БД → JSON для viewer | #64 |
| `nspd_enricher.py` / `nspd_enrich_cli.py` | NSPD gap-fill | #65 |
| `etl_exif.py` / `etl_exif_cli.py` | EXIF UserComment → extras | #67, #78 |
| `auto_export.py` | Общий `--export`/`--commit` hook | #69, #73 |
| `init_db_cli.py` | Bootstrap dev-БД | #72 |
| `morphology.py` | pymorphy3 падежи | #74 |
| `md_convert.py` | MD → PDF/DOCX | #79 |
| `etl_pipeline_cli.py` | Bulk-применение inbox YAML | #80 |
| `templates/osv_template.yaml` | Пример survey-листа | #62+ |

## Связи
- `obsidian/Architecture/dependencies.md` — Python-зависимости.
- `obsidian/Architecture/etp-exporter.md` — обзор пайплайна.
