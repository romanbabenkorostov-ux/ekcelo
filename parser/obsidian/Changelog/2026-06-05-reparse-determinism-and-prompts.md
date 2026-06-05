# 2026-06-05 — Детерминизм повторного парсинга + UX промптов + demo-guard

## Суть
По итогам теста экономиста: (1) повторный парсинг одних выписок давал ложные diff'ы;
(2) промпты неудобны (`Д/н` без дефолта); (3) `make_demo_block2` падал на существующей БД.

## Сделано
- **`parser/egrn_parser/merge/differ.py`** — JSON-массивы сравниваются канонически
  (порядок не важен, пустой ≡ None): `object_restrictions`, `permitted_uses`,
  `land_cad_numbers`, `old_numbers`, `nested_objects`. Реальные изменения значений — фиксируются.
- **`parser/egrn_parser/merge/interactive.py`** — `Д/н` → `y/n` с дефолтом из
  рекомендации (Enter = рекомендация); общий выбор `[e/r/n/s/d/q]`, Enter=enrich;
  фикс бага `д`→`d`.
- **`contracts/db/make_demo_block2.py`** — проверка существующей БД (оставить/пересоздать),
  `--force`, безопасно без TTY.
- **`parser/tests/test_differ_json_canonical.py`** — замок (4 теста, passed).
- **`obsidian/Architecture/parser-reparse-determinism.md`** — диагностика + нормативная основа.

## Корневые причины (детали в диагностике)
1. Один отчёт парсится и из PDF, и из XML; классификаторы ограничений расходятся +
   разный порядок JSON → ложный diff.
2. `parent_cad_number` обогащается алгоритмом, сырой re-parse его не содержит → diff.

## Проверено
`pytest parser/tests/test_differ_json_canonical.py` — 4 passed; differ: переупорядоченные
ограничения → нет diff, смена типа → diff; demo-guard (create/exists/force) — ок.

## Рекомендации (follow-up)
Дедуп входа (XML > PDF на один отчёт); выравнивание классификаторов ограничений;
провенанс полей (не диффить enriched против raw).
