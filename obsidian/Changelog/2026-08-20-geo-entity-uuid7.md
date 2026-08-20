# 2026-08-20 — `geo_entity.geo_uuid`: uuid4 → uuid7

## Задача
Найдено при разведке виноградников/wel-card (см.
`2026-08-20-vineyard-uuid-anchor-consistency.md`,
`contracts/format/BRWF_REGISTRY.md`): `geo_entity.geo_uuid` минтился как
uuid4 (`backend/app/services/geo.py`), расходясь с остальной семьёй
(assets, sites, якорь VineInvent — везде uuid7). По прямому запросу
пользователя — исправлено.

## Что сделано
- `backend/app/core/uuid7.py` (новый) — тот же алгоритм, что
  `gen_uuid7()` в EkceloFotoMakeInvent/VineInvent (`etl/uuid7.py`):
  UUIDv7 по RFC 9562, монотонный внутри миллисекунды через 12-битный
  счётчик. Скопирован, не вынесен в общую зависимость — разные
  репозитории с разным циклом релиза, тот же приём, что уже применён в
  VineInvent (`etl/uuid7.py`'s docstring прямо это объясняет).
- `backend/app/services/geo.py:register_geo` — `uid = geo_uuid or
  gen_uuid7()` вместо `str(uuid.uuid4())`.
- `schema/migrations/0003_geo_entities.sql` — комментарий у колонки
  исправлен (был "UUIDv4", схема не менялась — колонка всегда была
  просто `TEXT`, миграция не нужна).
- `backend/tests/test_geo.py` — новый тест
  `test_register_geo_generates_uuid7_not_uuid4` (парсит сгенерированный
  uuid, проверяет `.version == 7`).

## Осознанно НЕ сделано
**Существующие `geo_uuid` не переписаны.** Та же политика, что уже
принята в семье (VineInvent `sql/37`: "переписать выданный идентификатор
значит сломать ссылки, ушедшие наружу") — старые uuid4-значения остаются
валидными PK навсегда, только НОВЫЕ записи с этого коммита получают
uuid7. `geo_entity` в базе теперь смешанная (uuid4 + uuid7) по дизайну,
не по недосмотру — колонка это позволяет (просто `TEXT PRIMARY KEY`, без
формат-проверки).

## Как проверялось
`pip install pydantic fastapi` (отсутствовали в окружении) +
`pytest backend/tests/` — 155/157 зелёных (`test_geo.py` — 20/20,
включая новый тест); 2 непройденных — `_cffi_backend` для
auth-модуля `lot_orchestrator_web`, окружение, не связано с этой
правкой.

## Канал доставки
git push на `claude/ekcelofotomobile-folders-packages-4tryj0`.
