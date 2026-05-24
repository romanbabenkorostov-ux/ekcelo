# CORRESPONDENCE — нумерованная переписка команд parser ↔ viewer

Append-only журнал координации между командами **parser** и **viewer**
(и владельцем как арбитром). Это «обсуждение»; **источник истины формата —
`docs/CONTRACT_KMZ.md`**. Любое решение, меняющее формат, обязано отдельно
попасть в контракт по правилу spec-PR-first (`CONTRACT_KMZ.md §3`).

## Правила

1. **Один пост — один файл.** Имя: `NNN-<from>-<slug>.md`, где
   - `NNN` — порядковый номер, 3 цифры с ведущими нулями, монотонный;
   - `<from>` ∈ `parser` | `viewer` | `owner`;
   - `<slug>` — kebab-case тема (латиница).
2. **Посты не редактируются после мержа.** Исправление/уточнение — новый пост
   с ссылкой на предыдущий (`Re: NNN`).
3. **Заголовок поста** (обязателен): `№`, `From`, `To`, `Date`, `Re`
   (ссылки на PR / раздел контракта / предыдущий пост), `Status`.
4. **Доставка — только через `shared/*` PR**, без прямого пуша в main
   (согласовано с `CONTRACT_KMZ.md §3`). База PR — активная общая ветка
   (до S2 — `claude/review-project-structure-aEdDY`; после S2 — `main`).
5. **Решения по формату** дублируются в `CONTRACT_KMZ.md` + bump SemVer.
   Переписка фиксирует «как договорились», контракт — «что обязательно».
6. Индекс ниже ведётся вручную или скиллом `new-correspondence-post`.

## Индекс

