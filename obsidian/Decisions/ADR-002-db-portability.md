# ADR-002: SQLite (dev/export) ↔ PostgreSQL (prod) — единый слой доступа

**Date:** 2026-05-28
**Status:** accepted
**Supersedes:** —
**Related:** ADR-001 (etp-profile-extension), `obsidian/Database/dialect-portability.md`

## Контекст

Архитектурный план развития:
- **dev / per-user export**: SQLite-файл (текущий `parser/egrn_parser/db.sqlite`, выгрузка пользователю «слепка объекта» в виде `.sqlite`-файла, открываемого DB Browser).
- **prod (Timeweb apps)**: PostgreSQL — нужен под многопользовательский режим, потому что SQLite блокируется на запись.

Без общей абстракции код парсера придётся писать дважды (или потом переписывать). Диалект-специфичные конструкции (`INSERT OR REPLACE`, `PRAGMA`, `AUTOINCREMENT`, `RETURNING`, `JSON_EXTRACT`) ломаются при переезде.

## Решение

Зафиксировать ограничения **до** написания нового кода на БД:

1. **Запросы — только через SQLAlchemy Core 2.x.** Raw SQL в Python-коде — отказ при review.
2. **Миграции — только через alembic** с двумя `sqlalchemy.url` (`sqlite:///...` и `postgresql+psycopg://...`). Один набор миграционных файлов для обеих БД. `DROP COLUMN`/`ALTER COLUMN` — через `op.batch_alter_table` (alembic подставляет workaround для SQLite автоматически).
3. **Типы** — через SA: `Integer`, `Text`, `Float`, `JSON`, `Boolean`, `DateTime(timezone=False)`. Никаких `VARCHAR(n)` в PG (бессмысленно), никаких `DATETIME('now')` в SQLite (текущее время — из Python, всё в UTC).
4. **Координаты** — `Text` с WKT. **Без PostGIS** до отдельного ADR. Когда потребуются гео-запросы на сервере — миграция включит PostGIS только для Postgres-инстанса, SQLite-снепшоты для пользователей останутся без него (WKT-строки самодостаточны).
5. **Конфликты вставки** — через диалект-нейтральный helper или универсальный pattern `select-then-insert/update` под транзакцией. `INSERT OR REPLACE`, `ON CONFLICT DO UPDATE` — только через SA-обёртку, не raw.
6. **Per-object export как SQLite-файл**: prod-сервис создаёт временный `.sqlite`-файл через тот же SA-слой (url=sqlite-file), прогоняет подмножество §1..§6 для заданного `object_id`. Схема `.sqlite`-снепшота **идентична** prod-схеме (одна и та же alembic-голова).

## Что НЕ делаем сейчас

- Не разворачиваем Postgres-окружение, не пишем `alembic` setup, не мигрируем существующий код.
- Не трогаем `parser/egrn_parser/db.sqlite` и текущую `schema/egrn_current_schema.sql`.
- Не пишем код per-object snapshot — он появится, когда заработает prod на Postgres.

ADR фиксирует **правила для нового кода**. Существующий код приводится в соответствие постепенно, по мере правок.

## Acceptance

PR с правкой на БД (`parser/**/db*`, `schema/**`, `parser/**/models*`) отклоняется, если:
- содержит raw SQL без обёртки через SA Core;
- использует запрещённую конструкцию из `obsidian/Database/dialect-portability.md`;
- содержит `ALTER TABLE` / `DROP COLUMN` напрямую вместо `op.batch_alter_table`.

Автоматические гарантии (вводятся постепенно):
- Тесты, прогоняемые на in-memory SQLite сейчас, после ввода Postgres-окружения — на обеих БД.
- skill `db-portability` (см. `.claude/skills/db-portability/SKILL.md`) подсасывается на правках БД, напоминает про правила.

## Соответствие ADR-001

ADR-001 (§6 не-ЕГРН слой: `object_etp_profile`, `lots`, `lot_items`) — не меняется. ADR-002 описывает **как** писать запросы к этим таблицам, не **что** в них хранится.

## Открытые точки

- Когда переезжать с SQLite на Postgres в prod — отдельным ADR в момент, когда появится готовый FastAPI-слой.
- PostGIS — отдельным ADR, когда возникнет запрос на гео-фильтр «все объекты в bbox» на сервере.
