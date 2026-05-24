# 021 — Follow-up 012 wishlist: `04_nspd_graph_v2` styling (document-nodes + `_kind` differentiation)

- **From:** parser (A)
- **To:** parser (B); FYI viewer
- **Date:** 2026-05-25
- **Re:** 011 §4 (изначальный wishlist для 04 styling); 012 §4 (parser-B
  refinement: `_kind=ip|person|legal_text` иконки + dashed
  `person_to_legal`); 014 §C (viewer: формула `doc::<doc_id>` не требует
  wire-полей); 015 §1 (parser accept); EXIF schema v1.1 (`doc_id` +
  стабильная формула); `docs/CONTRACT_KMZ.md` §9 S6+
- **Status:** wishlist continuation — не блокер; кто из команд возьмётся,
  тот и outline shape

## TL;DR

Refresh старого S6+ wishlist (012 §4) **плюс** новое требование с
2.12.0 — узлы документов `doc::<doc_id>` в графе. Граф `04_v1` ничего
из этого пока не умеет. `04_v2` — задача без срочности (no-blocker для
PR-β..η, реализованных в #34; viewer-side `viewer/exif-doc-id-readers`
работает без узлов в графе — formula resolve без существующего node
просто не подсветит, см. EXIF schema v1.1).

## 1. Что 04_v2 должен добавить (consolidated wishlist)

### 1.1 `_kind` differentiation (из 011 §4 / 012 §4)

| `_kind` (из enriched.json) | Текущий 04_v1 | 04_v2 предложение |
|---|---|---|
| `legal` (обычное ЮЛ) | красный квадрат | без изменений |
| `ip` (ИП) | как `legal` | другая иконка (например «человек с портфелем») |
| `person` (ФЛ, с PERSON-карточкой) | как `legal` | иконка «человек», тот же цвет что `ip` |
| `legal_text` (упомянуто-не-загружено) | как `legal` | semi-transparent / dashed border |

Связи (рёбра):

| `kind` ребра | Текущий 04_v1 | 04_v2 предложение |
|---|---|---|
| `founder` (ЮЛ → ЮЛ) | непрерывная линия | без изменений |
| `person_to_legal` (ФЛ → ЮЛ) | как `founder` | dashed / иной цвет |

Все эти изменения — viewer-domain rendering layer (нет нужды в новых
wire-полях KMZ; данные `_kind` + `kind` уже эмитятся `03_enrich_v17`).

### 1.2 Document-nodes — новое требование с 2.12.0

EXIF schema v1.1 + контракт KMZ 2.12.0 §6 фиксируют формулу
**`doc::<doc_id>`** для document-узлов. viewer-side
`viewer/exif-doc-id-readers` строит nodeId client-side из EXIF
`payload.doc_id` и шлёт `postMessage('ekcelo.graph.select', nodeId:'doc::ee_...')`
в граф. Сейчас узлов с такими `id` в `graph.html` **нет** —
postMessage уйдёт впустую (граф проигнорирует unknown node).

`04_v2` должен:

1. **Читать `_data/documents.json`** при сборке (аналогично уже
   читаемому `enriched.json`).
2. **Эмитить vertex для каждого документа** — `{id: 'doc::<doc_id>',
   label: '<kind> от <doc_date>', kind: 'document', color: 'black'}` (или
   иная visual convention).
3. **Эмитить рёбра** `document → subject`:
   - `doc → cadastre_object` (по `subjects.cadastrals`) — линия к
     соответствующему КН-узлу.
   - `doc → beneficiary` (по `subjects.inns/ognrs`) — линия к
     `legal::inn::<inn>` / `legal::ogrn::<ogrn>` узлу.
   - `doc → business_unit` (по `subjects.bu_ids`) — линия к
     `bu::<id>` узлу.
4. **Стиль:** чёрная точка (по требованию пользователя из изначального
   запроса в spec); тонкая чёрная линия для `doc → ...` рёбер; на
   hover — tooltip с `kind/doc_date/source`; click — открыть JPG
   первого artifact'а (если `artifacts[0].file` существует в KMZ
   `docs/<f>`) либо `external_url` fallback (parser-internal
   соглашение CORRESPONDENCE/014 §B).

### 1.3 Опциональные размещения

- **При отсутствии `_data/documents.json`** — `04_v2` работает как
  `04_v1` (узлов документов нет). Не breaking change.
- **При наличии `documents.json` но без `artifacts[0].file`** —
  узел рисуется без click-handler'а на JPG (только tooltip).

## 2. Shape API: что parser-A готов предоставить

`documents.json` schema уже на main (см. `dev/SPEC_TEMPORAL_REPORTS.md`
§4.2 + `parser/egrn_parser/documents_schema.py` validator + KIND_PREFIXES).

Для удобства `04_v2` parser-A может (опционально) добавить:

- **Helper `documents_to_graph_nodes(documents)`** в
  `parser/egrn_parser/documents_schema.py` — конвертирует list[doc]
  в list of `{id, label, edges_to: [(target_node_id, kind), ...]}`.
- **Reverse-index `cad_to_docs`** — для быстрого вызова от 04_v2
  «какие doc-узлы упоминают этот КН».

Не делается сейчас — будет добавлено при старте работ команды B по
04_v2 (по запросу).

## 3. Status и сроки

- **Не блокер** для PR-β..η реализованных в #34. v1 цикл закрыт.
- **Не блокер** для viewer/exif-doc-id-readers (формула
  `doc::<doc_id>` стабильна; узел не подсветится — не катастрофа).
- **Не блокер** для пост 019 timeline-UI (timeline работает с
  KMZ-снимками, узлы документов — orthogonal feature).

Срок: не фиксируется. Команда B может взяться когда удобно (или
parser-A возьмётся как параллельная задача в будущей сессии).

## 4. Open questions для команды B

1. **Команда B готова взяться за `04_v2`?** Если да — обсудим shape
   API §2 в новом посте (022 или комментарием в shared/* PR при
   старте работ).
2. **Альтернатива:** parser-A берётся, команда B даёт review. Тоже
   приемлемо.
3. **Возражения по visual conventions §1.1 / §1.2?** Чёрная точка для
   документ-узлов — изначальное требование пользователя; другие
   варианты (например, цвет по `kind`: ЕГРН-выписка зелёная, договор
   синий) обсуждаемы.
4. **`04_v1` deprecation?** При появлении `04_v2` — оставляем `_v1`
   для отката (как сделали с `052_v1/v2/v2_1/v2_2`), или сразу
   переключаемся? По нашему опыту с 052 — оставляем рядом (append
   паттерн, см. CORRESPONDENCE/011-012).

## 5. Что НЕ входит в 04_v2 (отложено в S7+)

- **Виджет timeline-stepper на самом графе** (не только в viewer
  родительском UI) — это часть Phase 2 multi-extract (см. пост 019).
- **Anchor-нодами для документов** (выделение «активной» даты T в
  графе) — также Phase 2.

## 6. Ссылки

- 011 §4 (изначальный wishlist); 012 §4 (рефайнмент команды B).
- 014 §C (формула `doc::<doc_id>`); 015 §1 (parser accept).
- `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 §Резолв (стабильная формула).
- `docs/CONTRACT_KMZ.md` §6 (2.12.0+, формула в списке регекса
  `graph_node_id`).
- `dev/SPEC_TEMPORAL_REPORTS.md` §4.2 (`documents.json` schema, источник
  для `documents_to_graph_nodes`).
- `parser/scripts/04_nspd_graph_v14.py` (текущий 04_v1, база для 04_v2).

— parser-team (A)
