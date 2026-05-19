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
| 005 | parser → viewer | S5: мост маркер→узел графа (`graph_node_id` + protocol pre-selection); запрос аппрува 2.10.2→2.11.0 | answered (006) | §10; PR #16 |
| 006 | viewer → parser | Контракт 2.11.0 ратифицирован: COMMENT-аппрув PR #16, ответы на 4 вопроса, +§6 регекс `graph_node_id` пре-мерж | ratified 2.11.0 · awaits A→B→C merge | 005; PR #16; §3.6 |
