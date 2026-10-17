# SQLite ↔ PostgreSQL — справочник совместимости

Справочник по правилам ADR-002. Запрещённые конструкции и SA-эквиваленты.

## Запрещены в новом коде

| Конструкция | Где работает | Почему запрещена | Замена |
|---|---|---|---|
| `INSERT OR REPLACE INTO ...` | SQLite | Не работает в Postgres | `insert(table).values(...).on_conflict_do_update(...)` через SA-диалект-нейтральный helper или `select-then-update/insert` под транзакцией |
| `INSERT OR IGNORE INTO ...` | SQLite | Не работает в Postgres | `insert(table).values(...).on_conflict_do_nothing(...)` |
| `AUTOINCREMENT` | SQLite (плохая семантика) | В Postgres другой синтаксис (`SERIAL`/`IDENTITY`) | `Column('id', Integer, primary_key=True, autoincrement=True)` — SA сама выберет диалект |
| `PRAGMA ...` | SQLite | Не существует в Postgres | Управлять параметрами соединения через `engine.connect()` events или `connect_args` |
| `RETURNING *` напрямую | оба, но в SQLite только с 3.35+ | Версии Python/SQLite в окружении пользователя могут быть старее | `insert(...).returning(table.c.id)` через SA — она проверит поддержку |
| `JSON_EXTRACT(col, '$.path')` | SQLite | В Postgres — `col->>'path'`, синтаксис разный | `func.json_extract_path_text(col, 'path')` через SA или использовать `JSON`-тип с Python-доступом |
| `DATETIME('now')` | SQLite | В Postgres — `NOW()` | Текущее время — **из Python**: `datetime.utcnow()`, всё хранится в UTC |
| `VARCHAR(n)` | оба | В Postgres лимит без пользы, в SQLite просто игнорируется | `Text` (без лимита). Валидация длины — на уровне Python, не БД |
| `BOOLEAN` как `1`/`0` напрямую | SQLite | В Postgres строгий `bool` | `Boolean` через SA — она хранит как `INTEGER` в SQLite, как `bool` в Postgres |
| `ALTER TABLE ... DROP COLUMN` | оба, но в SQLite до 3.35 — нет | Старый SQLite ломается | `op.batch_alter_table(...)` в alembic — он сам пересобирает таблицу для SQLite |
| `CREATE INDEX ... WHERE` (partial) | оба | Синтаксис разный для Postgres ≥9.5 | `Index('name', col, sqlite_where=..., postgresql_where=...)` через SA |

## Что использовать (разрешено)

| Зачем | Как |
|---|---|
| Тип целого | `Integer` |
| Тип строки | `Text` |
| Тип числа с плавающей точкой | `Float` |
| Тип JSON | `JSON` (SA-тип, нейтральный) |
| Тип булева | `Boolean` |
| Тип даты-времени | `DateTime(timezone=False)`, всё UTC |
| Тип координат | `Text` с WKT (например `POLYGON((37.5 55.7, ...))`) |
| Первичный ключ | `Column('id', Integer, primary_key=True, autoincrement=True)` |
| Внешний ключ | `Column('parent_id', Integer, ForeignKey('parents.id'))` |
| Уникальность | `UniqueConstraint(col_a, col_b, name='uq_xxx')` |
| Текущее время | `datetime.utcnow()` в Python, не через БД |
| Транзакция | `with engine.begin() as conn:` |

## PostGIS

**Не используем до отдельного ADR.** Координаты хранятся как WKT-строки в `Text`-колонке. Когда потребуются гео-запросы на сервере:

- Postgres-инстанс включит расширение `postgis`.
- SQLite-снепшоты для пользователей **останутся без PostGIS** — WKT самодостаточен для open-in-QGIS/GoogleEarth.
- Запросы «в bbox» — в Postgres через PostGIS, в SQLite-снепшоте через Python (фильтр в коде, не в БД).

## Тесты

Каждый тест парсера/API, трогающий БД:
- сейчас: in-memory SQLite (`sqlite:///:memory:`).
- после ввода Postgres-окружения: запускается **дважды** — на SQLite и на тестовом Postgres (docker-compose в CI). Если запрос работает только на одном — баг.

## Per-object SQLite export для пользователя

Архитектура (детали — в отдельном ADR, когда заработает prod):
- сервис создаёт временный файл `tmp.sqlite`;
- открывает второй SA-engine с `sqlite:///tmp.sqlite`;
- прогоняет alembic-миграции (та же голова, что в Postgres) для создания схемы;
- копирует подмножество §1..§6 по `object_id` через SA-select-then-insert;
- отдаёт `tmp.sqlite` пользователю.

Пользователь открывает файл в DB Browser for SQLite или своим Python-скриптом. **Схема идентична prod**, никаких конвертеров.
