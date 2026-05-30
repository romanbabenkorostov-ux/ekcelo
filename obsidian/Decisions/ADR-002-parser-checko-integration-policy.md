# ADR-002: Политика интеграции `parser_checko_ru`

**Статус:** Accepted · **Дата:** 2026-05-30 · **Автор:** parser-team
**Связанные:** [[parallel-parsers-map]], [[orchestrator_spec|obsidian/Prompts/llm_memorandum_pipeline/orchestrator_spec.md]], [[ADR-001-etp-profile-extension]]

## Контекст

Команда parser поставила (zip 2026-05-30) новый модуль `parser_checko_ru`:

- Клиент checko.ru API + НПД ФНС + dadata.ru.
- SQLite-кэш `innogrn.db` со схемой v8.2 (vendors, subjects с branches через `is_branch`, founders, OKVED, special_regime).
- Гайд интеграции в FastAPI + Alembic + Postgres (`INTEGRATION.md`, 1216 строк).
- ~2.5K строк кода (Python + SQL + MD).

Точки пересечения с ekcelo:
1. `entity_registry` в `parser/egrn_parser/db/schema.sql` (ИНН/ОГРН/название/тип) — checko может быть источником истины.
2. `object_etp_profile.legal_extra` — checko даёт ОКВЭДы / статус юрлица / форму собственности.
3. Orchestrator SSOT `EgrnLayer.tables.entity_registry` — checko-обогащение перед сборкой ctx.

## Развилка

A. **Немедленная интеграция** — внести `parser/parser_checko_ru/` в `main`, добавить deps (`requests`, `python-dotenv`), вызывать из Orchestrator Фазы 1.
B. **Отложенная интеграция** — оставить checko у разработчиков, читать его выход (`innogrn.db`) opt-in'ом через адаптер, когда понадобится.
C. **Не интегрировать** — checko живёт отдельным сервисом, ekcelo читает его только через JSON-выгрузки.

## Решение

**Принят вариант B (отложенная интеграция).**

### Причины

1. **Orchestrator MVP cycle открыт** (см. PR #84 → следующий цикл). Внесение `parser_checko_ru` сейчас ломает scope и добавит ещё ~2.5K строк к review.
2. **Внешние API-ключи** (`CHECKO_API_KEY`, `DADATA_API_KEY`, `DADATA_SECRET_KEY`) — это secrets. До интеграции нужен secret-management контракт (env-only, `.env.example`, CI-secrets).
3. **БД-сопряжение нетривиально**: `innogrn.db` — отдельная SQLite со своей schema; интеграция с ekcelo требует FK-моста или ETL-выгрузки. ADR-001 фиксирует «БД = слепок ЕГРН + ЭТП-профиль», checko-данные туда не входят без отдельного решения.
4. **Скрипт уже даёт JSON** (`LEGAL_*.json`, `IP_*.json`, `PERSON_*.json`) и SQLite-выгрузку. Orchestrator может читать их как один из источников SSOT (Фаза 1, `inputs_finder.find_recursive`), не вызывая API сам.

### Что делаем сейчас

- В Orchestrator MVP `EgrnLayer.tables` — `dict[str, Any]`, открыт под произвольные таблицы. Если экономист положит `innogrn.db` или JSON в `Memorandum/_data/`, Pydantic-схема валидирует, но НЕ требует поля checko.
- Документация (`parallel-parsers-map.md`, эта ADR) фиксирует существование модуля и роль.
- НЕ копируем `parser_checko_ru/` в `parser/` репо.
- НЕ добавляем `requests` / `python-dotenv` в `parser/pyproject.toml` ради checko.

### Что делаем позже (триггеры для cycle 3-4)

| Триггер | Действие |
|---|---|
| Orchestrator MVP merged + работает на ≥1 реальном лоте | Открыть отдельный cycle: `feat/parser-checko-integration` |
| Появилась потребность: «экономист хочет, чтобы при ETL-OSV checko-данные подтягивались автоматически» | Адаптер `parser/exporters/etp/etl_checko.py` — читает `innogrn.db` (если есть) и пишет в `object_etp_profile.legal_extra` с `source='checko'`, `confidence=0.9` |
| Появилась потребность: «orchestrator должен дёргать checko если ИНН не в кэше» | Внести `parser/parser_checko_ru/` через `pip install -e parser/parser_checko_ru/` (pyproject там уже есть) + добавить `[checko]` extras в основной pyproject |

## Последствия

- ✅ Orchestrator MVP не блокируется новым модулем.
- ✅ `parser_checko_ru` остаётся standalone, может развиваться независимо.
- ⚠️ Дублирование данных по юрлицам: `entity_registry` (ЕГРН) vs `subjects` (checko). Mitigation — при cycle 3 интеграции вводится приоритет источников по `source` field (как у `object_etp_profile`).
- ⚠️ Если другой потребитель внутри ekcelo захочет checko-данные раньше cycle 3 — нужен ad-hoc файл-обмен (выгрузка JSON в `Memorandum/_data/`).

## Альтернативы (rejected)

- **A (немедленно)** — раздувает текущий cycle, тянет secrets-management до того, как они нужны.
- **C (никогда)** — checko уже даёт ценность (status юрлица, ОКВЭДы, цепочки founder'ов). Полный отказ — потеря данных.
