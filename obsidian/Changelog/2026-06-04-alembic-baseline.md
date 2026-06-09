# 2026-06-04 — Alembic-baseline C2 (§7–§12)

## Суть
По плану: первая миграция = вся C2-ORM-схема дата-инженера. Проверена на реальном
`models.py` (не на бумаге).

## Сделано
- `contracts/db/alembic.ini` + `migrations/{env.py,script.py.mako}` — переносимое
  окружение SQLite↔PG (`render_as_batch` для SQLite, `EKCELO_DB_URL` для PG).
- `contracts/db/migrations/versions/0001_baseline_*.py` — baseline, **25 таблиц** §7–§12.
- `contracts/db/seed.py` — идемпотентный сид `relation_types` из `relation_types_seed.py`.
- `contracts/db/MIGRATIONS_README.md`.

## Проверено (SQLite, sqlalchemy 2.0.50 / alembic 1.18.4)
- `upgrade head` → 25 таблиц зелёным.
- сид → 30 `relation_types` (legal 14 вкл. corporate, spatial 6, tech 4, accounting 3, commercial 3).
- `downgrade base` → чистый round-trip.
- поправлен баг автогена: `astext_type=Text()` → `sa.Text()` (11 мест).

## Открыто (follow-up, в README)
§1–§6 (ЕГРН-слепок + ЭТП) ещё не в `models.py` — рекомендую портировать и сделать
`0002`, иначе FK §7→§6 и лоты в разных мирах миграций.

## Дальше
Стадия импорта Block-2 БД парсера (land/building_objects/accessories →
objects+граф-таблицы); сведение graph v1.1/v14 к одному эмиттеру.
