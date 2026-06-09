# 2026-06-09 — E: агро-агрегаты (вьюхи отчётов)

Продолжение без A (техкарта). E на деле не требует техкарты — вьюхи и
JSON-развороты пишутся/тестируются на синтетике; от A нужны только реальные числа.

## Сделано
- **Миграция `0008_agro_aggregates.sql`** (ADR-006 §D) — 4 вьюхи поверх
  agro_event/agro_crop_cycle/agro_parcel:
  - `v_agro_harvest_by_variety` — урожай по сортам/сезонам/полям (Σ volume_kg);
  - `v_agro_harvest_timing` — сроки сбора + кислотность/сахар (json_extract);
  - `v_agro_pesticide_load` — пестицидная нагрузка, разворот `active_substances[]`
    через `json_each` → Σ rate по веществу/полю/сезону;
  - `v_agro_lot_techscheme` — техсхема лота (фактические циклы по полям за сезон).
- **`agro_reports.py`** — `ensure_views` (идемпотентно) + запросы
  `harvest_by_variety`/`harvest_timing`/`pesticide_load`/`lot_techscheme` → list[dict].

## Тесты
- `tests/test_agro_reports.py` (+6): урожай по сортам (2 прохода Σ), сроки+качество,
  разворот пест. веществ, техсхема (только fact, план исключён), пустая БД,
  исполнимость миграции 0008.
- `pytest` агро+земля → **52 passed**.

## Docs
- SPEC §12 — агро-агрегаты ✅.
- roadmap — E закрыт; остаётся A (блокер) → H(viewer). Весь разблокированный
  parser-слой завершён.

## Файлы
- `schema/migrations/0008_agro_aggregates.sql` (новый)
- `parser/egrn_parser/parsers/agro_reports.py` (новый)
- `parser/tests/test_agro_reports.py` (новый)
- `docs/specs/SPEC_parser.md`, `obsidian/Architecture/roadmap-land-agro-graph.md`
