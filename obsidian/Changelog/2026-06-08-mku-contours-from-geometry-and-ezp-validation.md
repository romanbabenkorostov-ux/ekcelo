# 2026-06-08 — МКУ-контуры из геометрии + валидация на ЕЗП 23:15:0804000:51

## Что сделано
- **МКУ-контуры из геометрии** (следующий шаг ADR-005):
  - `land_layout.split_geometry_contours(geom)` — GeoJSON Polygon/MultiPolygon →
    список контуров (Polygon на полигон, `contour_cad=NULL`).
  - `land_db.upsert_geometry_contours(conn, parent_cad, geom, ...)` —
    классификация (≥2 контуров → МКУ) + запись `land_contours`, идемпотентно
    `(parent_cad, contour_no)`.
- **Защита ЕЗП от понижения геометрией** (выявлено при валидации): геометрия
  многоконтурного ЕЗП — тоже MultiPolygon. Раньше это классифицировалось бы как
  МКУ. Теперь: если объект уже помечен `ЕЗП` (или `layout='ЕЗП'` передан явно) —
  раскладка сохраняется, NULL-cad контуры геометрии не пишутся (геометрия ЕЗП
  привязывается к дочерним КН отдельно). Дочерние КН контуров не затираются.

## Валидация парсера НСПД на ЕЗП 23:15:0804000:51
- Живой запрос к `nspd.gov.ru`/`pkk.rosreestr.ru` невозможен — host not in
  allowlist (сетевая политика среды). Валидация — кросс-консистентностью кода.
- Синтетический ЕЗП (3 обособленных контура) прогнан через **офлайн-ядро
  НСПД-парсера** `01_parsing_nspd_v8.py::_geojson_to_local_meters` и через новый
  `split_geometry_contours`:
  - НСПД: `тип=MultiPolygon`, полигонов=**3**, S=2 587 242.54 м².
  - split: контуров=**3** (все Polygon). **Число контуров совпало ✅**.
- `parse_land_extract` по тексту выписки с маркером «Единое землепользование» и
  списком дочерних → `layout=ЕЗП`, children=3 (классификация по КН, не по
  геометрии).
- ЕЗП-защита: подача MultiPolygon-геометрии не понизила `ЕЗП`→`МКУ`; дочерние КН
  контуров целы.
- Контраст: тот же MultiPolygon без ЕЗП-маркера → `layout=МКУ`, 3 контура NULL-cad.

## Тесты
- `tests/test_land_db.py`: +`test_mku_from_geometry`,
  `test_single_polygon_is_zu`, `test_geometry_contours_idempotent`,
  `test_ezp_geometry_not_downgraded_to_mku`, `test_explicit_layout_override`.
- `pytest tests/test_land_db.py tests/test_land_layout.py` → **17 passed**.

## ADR-006 §I (датирование, докручено и решено)
Добавлен раздел **I. Цикл культуры через сезоны + план/факт** (DECIDED). Озимая
(сев год N → уборка N+1) ломает чистый `season_year`. Решения заказчика:
- **(а) отдельная сущность `agro_crop_cycle`** (sow→harvest); `agro_event.cycle_id`.
  `crop`/`variety`/`lifecycle`/`planting_year` переезжают из `agro_parcel` в цикл.
- **(б) `season_year` = год уборки (N+1)** — ось агрегаций урожая.
- **(в) план≠факт — отдельными строками** `crop_status (plan|fact)` + §F
  (`valid_from`/`valid_to`/`known_from`), без перезаписи истории.
Схема `agro_crop_cycle` добавлена в ADR; план реализации (шаг 2) обновлён.

## Файлы под нож
- `parser/egrn_parser/parsers/land_layout.py` (+`split_geometry_contours`)
- `parser/egrn_parser/parsers/land_db.py` (+`upsert_geometry_contours`, ЕЗП-защита)
- `parser/tests/test_land_db.py` (+5 тестов)
- `obsidian/Decisions/ADR-006-...md` (+§I)
