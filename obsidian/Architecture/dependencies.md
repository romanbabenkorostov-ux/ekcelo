# Зависимости проекта ekcelo

> Канон-источник — `parser/pyproject.toml`. Этот документ — справочник
> по тому, зачем нужна каждая зависимость и где она используется.

## Установка

```powershell
# Windows / PowerShell
cd E:\Code\ekcelo\code
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e parser/
```

```bash
# Linux / macOS
cd /path/to/ekcelo
python3 -m venv venv
source venv/bin/activate
pip install -e parser/
```

`pip install -e parser/` устанавливает все runtime-зависимости + регистрирует пакет в editable-режиме для разработки.

## Python

| Требуется | Где задано |
|---|---|
| **Python ≥ 3.10** | `parser/pyproject.toml` `requires-python` |

Использования: PEP 604 union types (`str \| None`), `match`/`case`, walrus в комплексных тестах, `dataclasses` фишки.

## Runtime-зависимости (по разделам)

### Парсинг выписок ЕГРН

| Пакет | Версия | Зачем |
|---|---|---|
| `pdfplumber` | `>=0.11` | Парсинг PDF-выписок (`parser/egrn_parser/parsers/pdf_parser.py`). |
| `python-docx` | `>=1.1` | DOC/DOCX выписки + генерация отчётов (`parser/egrn_parser/parsers/docx_parser.py`, `parser/scripts/...09_make_reports_v1.py`). |
| `openpyxl` | `>=3.1` | XLSX-шаблоны выгрузки и ОСВ-сверки (`parser/egrn_parser/parsers/xlsx_template_parser.py`, `parser/egrn_parser/exporters/xlsx_exporter.py`). |

### ЭТП-экспортёр (`parser/exporters/etp/`)

| Пакет | Версия | Зачем |
|---|---|---|
| `jinja2` | `>=3.1` | Шаблонизатор описаний лотов ЭТП (`text_render.py`, `templates/torgi_long_description.j2`). |
| `pyyaml` | `>=6.0` | Чтение OSV survey-листов (`etl_osv.py`). |
| `piexif` | `>=1.1` | Чтение EXIF UserComment из JPG (`etl_exif.py`, согласовано с `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1). |
| `Pillow` | `>=10.0` | Открытие JPG для работы с EXIF (зависимость `piexif` де-факто). |
| `pymorphy3` | `>=2.0` | Морфология русского (`morphology.py`) — падежные фильтры в Jinja. |
| `pymorphy3-dicts-ru` | `>=2.4` | Словарь русского для `pymorphy3` (отдельный пакет, иначе AttributeError при первом анализе). |

### Optional (API)

`parser/pyproject.toml` `[project.optional-dependencies]`:

| Группа | Пакеты | Когда |
|---|---|---|
| `api` | `fastapi>=0.111`, `uvicorn[standard]>=0.29` | Если поднимаем REST-обёртку парсера (опционально, не используется на данный момент). |

Установка: `pip install -e "parser/[api]"`.

## Стандартная библиотека

Используется без сторонних wrapper'ов:

- `sqlite3` — основная БД (`parser/egrn_parser/db/`, `parser/exporters/etp/`).
- `pathlib` — пути.
- `argparse` — все CLI.
- `subprocess` — git-операции в `auto_export.py`.
- `dataclasses` — `OsvDocument`, `ApplyReport`, `EnrichReport` и др.
- `json` — все wire-форматы.
- `re` — `address_parser.py`, `encumbrance_mapper.py`, `morphology.py`.
- `functools.lru_cache` — кэш морфо-анализа.

## Dev-зависимости (тесты)

| Пакет | Установка | Зачем |
|---|---|---|
| `pytest` | `pip install pytest` | Test runner (≥9.0 на момент написания). |
| `pytest-asyncio` | автоустанавливается с anyio | Только для NSPD-парсера v8 (Playwright async). Не нужен для ЭТП-тестов. |

ЭТП-тестам внешних dev-зависимостей не требуется — реальные SQLite, реальные JPG (через piexif+Pillow), реальные git-репо (subprocess) в `tmp_path`.

## Зависимости viewer-side (HTML/JS)

`viewer/` — статический сайт под GitHub Pages, без npm-сборки. Внешние JS:

| Файл | Использование |
|---|---|
| `viewer/vendor/vis-network-9.1.9.min.js` | Граф связей (S5+). Лицензии: `viewer/vendor/vis-network-LICENSE-*.txt`. |

Прочие зависимости (`leaflet`, `openlayers`, …) — через CDN (см. inline-теги в `viewer/index.html` и `viewer/admin-etp-profile.html`).

## Обновление этого документа

Когда добавляется новый пакет в `parser/pyproject.toml`:
1. Добавить строку в соответствующий раздел выше.
2. Указать минимальную версию и причину.
3. Указать ключевой модуль / скрипт-потребитель.
4. Если зависимость опциональная — поместить в `[project.optional-dependencies]` и в раздел «Optional».

История изменений зависимостей идёт через `obsidian/Changelog/`.