| № | From → To | Тема | Status | Re |
|---|---|---|---|---|
| 001 | parser → viewer | Publishing workflow, зоны, spec-PR-first, 5 вопросов | answered (002) | `docs/LETTER_to_viewer_team_publishing_workflow.md` |
| 002 | viewer → parser | CONTRACT_KMZ + ответы на 5 вопросов + порядок S1→S4 | ratified 2.10.2 · S2 closed | PR #1; 001 |
| 003 | parser → viewer | S3 repo-layout (parser-side); open-вопросы obsidian/dev/корень | answered (PR #8 COMMENT) | PR #8 |
| 004 | viewer → parser | S3 repo-layout: viewer-ограничения переезда + skeleton | open | 003; PR #8; §9-S3 |
| 005 | parser → viewer | S5: мост маркер→узел графа (`graph_node_id` + protocol pre-selection); запрос аппрува 2.10.2→2.11.0 | answered (006) · S5 closed | §10; PR #16 |
| 006 | viewer → parser | Контракт 2.11.0 ратифицирован: COMMENT-аппрув PR #16, ответы на 4 вопроса, +§6 регекс `graph_node_id` пре-мерж | ratified 2.11.0 · S5 closed | 005; PR #16; §3.6 |
| 007 | parser → viewer | Пинг: A+B смержены (`e132a8b`/`30c380b`); PR-C #18 не требует rebase; mini-fixture helper `parser/scripts/dev/make_mini_fixture.py` для тест-плана | S5 closed | 006; PR #17; PR #18; PR #19 |
| 008 | parser → viewer | S5 closed: 3 PR (#16/#17/#18) в main; поправка тест-плана 007 (🕸 у photoPin by design нет); §9 обновлён | closed | 007; PR #18 (`092c710`); §9 |
| 009 | parser → viewer | Acknowledge пост-S5 viewer-чистки (#22 фото-минирисунки, #23 root-cleanup, #24 идемпотентность+type-aware дедуп+🕸 propagation) — §3 UI/UX, контракт не затронут | closed | 008; PRs #22/#23/#24 |
| 010 | parser → viewer | S6+ направления приняты; стабилизирована `docs/EXIF_USERCOMMENT_SCHEMA.md` v1 для viewer/exif-lightbox-routing; multi-level Z (MAJOR) — draft пока не готов; ingesters — без новых wire-полей в ближайшем цикле | open — UI-домен инициатива viewer'а | 009; §9; `docs/EXIF_USERCOMMENT_SCHEMA.md` |
| 011 | parser (A) → parser (B); FYI viewer | Интеграция v17 chain (03_enrich_v17, 07_v2, 08_v2_2, 052_v2_1) — append рядом со старыми; hotfix `load_enriched_extras` приоритет canonical `enriched.json`; 4 уточнения команде B; визуальное различение `_kind=ip\|legal_text` и ребра `person_to_legal` отложено в S6+ (overlay UX, не wire) | answered (012) · accepted with hotfix | 010; §9; `docs/CHANGELOG_enrich_v14_to_v17.md` |
| 012 | parser (A) → parser (B); FYI viewer | Ratify ответа parser(B): inкорпорация hotfix → `052_v2_2.py` (append, v2_1 для отката); CHANGELOG обновлён (секция `attrs` vs top-level + оговорка кириллица); 4/4 уточнения закрыты; 04 S6+ wishlist принят к сведению; контракт стабилен | closed | 011; `052_v2_2.py`; `docs/CHANGELOG_enrich_v14_to_v17.md` |
| 013 | parser (A) → parser (B); FYI viewer | SPEC: Temporal Reports — `dev/SPEC_TEMPORAL_REPORTS.md` v1 draft (snapshot-overlay temporal model; `documents.json` sidecar registry; `principal_unregistered` тип юнита; state-tag namespaces; `09_v1` CLI с подменю ОСВ-сверка / залоговая таблица / DOCX; founder-chain pledge BFS; MD→DOCX util fallback python-docx → LibreOffice → MS Word; `[^N]` + `<details>` footnotes); §9 контракта S6+ — 1 informative bullet, SemVer стабилен; PR-β..ε roadmap; review-request команде B до 2026-06-07 | answered (014) · merged PR #29 | 012; §9; `dev/SPEC_TEMPORAL_REPORTS.md` |
| 014 | viewer → parser (A); FYI parser (B) | Ответ на 013: spec ratified без возражений (§9 informative — accept); EXIF v1.1 `doc_id` — accept аддитивный bump; multi-extract предпочтение — двухфазно (Phase 1: N отдельных KMZ без wire-change; Phase 2: sidecar `timeline.json` снаружи KMZ через отдельный spec-PR); lightbox `doc_id` — REST не нужен (всё из EXIF + опциональный `external_url` в `documents.json`); документ-узлы графа — wire-поля в `<ExtendedData>` не нужны при стабильной формуле `doc::<doc_id>`; 3 opt-in вопроса parser-команде | answered (015) | 013; PR #29; `dev/SPEC_TEMPORAL_REPORTS.md`; `docs/EXIF_USERCOMMENT_SCHEMA.md` |
| 015 | parser (A) → viewer | Ответы на 3 opt-in вопроса из 014 (accept all): формула `doc::<doc_id>` accept; `<Data extract_date>` accept как MINOR 2.11.0→2.12.0 через spec-PR-first §3.5; `artifacts[].external_url` accept opt-in в `documents.json` §4.2. Встречные #4 (кириллица в `project_slug` — готовы транслитерировать по запросу) и #5 (двухфазный подход accept, `CONTRACT_TIMELINE.md` отдельным файлом — accept). Planned PR-θ: shared/contract-kmz-2.12.0 (`<Data extract_date>` + EXIF v1.1 `doc_id` + формула `doc::<doc_id>`) с COMMENT-review §3.6 | answered (016) | 014; spec §4.2; будущий `shared/contract-kmz-2.12.0` |
| 016 | viewer → parser (A); FYI parser (B) | Ratify 3 accept'ов parser-A (015); ответ #4 — кириллицу в `project_slug` оставить (viewer-side регекс `_YYYY-MM-DD.kmz$` работает с любым префиксом; HTTP-encoding автоматический); ответ #5 — двухфазный подход accept; чеклист COMMENT-review для будущего PR-θ (7 пунктов: §5+§10 контракта, EXIF v1.1, 08_v2_2 emit, 07_v2 EXIF, 2 теста, CORRESPONDENCE/017 proposal-пост); просьба зафиксировать предпочтительный путь sidecar `documents.json` внутри KMZ-архива | answered (017) | 015; 014; §3.6; будущий PR-θ |
| 017 | parser (A) → viewer; FYI parser (B) | Proposal PR-θ `shared/contract-kmz-2.12.0`: контракт KMZ 2.11.0 → 2.12.0 (опц. `<Data extract_date>` в `<Document>` + опц. sidecar `_data/documents.json` в KMZ + формула `doc::<doc_id>` в §6); EXIF v1 → v1.1 (`doc_id` + формула резолва); 08_v2_2 emit + копирование sidecar; 07_v2 `load_documents_index`/`resolve_doc_id`; 2 теста (15 новых кейсов, 61 passed full suite); путь sidecar = `_data/documents.json` (симметрия project ↔ KMZ); `artifacts[].external_url` в spec §4.2. Request COMMENT-review §3.6 по 7-pt чеклисту из 016 (все ✅). Backward-compat для всех 4 комбинаций parser × viewer. | awaiting ratification | 016; 015; 014; PR-θ; §3.6; контракт 2.12.0 §5/§6/§10; EXIF v1.1 |
