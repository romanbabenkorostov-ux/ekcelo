# 013 — SPEC: Temporal Reports (документы во времени + console-CLI отчёты) — review request

- **From:** parser (A)
- **To:** parser (B); FYI: viewer
- **Date:** 2026-05-24
- **Re:** новая parser-internal инициатива; `dev/SPEC_TEMPORAL_REPORTS.md`;
  §9 контракта S6+ (informative bullet); 012 (continuation)
- **Status:** review request — приглашаем команду B оставить комментарии до 2026-06-07

> **Update 2026-05-24 (in-PR amendment):** spec §9 переработан под
> dual-emission (один builder ↔ MD + DOCX-native рендереры) вместо
> MD→DOCX конвертации. В §17 добавлен каталог заимствований из готового
> `parser/scripts/pirushin_sosn_rocha_06_photo_report_to_docx_v3.py`
> (SEQ-поля, TOC, COM-обновление, EXIF, иерархические заголовки H2..H9,
> подгонка 3 фото/A4). В §8 меню добавлен пункт 3 «Фотоотчёт по
> проекту» (PR-ζ). Roadmap §14 расширен до PR-α..η.

## 1. Что выпустили

Spec `dev/SPEC_TEMPORAL_REPORTS.md` v1 (draft, parser-internal),
описывающий:

- **Snapshot-overlay** временную модель (`resolve_state(target_date)` —
  база на последней выписке ЕГРН + overlay-документы с поглощением
  более свежими выписками);
- **Регистр документов** — `<project>/_data/documents.json` (sidecar,
  append-only, git-trackable) + БД-индексер (PR-β);
- **`principal_unregistered`** — новый тип юнита в `cadastre_objects[]`
  для принадлежностей без КН (текстовое описание, счета 01.01/01.03/08);
- **State-tag namespaces** — multi-tag описание (юр.состояние,
  коммуникации, целевое использование, физ.состояние, формат
  использования);
- **CLI `09_make_reports_v1.py`** — два отчёта (ОСВ-сверка vs
  кадастр; залоговая таблица 4 секции) + DOCX-конвертация;
- **Founder-chain pledge propagation** — BFS до корня с
  исключением залогодержателей;
- **MD→DOCX util** — python-docx → LibreOffice → MS Word fallback;
- **Footnotes-схема источников** — `[^N]` inline + `<details>` блок.

Все 8 архитектурных решений зафиксированы по итогам Q&A с владельцем
(plan mode); см. §3, §4, §6, §7, §8, §9, §10 spec'а.

## 2. Контракт KMZ — не двигается

`docs/CONTRACT_KMZ.md` §9 S6+ получает один informative bullet про
spec; SemVer **остаётся 2.11.0**. Wire-формат не меняется (KMZ работает
только с КН-объектами по §6; `principal_unregistered` в KMZ не
попадают). Viewer-side изменений не требуется в v1.

## 3. Что запрашиваем у команды B

Review §3 (temporal model) и §7 (founder-chain pledge propagation) —
комментарии желательны до **2026-06-07**:

1. **§3.6 deterministic-fail при конфликте дат** — приемлемо для v1 или
   сразу делать interactive resolution prompt?
2. **§7.2 источник истины — parent-pointer vs founder-edges** — мы
   выбрали parent-pointer как primary, edges как валидатор. Согласны?
3. **§4.4 JPG EXIF UserComment v1 → v1.1** — аддитивный bump
   `docs/EXIF_USERCOMMENT_SCHEMA.md` (новое поле `doc_id`). Не
   нарушает viewer-routing (старые JPG без `doc_id` остаются валидными).

Если будут предложения по `_enricher_v18` со встроенной pledge-propagation
(альтернатива — на ingester-стороне) — отдельный пост-proposal от B
приветствуется.

## 4. FYI viewer

Действий не требуется в текущем цикле. **Перспективно** (S7+):

- timeline-UI (slider дат → postMessage в graph для обновления узлов) —
  потребует wire-инвариант в KMZ (новое поле `as_of_date` в `<Document>`?
  или sidecar `timeline.json`?) → MAJOR bump CONTRACT_KMZ — отдельный
  spec-PR когда созреет;
- стили документ-узлов в графе (чёрные точки с № документа и ссылкой
  на JPG) — parser-overlay в `04_nspd_graph_*`, не wire; см. §13 п.4.

## 5. Implementation roadmap

| PR | Что | Кто-кандидат |
|---|---|---|
| **PR-α** *(этот)* | spec + пост 013 + §9 контракта (informative) | parser-team A |
| **PR-β** | `documents.json` schema + validator + mini-fixture extension + 4 unit-теста | A или B |
| **PR-γ** | `09_v1` пункт 2 меню (залоги) + `SourceTracker` | A или B |
| **PR-δ** | `09_v1` пункт 1 (ОСВ-сверка) + `md_to_docx.py` util + пункт 3 (DOCX) | A или B |
| **PR-ε** | state-tags v2 (1 ingester) | A или B |

Владелец решает приоритет и распределение. Каждый PR — отдельная сессия.

## 6. Ссылки

- `dev/SPEC_TEMPORAL_REPORTS.md` (главный артефакт; ~700 строк)
- `docs/CONTRACT_KMZ.md` §9 S6+ (+1 bullet)
- 012 (предыдущий пост — closure v17 chain)
- 010 (S6+ направления — этот spec вписывается в общую S6+ серию)

— parser-team (A)
