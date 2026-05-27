# 2026-05-27 — Step 2: Surveycontract infrastructure

## Контекст

Договорное направление Ekcelo (сюрвей/оценка) получает базовую
инфраструктуру: идемпотентный init папки `Surveycontract/`, парсер
реквизитов сторон, валидатор УПД-XML, assembler сборок договоров.

Параллельно viewer-team разрабатывает скрипты генерации компонентов
(10/11/12) в PR #45. Step 2 их **не трогает** — assembler читает их
MD-output как есть.

## Что сделано

### 2.1 — `parser/utils/folder_match.py` + `07_init_project_v3.py`

- `parser/utils/folder_match.py` — `normalize_name`, `name_similarity`
  (SequenceMatcher + анаграмма + layout-swap ЙЦУКЕН↔QWERTY), `best_match`.
- `parser/scripts/pirushin_sosn_rocha_07_init_project_v3.py` —
  узкоспециализированный init папки `Surveycontract/` (7 подпапок +
  README в каждой). Идемпотентный walk-mode, fuzzy-match существующих
  папок (опечатки/регистр/разделители). НЕ дублирует v2 (GOLDEN_PATH-
  болванка проекта объекта); запускается отдельно.

### 2.2 — `parser/rekvizity/` (новый пакет)

```
parser/rekvizity/
  canonical.py        — схема, приоритеты источников, validate()
  merge.py            — идемпотентный merge с историей _sources[]
  store.py            — глобальный (~/.ekcelo/rekvizity/<ИНН>/) +
                        локальный (<project>/Surveycontract/rekvizity/) snapshots
  cli.py              — ingest / show / list
  parsers/
    doc_parser.py     — olefile + UTF-16LE для .doc; python-docx для .docx
    bank_vtb.py       — парсер выписки реквизитов с сайта ВТБ
    __init__.py       — dispatch по имени файла
```

ВТБ-фикстур (`parser/tests/fixtures/rekvizity/vtb_nekso_2026.doc`)
извлекает все 4 банковских поля (name, bic, ks, rs) + ИНН/КПП/ОГРН +
ФИО подписанта + email. Golden JSON приложен.

Стратегия `.doc`: чистый pure-Python через `olefile` (без soffice /
antiword). Подтверждено на реальном Word 97-2003 файле в sandbox.

### 2.3 — `parser/upd/` (новый пакет)

```
parser/upd/
  validator.py        — lxml + XSD; берёт самый свежий ON_NSCHFDOPPR_*.xsd
                        из parser/schema/xsd/upd/
  cli.py              — validate <xml> [--xsd <path>]
parser/schema/xsd/upd/
  NOTES.md            — описание + инструкция обновления редакции
                        (XSD-файл ФНС приложит пользователь отдельно;
                        имя NOTES вместо README — корневой .gitignore
                        игнорирует все README.md)
```

### 2.4 — `parser/scripts/pirushin_sosn_rocha_13_assemble_contract_v1.py`

Assembler v1: сканирует `Surveycontract/{tz1-content,body,tz2-calculation}/*.md`,
интерактивно компонует выбранные компоненты, сохраняет sborka-конфиг
в `sborki/`, финальную сборку (md/json/docx) — в `gotovo/`.

Поддерживает:
- **Версионирование** (`_parent_sborka`) — допсоглашения.
- **Subcontract chains** (`_parent_contract`) — субподряд.
- **Non-interactive** режим (`--auto-latest`) для CI.

Распознаёт `predmet_kind` (gk39/fz135) из тела MD-файлов (метка
«ГК-39» / «135-ФЗ»).

### Тесты (новые: 28; все проходят)

- `test_folder_match.py` — 8 тестов
- `test_init_project_v3.py` — 3 теста
- `test_rekvizity_bank_vtb.py` — 9 тестов (включая golden-check + idempotent + merge priority)
- `test_upd_validator.py` — 3 теста
- `test_assembler.py` — 5 тестов

Pre-existing `test_ons_pdf_parsing` падает из-за отсутствия `pdfplumber`
в sandbox — НЕ связано со Step 2.

## Файлы под нож

**Новые:**

```
parser/__init__.py
parser/utils/__init__.py
parser/utils/folder_match.py
parser/scripts/pirushin_sosn_rocha_07_init_project_v3.py
parser/scripts/pirushin_sosn_rocha_13_assemble_contract_v1.py
parser/rekvizity/__init__.py
parser/rekvizity/canonical.py
parser/rekvizity/store.py
parser/rekvizity/merge.py
parser/rekvizity/cli.py
parser/rekvizity/parsers/__init__.py
parser/rekvizity/parsers/doc_parser.py
parser/rekvizity/parsers/bank_vtb.py
parser/upd/__init__.py
parser/upd/validator.py
parser/upd/cli.py
parser/schema/xsd/upd/NOTES.md
parser/tests/test_folder_match.py
parser/tests/test_init_project_v3.py
parser/tests/test_rekvizity_bank_vtb.py
parser/tests/test_upd_validator.py
parser/tests/test_assembler.py
parser/tests/fixtures/rekvizity/vtb_nekso_2026.doc
parser/tests/fixtures/rekvizity/vtb_nekso_2026.golden.json
obsidian/Changelog/2026-05-27-step2-surveycontract-infra.md
```

**Не тронуты:**

- `parser/scripts/pirushin_sosn_rocha_07_init_project_v2.py` (GOLDEN_PATH болванка проекта объекта — обратная совместимость).
- Скрипты 10/11/12 + `_contract_predmet.py` — зона ответственности PR #45 viewer-team.

## Зависимости

Новая dependency: `olefile` (pure Python, ~30 KB). Добавить в
`parser/requirements.txt` отдельным следующим коммитом если нужно.
Для теста `test_rekvizity_bank_vtb.py` — `pytest.importorskip("olefile")`.

`lxml` — для validator'а УПД. Уже используется в проекте (или будет
установлено пользователем при необходимости валидации).

## Следующие шаги (post-Step 2)

1. CORRESPONDENCE-пост viewer-team:
   - попросить добавить JSON-sidecar в скрипты 10/11/12
   - переориентировать default `out_dir` в `Surveycontract/{tz1-content,body,tz2-calculation}/`
   - уточнить статус «Wizard 10+11+12» (зона ответственности)
2. Получить от пользователя:
   - XSD-файл ФНС `ON_NSCHFDOPPR_*.xsd` для bundling.
   - (опц.) Выписки от других банков (Сбер/Тинькофф/Альфа) для парсеров.
3. Багфикс: площадь `network_capture` в `01b_ingest_contours.py`
   (отдельная задача, вне scope Step 2).
