# 2026-06-04 — Порт §1–§6 (ЕГРН+ЭТП) в ORM + миграция 0002

## Суть
По выбору заказчика: §1–§6 из `schema/egrn_current_schema.sql` перенесены в ORM на
общий `Base`, теперь вся C2-схема (§1–§12) — один `Base.metadata` и одна история Alembic.

## Сделано
- `contracts/db/models_egrn.py` — §1–§6 на общем Base: `objects, entity_registry,
  rights, extracts, object_restrictions, object_etp_profile, lots, lot_items`.
  Натуральные ключи (cad_number/inn/lot_id) сохранены; CHECK-и (etp source/confidence,
  lot_id charset/len, deal_type, role) перенесены; JSON-поля → PortableJSON; даты → DateTime.
- `contracts/db/migrations/env.py` — `+ import contracts.db.models_egrn` (регистрация на метаданных).
- `contracts/db/migrations/versions/0002_egrn_c2_egrn_layers_1_6.py` — +8 таблиц §1–§6.

## Проверено (SQLite)
- `upgrade head` (0001→0002) → **33 таблицы** (25 §7–§12 + 8 §1–§6).
- сид `relation_types` → 30; FK-цепочка objects→rights→entity_registry и lots→lot_items вставляется.
- `downgrade base` round-trip чистый.
- баг автогена `Text()` → `sa.Text()` поправлен (8 мест в 0002).

## Отличия порта от исходного DDL (осознанно)
- `updated_at/parsed_at/created_at`: TEXT → DateTime (server_default=now).
- JSON-в-TEXT (etp-профиль, raw_json, platform_targets): TEXT → PortableJSON (JSONB на PG).
- Поведение и ключи идентичны; смысл сохранён.

## Порядок выкладки
A (описание) → B (alembic-baseline 0001) → **C (этот: 0002 + models_egrn + env.py)**.
`env.py` здесь обновлён — перезаписывает версию из B.

## Дальше
Soft-связи §7↔§6 (lot_snapshots.lot_id ↔ lots.lot_id, subjects.inn ↔ entity_registry.inn)
— оставлены строковыми по SCHEMA_SPEC; при желании ужесточить FK — миграция 0003.
Затем стадия импорта Block-2 БД и единый граф-эмиттер.
