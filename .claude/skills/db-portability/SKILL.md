---
name: db-portability
version: 1.0
description: |
  Применяется при любых правках в schema/, parser/**/db*, parser/**/models*,
  миграциях, новом SQL-коде. Обеспечивает совместимость SQLite (dev / per-user
  export) и PostgreSQL (prod). Запрещает диалект-специфичные конструкции,
  требует SQLAlchemy Core 2.x и alembic batch_alter_table. См. ADR-002.
tags: [database, schema, migrations, portability, sqlite, postgres]
---

## Когда срабатывать

- Правка `schema/**`, `schema/migrations/**`.
- Любой новый Python-файл в `parser/`, который читает/пишет БД.
- Новый запрос/миграция в существующих модулях `parser/egrn_parser/db/`.
- Обсуждение per-object SQLite export.

## Жёсткие правила (ADR-002)

1. **Только SQLAlchemy Core 2.x.** Raw SQL в коде — отказ при review.
2. **Миграции только через alembic.** `DROP COLUMN` / `ALTER COLUMN` — через `op.batch_alter_table` (работает на обеих БД).
3. **Запрещены конструкции:**
   - `INSERT OR REPLACE/IGNORE` → `insert(...).on_conflict_do_update/nothing(...)`
   - `AUTOINCREMENT` → `autoincrement=True` в `Column`
   - `PRAGMA ...` → `connect_args`
   - `DATETIME('now')` → `datetime.utcnow()` из Python
   - `VARCHAR(n)` → `Text`
   - `JSON_EXTRACT(...)` → SA-`JSON`-тип + Python-доступ
   - `1`/`0` для bool → `Boolean`
4. **Типы:** `Integer`, `Text`, `Float`, `JSON`, `Boolean`, `DateTime(timezone=False)`. Всё UTC.
5. **Координаты:** WKT-строка в `Text`. **Без PostGIS** до отдельного ADR.
6. **Тесты:** трогающие БД — на in-memory SQLite (`sqlite:///:memory:`). Постгрес-тесты добавятся в CI позже.

## Acceptance check

Перед сдачей PR:
- [ ] Нет raw SQL без SA-обёртки.
- [ ] Нет конструкций из списка запрещённых.
- [ ] Типы — из разрешённого списка.
- [ ] Миграция использует `op.batch_alter_table` для DROP/ALTER COLUMN.
- [ ] Тесты гоняются на in-memory SQLite, проходят локально.

## Справки

- `obsidian/Decisions/ADR-002-db-portability.md`
- `obsidian/Database/dialect-portability.md`
- `obsidian/Decisions/ADR-001-etp-profile-extension.md` (контекст §1..§6)
