# Золотой путь: от выписок до KMZ (и дальше)

> Полная последовательность шагов экономиста / оператора от ввода исходных документов до получения карточек ЭТП, KMZ-файла и (опционально) меморандума. Поддерживает Win10 и Linux.

## Когда использовать

Когда нужно: сделать карточку лота под публикацию на ЭТП, собрать KMZ для viewer'а и отчёта оценщика, опционально — собрать меморандум через LLM-оркестратор.

## Опорный лот в примерах

`lot:pirushin:001` — лот из baseline-шаблона. Поменяйте на свой.

## Подготовка (один раз на проект)

```powershell
# Win10 PowerShell
cd E:\Code\ekcelo
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"

# Linux
cd ~/ekcelo
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**ANTHROPIC_API_KEY НЕ нужен для шагов 0-10 и 12.** Нужен только для шага 11 (меморандум через LLM).

## Шаг 0 — Структура рабочей папки

```
<рабочая_папка_лота>/
├── Выписки_PDF/             # ЕГРН PDF/XML (PDF свид. о ГРП, XML кадастровые выписки)
├── Фотографии/              # JPG фото объекта (опционально с EXIF GPS)
├── ОСВ/                     # 1С ОСВ счёт 01.01 / 01.К (опц.)
├── Сторонние_документы/     # ГПЗУ, Минкульт, техпаспорта (опц.)
├── _data/                   # создаётся скриптами автоматически
│   └── documents.json       # overlay-эффекты, заполняется парсером
└── (после шагов ниже)
    ├── structure_*.json
    ├── enriched.json
    ├── graph.html
    └── <проект>.kmz
```

## Шаг 1 — Парсинг ЕГРН в SQLite

```powershell
# Создать новую БД
egrn-parser migrate --db .\output\ekcelo.sqlite
egrn-parser dict-load --db .\output\ekcelo.sqlite

# Парсинг
egrn-parser parse --input .\Выписки_PDF\ --db .\output\ekcelo.sqlite
```

Результат: таблицы `objects`, `rights`, `entity_registry`, `extracts`, `object_restrictions` заполнены. Опц. экспорт XLSX:

```powershell
egrn-parser export --db .\output\ekcelo.sqlite --xlsx report.xlsx
```

## Шаг 2 — Применение миграции ЭТП-слоя (один раз)

```powershell
python -m parser.exporters.etp.init_db_cli --db .\output\ekcelo.sqlite
```

Создаёт таблицы `object_etp_profile`, `lots`, `lot_items` (миграция `0001_etp_profile.sql`).

Опц. `--with-template` подгружает baseline-шаблон с 3 объектами для немедленного smoke.

## Шаг 3 — Загрузка OSV survey-листа экономиста

Положите YAML в `parser/inbox/etp/<YYYY-MM-DD>-<slug>.yml` (формат — `parser/exporters/etp/templates/osv_template.yaml`).

```powershell
# Поштучно
python -m parser.exporters.etp.etl_osv_cli `
    --yaml .\parser\inbox\etp\2026-06-01-pirushin-v1.yml `
    --db .\output\ekcelo.sqlite `
    --export --commit

# Bulk (вся пачка inbox)
python -m parser.exporters.etp.etl_pipeline_cli `
    --db .\output\ekcelo.sqlite `
    --move-applied --export --commit
```

Результат: `object_etp_profile` обогащено отделкой, инженеркой, рисками, преимуществами. Успешные YAML переехали в `_applied/<YYYY-MM-DD>/`.

## Шаг 4 — NSPD-обогащение (опц.)

```powershell
python -m parser.exporters.etp.nspd_enrich_cli `
    --db .\output\ekcelo.sqlite `
    --nspd-dir .\nspd_cache\
```

Gap-fill `building_type`, `year_built`, `use_type_permitted` (НЕ перезатирает существующие значения от OSV/manual).

## Шаг 5 — EXIF-обогащение из фото (опц.)

```powershell
python -m parser.exporters.etp.etl_exif_cli `
    --db .\output\ekcelo.sqlite `
    --photos .\Фотографии\
```

Сводит JPG с EXIF UserComment v1.1 → `extras.advantages[]` («Комплексная фотофиксация: Фасад, Кровля, …»).

## Шаг 6 — Checko-обогащение (opt-in)

Только если у вас есть `innogrn.db` от стороннего `parser_checko_ru` (см. [[etp-checko]]).

```powershell
python -m parser.exporters.etp.etl_checko `
    --db .\output\ekcelo.sqlite `
    --innogrn-db D:\checko_cache\innogrn.db `
    --lot lot:pirushin:001
```

Добавляет `legal_extra.owner_checko = {is_active, status_text, special_regime, main_okved, ust_kap, schr, region, reg_date, termination_date}`.

## Шаг 7 — Генерация карточек ЭТП

```powershell
python -m parser.exporters.etp.cli `
    --lot lot:pirushin:001 `
    --db .\output\ekcelo.sqlite `
    --platforms torgi.gov.ru,sberbank-ast.ru,roseltorg.ru `
    --modes short,full `
    --out .\out\etp\
```

