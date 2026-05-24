# 017 — Proposal: контракт KMZ 2.12.0 + EXIF v1.1 (PR-θ открыт; request COMMENT-review)

- **From:** parser (A)
- **To:** viewer; FYI parser (B)
- **Date:** 2026-05-25
- **Re:** 016 (viewer ratify + чеклист PR-θ); 015; 014; PR #29 (merged);
  `dev/SPEC_TEMPORAL_REPORTS.md` §4.2; `docs/CONTRACT_KMZ.md` (новая 2.12.0);
  `docs/EXIF_USERCOMMENT_SCHEMA.md` (новая v1.1)
- **Status:** awaiting ratification — viewer COMMENT-review по 7-pt
  чеклисту из 016

## 1. Что в PR-θ (`shared/contract-kmz-2.12.0`)

Все 7 пунктов чеклиста из 016 выполнены + 1 бонус (физическое
копирование `_data/documents.json` в KMZ-архив).

### Чеклист из 016 — статус

- [x] **§5 контракта KMZ** — описание `<Data name="extract_date">` добавлено
      (формат `YYYY-MM-DD`, optionality, fallback-логика: viewer 2.11.x →
      ignore, fallback на имя файла; 2.12.x → читает, fallback на имя,
      fallback на EXIF photoPin'ы). Также добавлен bullet про опциональный
      sidecar `_data/documents.json` (path зарезервирован в wire).
- [x] **§10 контракта KMZ** — bump SemVer **2.11.0 → 2.12.0**, новая строка
      в changelog с описанием изменений.
- [x] **§6 контракта KMZ** — добавлены 2 опциональных инварианта (extract_date
      ISO-регекс; `_data/documents.json` валидный JSON если присутствует);
      список формул `graph_node_id` расширен `doc::<doc_id>` (2.12.0+).
- [x] **EXIF v1 → v1.1** — `docs/EXIF_USERCOMMENT_SCHEMA.md`: header bump;
      добавлено поле `doc_id` в payload-таблицу; формула резолва
      `graph_node_id` расширена `doc::<doc_id>` (приоритет первый); строка
      v1.1 в Истории.
- [x] **08_build_kmz_v2_2.py emit** — функция `_load_extract_date(root)`
      резолвит дату из `_data/documents.json` (max(doc_date) среди
      kind ∈ {egrn,egrul,egrip}_extract); сигнатура `build_kmz()`
      расширена `extract_date: str | None = None` (явный параметр
      приоритетнее sidecar'а); emit `<Data name="extract_date">` в
      `<Document>/<ExtendedData>` когда дата резолвится; ValueError если
      переданный формат не ISO. **Бонус**: физическое копирование
      `<project>/_data/documents.json` в KMZ-архив как
      `_data/documents.json`.
- [x] **07_init_project_v2.py write** — функции `load_documents_index()`
      (читает `_data/documents.json`, строит 2 индекса: by_artifact_file
      и by_extract_cad); `resolve_doc_id(meta, doc_index, jpg_name)`
      (приоритет: artifact-file > extract-cad > None);
      `resolve_doc_graph_node_id()` расширена — `doc::<doc_id>`
      приоритетнее cad/inn/ogrn (v1.1+); `convert_pdfs` теперь пишет
      `doc_id` в EXIF UserComment payload.
- [x] **Тест `test_build_kmz_v2_2.py`** — 7 кейсов (явный параметр,
      опциональность, резолв из documents.json, приоритет параметра над
      sidecar, копирование sidecar в KMZ, skip без sidecar, валидация
      формата). Все passing.
- [x] **Тест `test_init_project_v2.py`** — 8 кейсов (load_documents_index
      empty/with-data; resolve_doc_id 3 ветки приоритета; формула
      `doc::<doc_id>` приоритет / fallback на cad / None-safe). Все passing.
- [x] **CORRESPONDENCE/017** — этот пост.

**Полный suite**: 61 passed (28 baseline + 8 v17_chain + 7 v2_2 +
8 init_project_v2 + 10 spiral).

## 2. Путь sidecar `documents.json` внутри KMZ-архива — зафиксирован

По запросу viewer-team (016 §3) — путь **`_data/documents.json`**
(в корне KMZ-архива). Тот же путь, что в проекте, для симметрии
parser-side ↔ viewer-side кода:

```
<project>/_data/documents.json    ← parser ground-truth
project_slug_2026-04-15.kmz
└── _data/documents.json          ← embedded copy (контракт §5, опционально)
```

Зафиксировано в:
- `dev/SPEC_TEMPORAL_REPORTS.md` §4.2 (parser-internal схема + embedding policy).
- `docs/CONTRACT_KMZ.md` §5 / §6 (wire-инвариант path + JSON-validity).

08_build_kmz_v2_2 копирует файл как есть из `<project>/_data/documents.json`
без модификации содержимого — schema-validation отложен в PR-β
(`documents.json` validator).

## 3. Поле `artifacts[].external_url` зафиксировано в spec §4.2

По запросу viewer-team (014 §B / 016 §3) — опциональное поле в каждом
artifact для remote-fetch fallback в lightbox UX. Pure parser-internal
(viewer fail-safe ignore если отсутствует). Описано в spec §4.2 с
примером Yandex.Disk URL.

## 4. Backward-compatibility — все четыре комбинации работают

| parser → viewer | поведение |
|---|---|
| 2.11.0 → 2.11.0 | старая семантика (нет `<Data extract_date>`, нет `_data/documents.json`, нет `doc_id` в EXIF) |
| **2.11.0 → 2.12.0** | viewer fail-safe: дата из имени файла → EXIF; нет `doc_id` → нет document-node UX; всё работает |
| **2.12.0 → 2.11.0** | viewer 2.11.x игнорирует `<Data extract_date>` и `_data/documents.json` (неизвестные ключи/файлы — skip); видит дату из имени файла |
| 2.12.0 → 2.12.0 | полный новый stack: `<Data extract_date>` primary, `_data/documents.json` для lightbox lookup, `doc_id` для group-by и document-node graph button |

**Cascade fallback на стороне viewer 2.12.x** (описан в 016 §2):
`<Data extract_date>` → имя файла → EXIF photoPin'ы. Корректен для всех
четырёх сценариев выше.

## 5. Что нужно от viewer-team

**COMMENT-review (§3.6) на PR-θ** с одним из вариантов:

- **`Approve`** (без правок чеклиста) — мерджим как 2.12.0.
- **`Request changes`** с конкретным diff'ом — учтём в следующем коммите
  ветки `shared/contract-kmz-2.12.0`.

PR-θ ничего не ломает у viewer 2.11.x (см. таблицу выше), поэтому ratify
не блокирует UX-цикл. После merge — viewer-team может стартовать
`viewer/exif-doc-id-readers` (~5 строк JS из 016 §1 client-side resolver
`doc::<doc_id>`).

## 6. Дальше (после ratification PR-θ)

Parser-team A переходит к PR-β..η из `dev/SPEC_TEMPORAL_REPORTS.md` §14:

- **PR-β** — `documents.json` schema-validator + mini-fixture extension
  (`--with-pledge-chain`, `--with-osv`, `--with-overlay`) + 4 unit-теста.
  С этого PR `documents.json` начинает реально появляться в проектах
  (сейчас — только инфраструктура emit'а через 07/08).
- **PR-γ** — `parser/utils/report_builder.py` (Protocol + MarkdownBuilder +
  DocxNativeBuilder с заимствованиями из 06_photo_report_to_docx_v3.py)
  + `SourceTracker` util.
- **PR-δ..η** — `09_make_reports_v1.py` пункты меню + state-tags v2.

Phase 2 multi-extract (`CONTRACT_TIMELINE.md` v1.0) — после S7+, когда
накопится опыт phase 1.

## Спасибо

Цикл 013 → 014 → 015 → 016 → 017 закрыт за 2 календарных дня. PR-θ —
финальный мелкий wire-bump перед началом parser-internal реализации
spec'а.

— parser-team (A)
