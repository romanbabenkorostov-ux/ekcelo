# 2026-06-08 — P0.1 DB-контракт C2 sub-stage P0.1.1

## Что сделал
Машиночитаемый DB-контракт interchange-схемы Bundle + валидатор + CI sync-guard.

## Файлы
- ✨ `contracts/db/schema.json` — машиночитаемый контракт (8 таблиц, secties §1..§6, restorable=true/false).
- ✨ `contracts/db/DB_SPEC.md` — человекочитаемая спека.
- ✨ `backend/app/services/db_contract.py` — `load_contract`, `validate_db`, `check_contract_matches_ddl`.
- ✨ `backend/tests/test_db_contract.py` — 13 тестов (3 load + 5 validate + 5 sync-guard).
- ✨ `obsidian/Architecture/p0-db-contract.md` — снимок P0.1.1.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — P0.1 разбит на P0.1.1 ✅ + P0.1.2..4 план.
- ✏️ `obsidian/CHECKPOINT.md` — live-указатель.

## Тесты
- 13 новых, все зелёные.
- Полный suite: **299 passed** (286 после C3.2 + 13 P0.1.1).
- Регрессий нет.

## Решения

- **Контракт читает существующую interchange-схему, не меняет её.** После
  round-trip C3.2 формат `db.sqlite` внутри Bundle стабилен. P0.1.1 фиксирует
  его машиночитаемо — это формализация, не новое требование. Parser-team не
  должен ничего менять (см. §«Почему НЕ блокирует parser-team»).
- **Источник правды — DDL (`schema/egrn_current_schema.sql`), контракт зеркало.**
  При любом изменении DDL контракт обновляется вручную, sync-guard ловит
  забытое. Альтернатива (генерировать DDL из контракта) — overkill для 8 таблиц
  и теряет SQL-нюансы (CHECK constraints, defaults).
- **§6 restorable=false проверяется опционально.** ADR-001: ЭТП-слой может
  отсутствовать в чистом ЕГРН-слепке. Дефолт `require_section6=False` отражает
  это; для строгого режима — `validate_db(db, require_section6=True)`.
- **Лишние колонки в БД — НЕ нарушение.** Схема расширяема вперёд (parser
  может эмитить дополнительные поля для будущих версий контракта; backend
  игнорирует неизвестные через `extra="allow"` в Pydantic-моделях).
- **Lightweight regex-парсер DDL.** Полный SQL-парсер избыточен для guard'а
  «контракт не отстал от schema.sql». Regex покрывает: `CREATE TABLE ... (...)`,
  strip-comments, top-level split по запятым, фильтрация table-level constraints.
- **Sync-guard — критический тест.** При забытом обновлении контракта тест
  `test_contract_in_sync_with_real_ddl` падает с точным diff'ом, что не позволит
  смерджить расходящееся состояние.

## Канал доставки
- Sandbox-proxy блокирует git push — zip-handoff.
- Архив P0.1.1 готов к доставке.

## Следующий шаг
1. Применить архив P0.1.1, открыть PR, прислать номер.
2. **P0.1.2** — интеграция `validate_db` в `import_bundle` (early-fail на
   невалидном db.sqlite в Bundle) + CLI `ekcelo-validate-bundle-db`.
