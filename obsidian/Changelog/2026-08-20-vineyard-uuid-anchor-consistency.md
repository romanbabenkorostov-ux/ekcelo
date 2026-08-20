# 2026-08-20 — Виноградники/wel-card: находка несоответствий + фикс якоря

## Задача
По запросу пользователя (§4 плана ekcelofotomobile, `brwf`) — просмотреть
идентификацию виноградников в `wel-card`/`VineInvent`, обеспечить
консистентность форматов данных, если уместно. `wel-card` (сам реестр) в
этой сессии не подключён — работа только по тому, что раскрывают
`VineInvent`/`iarobo-welcard`/`ekcelo-site`/`ekcelo` о его контракте.

## Что нашли
Разведка (агент-исследователь + ручная проверка кода) вскрыла три
несоответствия — см. `contracts/format/BRWF_REGISTRY.md`, раздел
«Известные несоответствия идентичности (uuid7) в семье»:
1. `vineyards`/`vineyard_plots`/`land_parcels` в `VineInvent` минтились
   через `gen_uuid7()` в обход якоря `core.uuid_anchor` — в отличие от
   `sites` (тот же класс сущностей), защиты от задвоения не было вовсе.
2. `ekcelo.geo_entity.geo_uuid` генерируется как uuid**4**
   (`backend/app/services/geo.py`), расходится с остальной семьёй
   (uuid7 везде, включая якорь VineInvent).
3. `brwf:3.x` (origin=3, VineInvent) зарезервирован, но ни разу не
   использован — ожидаемо, версия формата данных, а не идентичности.

## Что сделано
Пользователь выбрал: зафиксировать находку в реестре (сделано, см. выше)
**и** расширить якорь VineInvent (сделано) — находку №2 (uuid4 в
`geo_entity`) осознанно НЕ трогали: архитектурное решение отдельного
блаcт-радиуса (production PK backend), не относится напрямую к запросу.

В `VineInvent` (отдельный репозиторий, тот же push):
- `sql/56_uuid_anchor_vineyard.sql` — CHECK `entity_kind` якоря +
  `'vineyard'|'vineyard_plot'|'land_parcel'` (тот же приём пересоздания
  таблицы, что sql/44/sql/55).
- `core/uuid_anchor.py:ENTITY_KINDS` — три новых вида + попутно найденный
  и исправленный пропуск `'measurement'` (был в CHECK с sql/55, отсутствовал
  в python-списке).
- `etl/backfill_uuid_anchor.py` — регистрирует существующие
  `vineyard_id`/`plot_id`/`land_parcel_id`, там где org уже известна
  (`owner_org_id`/`org_id IS NOT NULL` — тот же неполный охват, что уже
  принят для `sites`).

## Как проверялось
Полная копия `VineInvent` (репозиторий + БД) в scratch — не трогая
рабочую базу: `etl/migrate.py --db assets.db` накатил 56-ю миграцию
чисто, `etl/backfill_uuid_anchor.py` (dry-run → реальный прогон →
повторный прогон) зарегистрировал 33 `vineyard` + 125 `vineyard_plot`
(0 `land_parcel` — сверено отдельным запросом: ни у одной из 67 строк
`land_parcels` `owner_org_id` пока не заполнен, это правда, не баг),
повторный прогон — идемпотентно, 0 новых записей. `pytest
tests/test_uuid_anchor.py tests/test_migrate.py` — 28/28 зелёных, без
регрессий.

## Канал доставки
`ekcelo`: git push на `claude/ekcelofotomobile-folders-packages-4tryj0`
(этот файл + `contracts/format/BRWF_REGISTRY.md`).
`VineInvent`: git push на ту же ветку, отдельный репозиторий.
