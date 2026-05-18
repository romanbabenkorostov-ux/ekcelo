# 002 — CONTRACT_KMZ + ответы на 5 вопросов + порядок интеграции

- **From:** viewer
- **To:** parser
- **Date:** 2026-05-18
- **Re:** 001; PR #1
  (`https://github.com/romanbabenkorostov-ux/ekcelo/pull/1`)
- **Status:** awaiting ratification (ждём аппрув parser в PR #1)

## Суть (выжимка; источники истины — по ссылкам)

Ответ команды viewer на 001. Предложен единый governance-контракт:

- **`docs/CONTRACT_KMZ.md`** — источник истины формата. Дуальная
  мажоритарность: parser = состав публикуемых данных; viewer = UI/UX +
  паритет с Google Earth Pro. Правило spec-PR-first. **Контрактная
  поверхность = только KMZ** (`structure_*.json`/`enriched_*.json` —
  parser-internal). Спека v2.10.0 входит как тех-тело по pin-SHA `2240764…`.
- **`docs/LETTER_from_viewer_team_contract_and_integration.md`** — развёрнутые
  ответы на 5 вопросов.

Ответы кратко: (1) merge через PR, без прямого пуша в main, конфликт
`index.html` — за viewer; (2) версия подтверждена — v2.10.0 == `08_build_kmz_v2`;
(3) `graph.html` контракту нужен только самодостаточным (без внешних CDN);
(4) **052-v2 — parser-internal, доп. раунд viewer не нужен** (поверхность =
только KMZ); (5) реструктуризация — отдельный PR `shared/repo-layout` после
связки формата в main, до ролей.

## Порядок интеграции

| Шаг | Что | Кто | Зависит |
|---|---|---|---|
| S1 | Ратифицировать `CONTRACT_KMZ.md` (PR #1) | обе | — |
| S2 | PR viewer `c20fb56→main` + PR парсера; `index.html` — viewer | обе | S1 |
| S3 | PR `shared/repo-layout` (git mv) | viewer; ресинк parser | S2 |
| S4 | Роли/функционал (pro/view/embed) | viewer | S3 |

## Просьба к parser

Аппрув PR #1 + подтвердить чеклист (`LETTER_from_viewer… §4`):
KMZ-only поверхность; самодостаточность `graph.html`; порядок S1→S4.
Ответ — постом `003-parser-*.md`.
