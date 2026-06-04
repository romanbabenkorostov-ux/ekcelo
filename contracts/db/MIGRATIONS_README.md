# C2 — Alembic-миграции (contracts/db)

Источник истины схемы — `contracts/db/models.py` (`Base.metadata`). Миграции
переносимы **SQLite ↔ PostgreSQL** (`render_as_batch=True` для SQLite, `EKCELO_DB_URL`
для PG). Проверено: `upgrade head` → 25 таблиц, сид 30 `relation_types`, `downgrade
base` round-trip — зелёное на SQLite 2.0.50 / Alembic 1.18.4.

## Состав
```
contracts/db/
  alembic.ini                      # конфиг (url из env EKCELO_DB_URL или sqlite-файл)
  migrations/
    env.py                         # импортит models.Base, batch-режим для SQLite
    script.py.mako
    versions/0001_baseline_*.py    # baseline: §7-§12 (25 таблиц)
  seed.py                          # идемпотентный сид relation_types
```

## Запуск (из каталога `contracts/db`)
```bash
# 1. поднять окружение
pip install "sqlalchemy>=2.0" alembic

# 2. SQLite локально (по умолчанию пишет в contracts/db/ekcelo.db)
alembic -c alembic.ini upgrade head

# 2'. PostgreSQL
export EKCELO_DB_URL="postgresql+psycopg://user:pwd@host/ekcelo"
alembic -c alembic.ini upgrade head

# 3. сид справочника типов рёбер
EKCELO_DB_URL=sqlite:///contracts/db/ekcelo.db python -m contracts.db.seed
```

## Что покрывает baseline 0001
**§7–§12** (NEW-слои из `models.py`): `entities, relation_types, relations,
legal/tech/spatial/accounting_relation, assertions, evidences, geometries, devices,
flow_events, subjects, subject_names, subject_kpp, bank_accounts, ip_status_periods,
subject_external_ref, lot_snapshots, orders, contracts, invoices, upd_documents,
documents, doc_links` — 25 таблиц.

## ⚠️ Что НЕ покрывает (follow-up)
**§1–§6** (ЕГРН-слепок + ЭТП: `objects, entity_registry, rights, extracts,
object_restrictions, object_etp_profile, lots, lot_items`) пока живут в
`schema/egrn_current_schema.sql` и **не внесены в `models.py`**. Варианты на решение
архитектора:
1. портировать §1–§6 в `models.py` и сделать миграцию `0002` (единый источник истины);
2. оставить §1–§6 как raw-DDL, а C2-ORM держать только над NEW-слоями + FK-мост.

Рекомендация: (1) — иначе FK из §7 (напр. `accounting_relation.subject_id`,
`legal_relation.legal_document_id`) и §6-лоты живут в разных мирах миграций.

## NB по автогенерации
Из-за `JSON().with_variant(JSONB(astext_type=Text()))` Alembic autogenerate печатает
неквалифицированный `Text()` — в `0001` поправлено на `sa.Text()` (11 мест). При
следующих `--autogenerate` проверять этот момент.
