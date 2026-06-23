# ADR-002 — Geo entities (§7) как отдельный bitemporal-слой

**Дата:** 2026-06-23
**Статус:** ✅ Accepted
**Связанные:** ADR-001 (ЭТП-профиль §6 как не-ЕГРН слой).

## Контекст

В БД исторически не было геометрии — координаты жили только в KMZ-артефактах
(parser → KMZ → frontend). Появилась задача: «геосущность контур и/или
точка служит для привязки активов, может изменяться во времени». То есть
нужно ввести БД-сторонний источник для:

- центров и контуров (для backend ViewModel.geo, как-если-API-режим);
- истории изменений (территория переразмечена → надо помнить как было);
- M:N (один актив → несколько точек/контуров с разными ролями: основная
  привязка, точка доступа, ссылочная).

Вариант «закатать lat/lon в `objects.lat/lon`» не подходит: (а) у одного
актива могут быть несколько разных точек; (б) теряется история; (в) КМ
выходит из под доктрины «БД = слепок ЕГРН» — но геометрия не из ЕГРН.

## Решение

Создан **§7 «Geo entities»** — отдельный не-ЕГРН слой (как §6 ЭТП-профиль).
Четыре таблицы:

- `geo_entity(geo_uuid PK, name, source, confidence, created_at)`
- `geo_entity_contour(contour_id PK, geo_uuid FK, geometry GeoJSON, valid_from, valid_to, recorded_at, source, confidence)`
- `geo_entity_point(point_id PK, geo_uuid FK, lat, lon, valid_from, valid_to, recorded_at, source, confidence)`
- `asset_geo_link(link_id PK, asset_type, asset_id, geo_uuid FK, role, valid_from, valid_to, recorded_at, source)`

### Принятые опции

| Решение | Выбрано | Альтернатива |
|---|---|---|
| Привязка актив↔geo | **M:N + история** (`asset_geo_link` с valid_from/to + role) | FK-колонка `geo_uuid` в `objects`/`lots` |
| Модель валидности | **Bitemporal** (valid_from/to + recorded_at) | Только valid_from |
| Формат геометрии | **GeoJSON Geometry** в TEXT | WKT / отдельные lat/lon-колонки |
| СК | **WGS84** (lon/lat в EPSG:4326) | — |
| `restorable` | **false** (как §6) | true |
| `ON DELETE` для geo_entity | **CASCADE** для contour/point, **RESTRICT** для asset_geo_link | CASCADE везде |

### Почему M:N + история

- Один актив может иметь несколько geo с разными ролями (на голосование
  выбран этот вариант).
- Привязка сама может меняться во времени (актив перенесён в другую
  гео-сущность, например при переразметке) — поэтому `valid_from/to` в самой
  таблице связи, а не только в записях контура/точки.

### Почему bitemporal (а не только valid_from)

- `recorded_at` ничего не стоит (default `datetime('now')`).
- Совместимость с roadmap parser-A v2 (post 020 — bitemporal ownership).
- При появлении ретро-аналитики «что мы знали в день Y про состояние в день X»
  ничего не надо мигрировать.

### Почему GeoJSON в TEXT

- Прямо ложится на `ViewModel.geo.geometry` (C4 REST) — без перепаковки.
- Не требует SpatiaLite / расширений SQLite.
- Объёмы данных небольшие (сотни–тысячи геосущностей в проде).
- Если позже понадобится R-Tree — добавим виртуальную таблицу-индекс, не
  меняя текущую.

### Почему restorable=false

§7 не строится из ЕГРН-выписок. Источники: KMZ (parser), NSPD-gap-fill,
ручная разметка экономиста, EXIF фото. При полной пересборке БД из ЕГРН §7
сохраняется (как §6).

### Почему RESTRICT на asset_geo_link.geo_uuid

Защита целостности: пока есть линк, удаление гео-сущности — операционная
ошибка. Контур/точку можно удалить через cascade, потому что они — история
самой сущности.

## Последствия

### Положительные
- Бэкенд теперь может отдавать `ViewModel.geo` независимо от KMZ.
- История переразметок сохраняется автоматически.
- Frontend (FE) не правится — то же место под geo в ViewModel.
- Контракт C2 расширен §7; валидатор учит §7 как опциональный (как §6).
- 19 новых тестов покрывают запись/чтение/инварианты.

### Цена
- 4 таблицы вместо 0.
- При импорте KMZ — больше операций записи (но это одноразовое).
- Helper-слой `backend/app/services/geo.py` — ~190 строк.

### Не решено в этом ADR
- Политика «закрывать старую запись или нет» при новой версии контура.
  Сейчас append-only; явное закрытие — когда придёт parser-A v2 или
  аналитика интервалов.
- Spatial-индексирование (R-Tree / SpatiaLite). Включать когда выборка
  начнёт тормозить.
- WKT-экспорт (нужен для интеграций с GIS-инструментами).

## Артефакты

- Миграция: `schema/migrations/0003_geo_entities.sql`
- Mirror в base schema: `schema/egrn_current_schema.sql` §7
- C2 контракт: `contracts/bundle-db-slice/schema.json` (+4 таблицы)
- Helper: `backend/app/services/geo.py`
- Тесты: `backend/tests/test_geo.py` (19)
- Обзор: `obsidian/Database/geo-entities-7.md` (ER, workflow)
- Apply CLI: `python -m parser.exporters.etp.init_db_cli` (applies 0003)
