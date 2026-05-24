# README: `09_make_reports_v1.py` — console-CLI отчёты по проекту

**Реализация:** `parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py`
(PR-δ/ε/ζ из `dev/SPEC_TEMPORAL_REPORTS.md` §14).

## Быстрый старт

```bash
# Создать mini-fixture с тремя расширениями (PR-β)
python3 parser/scripts/dev/make_mini_fixture.py /tmp/proj \
    --with-pledge-chain --with-osv --with-overlay

# Запустить интерактивное меню
python3 parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py /tmp/proj --as-of 2026-04-15
```

В меню:
- `[1]` ОСВ-сверка (счета 01.01 / 01.03 / 01.К / 08).
- `[2]` Залоговая таблица (4 секции).
- `[3]` Фотоотчёт по проекту (DOCX через `06_photo_v3` логику).
- `[4]` Формат output (`md` / `docx` / `both`) — toggle на сессию.
- `[Q]` Выход.

Файлы сохраняются в `<project>/reports/report_<kind>_<YYYYMMDD_HHMMSS>.{md,docx}`.

## Manual smoke-test для DOCX (Windows 10)

CI прогоняет только python-docx ветку (Linux). Полную DOCX-конвертацию с
обновлением SEQ/TOC через MS Word COM нужно тестировать вручную:

### Prerequisites

```cmd
pip install python-docx pillow piexif pywin32
```

### Smoke-test

```cmd
REM 1. Создать mini-fixture
python parser\scripts\dev\make_mini_fixture.py D:\test\proj --with-overlay --with-pledge-chain --with-osv

REM 2. Запустить отчёты
python parser\scripts\pirushin_sosn_rocha_09_make_reports_v1.py D:\test\proj --as-of 2026-04-15
REM В меню: 4 → docx → 1 → 2 → Q

REM 3. Проверить что DOCX открывается в Word без ошибок
start D:\test\proj\reports\report_pledges_<ts>.docx
start D:\test\proj\reports\report_osv_recon_<ts>.docx
```

**Ожидаемое поведение:**
- DOCX открывается в Word без preview-warning'ов.
- SEQ-поля «Таблица N» отрисованы как «Таблица 1», «Таблица 2» (через
  COM-обновление при сохранении из 09; F9 нажимать не нужно).
- Если pywin32 не установлен или Word недоступен — DOCX всё равно
  валиден, но SEQ-поля показывают `#` до первого нажатия F9 (Word
  обновит при открытии благодаря `<w:dirty>true</w:dirty>`).

### Если что-то не работает

| Симптом | Причина | Решение |
|---|---|---|
| `RuntimeError: python-docx не установлен` | нет `python-docx` | `pip install python-docx` |
| `⚠ DOCX-рендерер недоступен` в stdout | то же | то же |
| DOCX открывается, но SEQ-поля = `#` | COM-обновление не сработало | Откройте Word, нажмите Ctrl+A → F9 (или установите pywin32) |
| Кириллица в имени файла → Word не открывает | редкий случай Windows | переименуйте файл в латиницу |

## Архитектура

```
09_make_reports_v1
├── load_structure (parser/egrn_parser/temporal.py не нужен здесь)
├── load_documents      → egrn_parser/documents_schema.py
├── load_osv            → читает _data/osv_cache.json
├── load_enriched
├── build_pledge_report → egrn_parser/temporal.py (resolve_state,
│                          founder_chain_has_pledge, collect_pledge_holders)
├── build_osv_recon_report
├── build_photo_report  → 06_photo_report_to_docx_v3.py через importlib
└── ReportBuilder Protocol → utils/report_builder.py
    ├── MarkdownBuilder (git-friendly)
    └── DocxNativeBuilder (python-docx + SEQ + TOC + COM-обновление)
```

## Что НЕ работает в v1 (out-of-scope, см. spec §13)

- **State-tags автоматическое извлечение** из ОСВ-комментариев /
  ЕГРН-описаний. v1 только ручное добавление через `documents.json`
  effects (PR-η `collect_tags_from_documents`).
- **Multi-source conflict resolution** — две выписки той же даты с
  разными restrictions. v1 fails-fast.
- **Bitemporal** (effective_at vs recorded_at).
- **Phase 2 multi-extract timeline-UI** — viewer-side инициатива
  CONTRACT_TIMELINE.md в S7+.
- **04_nspd_graph styling для документ-узлов** — S6+ wishlist (черные
  точки с № документа и ссылкой на JPG).
- **REST endpoint** для documents.json — viewer fully client-side,
  пользуется `_data/documents.json` из KMZ-архива.

## Контракт KMZ — стабилен

Реализация v1 — parser-internal. Wire-формат KMZ остаётся 2.12.0
(`<Data extract_date>` + опц. `_data/documents.json` sidecar в архиве).
Никаких новых wire-полей, никаких изменений SemVer.