Результат в `out/etp/lot_pirushin_001/`:

```
├── lot_appendix.md           # Markdown-приложение
├── torgi.gov.ru/
│   ├── description.short.txt  # 3 абзаца для карточки ЭТП
│   ├── description.full.txt   # 6 абзацев для PDF/виджета
│   └── long_description.json  # JSON ядро (для отладки)
├── sberbank-ast.ru/           # аналогично
└── roseltorg.ru/              # аналогично
```

Опц. PDF-приложение (требует LibreOffice или pandoc):

```powershell
python -m parser.exporters.etp.cli ... --appendix-format pdf
```

## Шаг 8 — Сборка структуры проекта (KMZ-вход)

```powershell
python parser\scripts\pirushin_sosn_rocha_07_init_project_v3.py
```

Интерактивно создаёт идемпотентную структуру папок (fuzzy-match `Memorandum`↔`memorandum`, layout-swap ЙЦУКЕН↔QWERTY).

```powershell
python parser\scripts\pirushin_sosn_rocha_052_make_structure_v2_2.py
```

Сводит ЕГРН + NSPD + фото в `structure_*.json` для KMZ.

## Шаг 9 — Сборка KMZ

```powershell
python parser\scripts\pirushin_sosn_rocha_08_build_kmz_v2_2.py
```

Опц. с `_data/documents.json` (overlay-эффекты по spec 2.12.0) — KMZ получит `<extract_date>` из max(doc_date) выписочных kind'ов.

Результат: `<проект>.kmz` (ZIP с `doc.kml`, `images/`, `docs/`, `graph.html`).

## Шаг 10 — Открыть KMZ в viewer

Локально:

```powershell
# Win10
cd E:\Code\ekcelo
python -m http.server 8001
# открыть http://localhost:8001/viewer/index.html в Chrome/Edge
# в UI «Загрузить KMZ» → выбрать <проект>.kmz
```

Или опубликовать viewer/ на GitHub Pages и открыть как hosted.

## Шаг 11 — Меморандум через LLM (опц.)

**Требует `ANTHROPIC_API_KEY`** (или Mock-режим для тестов).

Подготовьте `Memorandum/_data/enrich_<lot_id>.json` через Этап 1 (intake) — copy-paste промпта из `obsidian/Prompts/llm_memorandum_pipeline/01_intake_and_pipeline.md` в claude.ai и сохраните результат.

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# CLI (один лот):
python -m lot_orchestrator.cli `
    --workspace E:\Объекты\pirushin `
    --lot pirushin_001

# или Web (интерактивно):
# (требует pip install -e ".[orchestrator-web]" — будет после merge PR #92)
ekcelo-orchestrate-web --reload
# → http://localhost:8000/
```

**Без ключа** для smoke-теста:

```powershell
python -m lot_orchestrator.cli `
    --workspace .\test_project `
    --lot test_001 `
    --mock-llm "Финальный отчёт.<!-- MARP_START --># Slide"
```

Результат: `Memorandum/{final_report.md, investment_slides.md, market_template.md, _data/_run_log.jsonl}`.

## Шаг 12 — Smoke-проверка всего пайплайна

```powershell
python -m parser.exporters.etp.smoke_cli
```

33 проверки: import всех модулей, init_db, генерация карточек, проверка артефактов, JSON payload. rc=0 если всё ок.

## Опорные документы

- **Контракт KMZ:** `docs/CONTRACT_KMZ.md` + `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md` (wire-формат).
- **Спецификация ЭТП-экспортёра:** `docs/etp_export/SPEC_etp_export.md`.
- **Архитектура внутри:** `obsidian/Architecture/etp-exporter.md`, `lot-orchestrator.md`, `system-state-2026-05-30.md`.
- **ADR:** `obsidian/Decisions/ADR-001..003`.

## Troubleshooting

### `egrn-parser: command not found`

Установите парсер: `pip install -e .\parser\` (отдельный pyproject) или `pip install -e ".[egrn-full]"` после merge PR #92.

### `error: db not found`

Создайте через `init_db_cli --with-template`.

### Все шаги 7-9 падают «нет данных для cad_number X»

Сначала шаги 1-3 (parse + init_db + osv).

### KMZ открывается в Google Earth, но не в viewer

Проверьте `kml_schema_version` в `doc.kml` (должна быть 2.0+). Используйте `parser/scripts/pirushin_sosn_rocha_08_build_kmz_v2_2.py`, не v1.

### Шаг 11 валится «ANTHROPIC_API_KEY не задан»

Меморандум — единственный шаг, требующий ключа. Используйте `--mock-llm` или `--dry-run` для smoke без сети.
