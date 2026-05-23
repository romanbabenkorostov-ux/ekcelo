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
