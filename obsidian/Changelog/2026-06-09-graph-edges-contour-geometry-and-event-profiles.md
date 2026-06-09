# 2026-06-09 — B/C/D: рёбра графа, площадь/центроид контуров, профили agro_event

Три задачи разработки (A — парсер техкарты — в техдолге, ждёт образец).

## B. Рёбра/узлы граф-слоя из land_contours (GRAPH_SCHEMA)
- `land_db.land_graph_edges(conn)` — рёбра: `land_<parent>` → `contour_<parent>_<no>`,
  тип `ezp_child` (contour_cad заполнен) / `mku_contour` (NULL).
- Миграция `0006_land_graph_edges.sql`: вьюхи `v_land_graph_edges` (рёбра) и
  `v_land_graph_nodes` (`graph_node_id`=`contour_<parent>_<no>` + площадь/центроид).
- Граф = логический (вьюхи поверх таблиц), отдельный движок не вводится.

## C. Площадь/центроид контуров в БД
- `land_layout.polygon_area_centroid(polygon_coords)` — площадь (внешнее кольцо −
  дыры) + центроид через локальную равноугольную проекцию (та же математика, что
  в NSPD-парсере v8).
- `split_geometry_contours` обогащает каждый контур `area_sqm`/`centroid_lon`/
  `centroid_lat`/`geom_source`. `upsert_contours` пишет их (и обновляет центроиды
  при пере-ingest — добавлено в ON CONFLICT).

## D. JSON-профили `agro_event.attrs` + валидатор (ADR-006 §C)
- `agro_event_profiles.py`: профили harvest/treatment/observation/phenology/sowing
  (required + типы полей); `validate_event_attrs(event_type, attrs) -> [errors]`,
  `is_valid_event`. Без внешних зависимостей. Неизвестные ключи допускаются
  (модель events+JSON расширяема). `active_substances[]` валидируется поэлементно.

## Тесты
- `tests/test_land_graph_and_geometry.py` (+14): площадь/центроид (квадрат, дыра),
  обогащение split, запись area в БД, рёбра МКУ/ЕЗП, вьюхи миграции 0006,
  профили событий (валид/невалид/типы/substances/unknown/JSON-строка).
- `pytest tests/test_land_*.py` → **36 passed**.

## Docs
- SPEC §11 (рёбра+площадь ✅), §12 (профили событий ✅, техкарта → техдолг).
- GRAPH_SCHEMA — раздел «Уже реализовано» дополнен рёбрами/площадью.

## Файлы
- `parser/egrn_parser/parsers/land_layout.py` (геометрия: area/centroid + enrich)
- `parser/egrn_parser/parsers/land_db.py` (`land_graph_edges` + centroid в ON CONFLICT)
- `parser/egrn_parser/parsers/agro_event_profiles.py` (новый)
- `parser/tests/test_land_graph_and_geometry.py` (новый)
- `schema/migrations/0006_land_graph_edges.sql` (новый)
- `docs/specs/SPEC_parser.md`, `docs/specs/GRAPH_SCHEMA_land_and_entities.md`

## Техдолг
- **A. Парсер техкарты** → `agro_parcel`/`agro_crop_cycle`/`agro_event` (ждёт
  обезличенный образец техкарты в `fixtures/agro/`).
- **E. Агрегаты-вьюхи агро** (после A): урожай по сортам/датам, пест. нагрузка.
