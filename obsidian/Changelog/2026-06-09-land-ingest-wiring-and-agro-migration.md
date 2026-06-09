# 2026-06-09 — Подключение МКУ/ЕЗП к ingest + миграция агро-слоя

Две задачи по плану: (#1) замкнуть ADR-005 ingest→БД, (#2) миграция ADR-006 §I.

## #1 — МКУ/ЕЗП → ingest (ADR-005, end-to-end)
Раньше `upsert_geometry_contours`/`upsert_land_extract` существовали, но в потоке
не вызывались. Добавлен мост:
- **`egrn_parser/parsers/land_ingest.py`** (новый, слой склейки):
  - `ingest_sidecar_contours(conn, sidecar)` — `_data/contours.json` (вывод 01b) →
    `land_contours`. Берёт `payload["geojson"]` (WGS84, WFS/PKK), классифицирует
    ЗУ/МКУ по числу полигонов. Объекты без geojson (screenshot_cv) — пропускает.
    Известный ЕЗП не понижается.
  - `ingest_land_extract_text(conn, text)` — текст выписки → ЕЗП/ЗУ/МКУ + контуры
    (дочерние КН для ЕЗП).
- **`scripts/01c_contours_to_db.py`** (новый CLI): `--project --db [--dry-run]`,
  читает sidecar → пишет в БД, печатает сводку (cad/layout/контуров).
- **`tests/test_land_ingest.py`** (+5): МКУ+ЗУ из sidecar, пропуск без geojson,
  идемпотентность, ЕЗП из текста, ЕЗП-не-понижается-геометрией.

Поток теперь: `01_parsing_nspd_v8` → `01b_ingest_contours` (sidecar) →
**`01c_contours_to_db`** (land_contours), либо текст выписки →
`ingest_land_extract_text`.

## #2 — Миграция `0005_agro_layer.sql` (ADR-006 §A/C/H/I)
- `agro_parcel` (§A) — поле-снимок на сезон (геометрия/площадь/код, мягкая
  привязка к земле).
- `agro_crop_cycle` (§I) — цикл sow→harvest; `season_year`=год уборки;
  `cycle_kind (winter|spring|perennial)`; план/факт строками `crop_status` +
  датировка §F (`valid_from`/`valid_to`/`known_from`).
- `agro_event` (§C) — лог событий (harvest|treatment|…); `cycle_id` (§I),
  `asset_id` (§G техника из ОСВ), показатели в JSON `attrs`.
- `agro_attribute_dict` (§C/§H) — словарь признаков + стартовые 5 строк (§H).
- Smoke-валидация: миграция исполнима (после 0003); озимая plan→fact + событие
  боронования на plan-цикл записываются корректно.

## Тесты
`pytest tests/test_land_ingest.py tests/test_land_db.py tests/test_land_layout.py`
→ **22 passed**. (Прочие модули падают на сборе из-за отсутствующих в среде
зависимостей — playwright/pymorphy3 — не связано с правками.)

## Файлы
- `parser/egrn_parser/parsers/land_ingest.py` (новый)
- `parser/scripts/01c_contours_to_db.py` (новый)
- `parser/tests/test_land_ingest.py` (новый)
- `schema/migrations/0005_agro_layer.sql` (новый)

## Дальше
- Заблокировано образцом техкарты: парсер техкарты → `agro_parcel`+`agro_crop_cycle`
  +`agro_event`; JSON-схемы профилей `attrs`; вьюхи-агрегаты (урожай по
  сортам/датам, пест. нагрузка, техсхема лота).
