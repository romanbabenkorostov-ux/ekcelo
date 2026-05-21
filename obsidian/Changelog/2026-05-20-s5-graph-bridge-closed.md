# S5: мост маркер↔узел графа — закрыт (контракт 2.11.0)

**Даты:** 2026-05-19 → 2026-05-20 (1 день)
**Контракт:** `docs/CONTRACT_KMZ.md` 2.10.2 → 2.11.0 (MINOR, аддитивно).
**PR-цепочка:** #16 (spec) → #17 (parser) → #18 (viewer) + #19 (CORRESPONDENCE/007 + helper) + текущий closure-PR (008 + §9).

## Что в итоге

**Контракт §5 (нормативно, MINOR):**
- `<ExtendedData>/graph_node_id` (string, опц.) для `cad_{zu,oks,room,str,ons,bu,eq,ben}_*` и `photoPin_*` — opaque-string = `id` узла графа.
- Protocol pre-selection: `postMessage({type:'ekcelo.graph.select', nodeId}, '*')` + `location.hash = '#node=<urlencoded>'`. Apply отложен до `network.once('stabilizationIterationsDone')`.
- `<meta name="ekcelo-graph-protocol" content="1">` в `<head>` `graph.html`.
- `kml_schema_version` `2.0 → 2.1`.

**Контракт §6:** +5 чекбоксов + регекс `^[A-Za-z0-9_:/-]{1,256}$` (defense для hash-fallback).

**Контракт §5 (информативно):** EXIF UserComment.graph_node_id в JPG-документах (parser-internal, не wire-инвариант).

## Реализация

| Файл | Что |
|---|---|
| `parser/scripts/04_nspd_graph_v14.py` | `<meta>` + IIFE-listener + `build_graph_node_index()` + sidecar `_data/graph_node_index.json` |
| `parser/scripts/07_init_project_v1.py` | `load_graph_index` + `resolve_doc_graph_node_id` (cad→inn→ogrn priority); `graph_node_id` в EXIF UserComment документов и фото |
| `parser/scripts/08_build_kmz_v2.py` | `KML_SCHEMA_VERSION=2.1`; `load_graph_index`; `graph_node_id` в 5 классах ExtendedData |
| `parser/tests/conftest.py` | extracted fixture `synthetic_root` (общая для всех parser-тестов) |
| `parser/tests/test_graph_node_id.py` | 17 тестов (включая 3 регекс-инварианта от viewer-team) |
| `parser/scripts/dev/make_mini_fixture.py` | standalone-генератор valid KMZ для smoke-теста viewer'а |
| `viewer/index.html` | DOM `#graph-overlay` (z-index 9600), `_openGraphFor`/`_closeGraphOverlay`, `_graphNodeIdOf` с client-side §6-валидатором (многопутевой fallback), кнопка 🕸 в `_renderObjectCard`+`renderMarksList`, ESC-handler. +86 строк, 5 коммитов с UI-фиксами. |

## Архитектурное решение (фикс плана)

Изначально предлагался enrich-passthrough от 03 → 08. При имплементации обнаружилось, что **08 читает только `structure.json`** (не enriched), поэтому ключи `_bu_key`/`_b_key` 03-эмиссии в 08 недоступны. Переключились на **sidecar `graph_node_index.json` от 04** — единый owner всех node-id формул, 07/08 lookup'ят по локально-известным ключам (cn, bu_name, eq_id, inn/ogrn/name). DRY-инвариант: формулы только в 04, нигде не дублируются.

## Цикл governance (показательный пример §3.5 spec-PR-first)

1. parser-team: пост 005 — proposal + 4 вопроса.
2. viewer-team: пост 006 — COMMENT-аппрув (§3.6 ≡ Approve) + 4 ответа + 1 предложение (регекс §6).
3. parser-team: акцепт регекса в той же 2.11.0 (без bump до 2.11.1, контракт ещё не закрыт).
4. Мерж A → ребейз B → мерж B (parser-домен, аппрув не требуется).
5. viewer-team: пост от них — PR-C #18 готов, ждёт A+B (как и было запланировано).
6. parser-team: пост 007 + helper `make_mini_fixture.py` (готовый KMZ для smoke-теста).
7. viewer-team: 4 self-rework фикса в PR-C (UI-баг кнопки в списке + многопутевой `_graphNodeIdOf`) — without rework контракта/парсера.
8. Мерж C → пост 008 (closure) + Changelog + §9.

**Время цикла:** 1 календарный день от первого предложения до зелёного main с UI.

## Тесты

- parser: **28 passed** (17 `test_graph_node_id.py` + 11 `test_build_kmz_v2.py`), 1 pre-existing failure (pdfplumber отсутствует в окружении, не моя регрессия).
- viewer: `node --check viewer/index.html` чист; `_graphNodeIdOf` нашёл id у всех 6 cad-маркеров на mini-fixture (`document.getElementsByClassName('mark-graph-btn').length === 6`).

## Backward-compatibility

- **viewer 2.10.x + KMZ от parser 2.11.0:** `<Data name="graph_node_id">` игнорируется, остальное работает. ✅
- **viewer 2.11.0 + KMZ от parser 2.10.x:** поле отсутствует → кнопки 🕸 нет (gating через наличие `graph_node_id`); остальное работает. ✅
- **mixed `graph.html`:** если по какой-то причине новый KMZ имеет старый граф — `postMessage` no-op (worst-case), визуального бага нет.

## Out of scope (S6+)

Зафиксированы как «будущее» в `CONTRACT_KMZ §9` и постах 005/008:

- **Multi-level Z** для помещений (`cad_room_*` на нескольких этажах с Z-привязкой ОС к высоте пола конкретного уровня). MAJOR-bump.
- **Ingesters ОСВ/ЕГРЮЛ/ЕГРИП** — отдельные скрипты вне `parser/scripts/`.
- **EXIF-роутинг lightbox**: viewer парсит `UserComment.graph_node_id` из открытого документа → кнопка «🕸 в граф для этого документа». Чисто viewer-инициатива, контракт не расширяется.
- **MessageChannel** как опц. усиление postMessage-канала.
- **De-sandbox** для подписанных KMZ (`allow-same-origin` + meta-feature-detect).

## Что не понадобилось

- Не пришлось трогать `03_enrich_v14.py` — sidecar делает 04, который и так знает все node-id'ы.
- Не пришлось расширять `08` для чтения enriched.json — sidecar от 04 покрыл потребность.
- Не пришлось вводить новый MAJOR (всё аддитивно).
- Feature-detect через `<meta>` оказался unreliable в sandboxed iframe (viewer-team обнаружили) — fallback'нулись на гейтинг через наличие `graph_node_id`, что даже элегантнее.
