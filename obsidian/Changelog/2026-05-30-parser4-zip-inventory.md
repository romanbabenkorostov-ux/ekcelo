# 2026-05-30 — Inventory параллельной разработки команды parser (zip parser4)

## Итог
Принят zip `5abdef30-parser4.zip` (E:\Code\ekcelo\code\parser\<dir>) — 4 группы модулей от других разработчиков. Зафиксированы в `obsidian/Architecture/parallel-parsers-map.md` + `obsidian/Decisions/ADR-002-parser-checko-integration-policy.md`. В `main` ничего не вносим — все 4 группы документированы как existing-of-record для будущих циклов.

## Что внутри zip

| Группа | Файлов | Статус |
|---|---|---|
| `egrn_parser/` | 51 (3 новых: MIGRATION.md, README.md, pyproject.toml; остальные идентичны репо по контенту, только CRLF) | accept docs+pyproject отдельным PR при ближайшей синхронизации |
| `parsing_nspd/` | 8 (1 в репо, 7 dev-стенд) | оставляем у разработчиков |
| `pirushin_sosn_rocha/` | 13 (5 скриптов 01-05 мигрированы в `egrn_parser`; 4 MD уже в `shared/*` ветках) | без изменений |
| `parser_checko_ru/` | 6 (1945+500+272+193+1216+122 строк, ENTIRELY NEW) | ADR-002: отложенная интеграция (вариант B) |

## Ключевая находка: `parser_checko_ru`

- Клиент checko.ru + dadata.ru + НПД ФНС (statusnpd.nalog.ru).
- SQLite-кэш `innogrn.db` v8.2: vendors, subjects (с branches via `is_branch`), founders, OKVED, special_regime.
- Multi-vendor pipeline architecture (vendor_id FK на каждой записи).
- Полный FastAPI-гайд (`INTEGRATION.md` 1216 строк) для будущего переноса в production-стек.

**Точки пересечения с ekcelo:**
1. `entity_registry` (ЕГРН) ↔ `subjects` (checko) — дублирование данных по юрлицам.
2. `object_etp_profile.legal_extra` — checko даёт ОКВЭДы / статус / форму собственности.
3. Orchestrator SSOT `EgrnLayer.tables.entity_registry` — opt-in обогащение.

## Решение (ADR-002)

**Отложенная интеграция (вариант B).** Orchestrator MVP сейчас не блокируется новым модулем. `parser_checko_ru` остаётся standalone у разработчиков; ekcelo может читать выходные JSON / `innogrn.db` opt-in через адаптер, когда понадобится.

**Триггеры для cycle 3-4:**
- Orchestrator MVP merged + работает на реальном лоте → `feat/parser-checko-integration`.
- Экономист хочет автоматическое обогащение `object_etp_profile.legal_extra` при ETL-OSV → `parser/exporters/etp/etl_checko.py`.

## Артефакты

- `obsidian/Architecture/parallel-parsers-map.md` — карта 4 модулей + что в репо, что нет, чьё что.
- `obsidian/Decisions/ADR-002-parser-checko-integration-policy.md` — решение + триггеры будущих циклов.
- `obsidian/Changelog/2026-05-30-parser4-zip-inventory.md` — этот файл.

## Дальше

Orchestrator MVP (cycle 4) — теперь с пониманием, что:
- `EgrnLayer.tables` оставляем `dict[str, Any]` (гибкий контейнер под произвольные таблицы).
- В `inputs_finder` есть будущий слот под `innogrn.db` / `LEGAL_*.json` / `IP_*.json` / `PERSON_*.json`.
- Pydantic-схемы НЕ требуют checko-полей в MVP.

Параллельно по согласованию с пользователем — orchestrator-frontend и orchestrator-backend на отдельных ветках (`orchestrator/frontend`, `orchestrator/backend`).
