# 2026-06-08 — Заглушка техкарты (ТЗ) + детектор ЗУ/ЕЗП/МКУ

## Суть
ЮНИКРЕДИТ-прогон подтвердил PDF-фикс (директор + иностр. акционер легли в БД).
Дальше: заглушка парсера техкарты с ТЗ (образец — техдолг заказчика) и реализация
шага 1 ADR-005 (детект представления земли).

## Сделано
- **Заглушка техкарты** `egrn_parser/parsers/agro_techcard.py`: `parse_techcard`
  бросает NotImplementedError с пояснением; docstring = ТЗ (вход/выход
  `{parcels[], events[]}`, ADR-006). Полное ТЗ — `fixtures/agro/TZ_techcard.md`
  (ожидаемые колонки техкарты, профили событий, единицы, идемпотентность).
- **Детектор ЗУ/ЕЗП/МКУ** `egrn_parser/parsers/land_layout.py` (ADR-005 шаг 1):
  `detect_land_layout` (маркер «Единое землепользование» / дочерние КН → ЕЗП;
  ≥2 контуров без дочерних → МКУ; иначе ЗУ) + `detect_from_land_object`
  (по land_objects-dict / GeoJSON). Тесты `tests/test_land_layout.py` (7/7).
- SPEC_parser: трек 11 (детект land_layout ✅), трек 12 (fixed_asset ✅,
  техкарта — заглушка).

## Файлы под нож
- `parser/egrn_parser/parsers/agro_techcard.py` (заглушка+ТЗ)
- `parser/egrn_parser/parsers/land_layout.py` (новый)
- `parser/tests/test_land_layout.py` (новый)
- `fixtures/agro/TZ_techcard.md` (ТЗ)
- `docs/specs/SPEC_parser.md` (треки 11-12)

## Дальше по плану (ADR-005)
- `land_layout_type` в land_objects + миграция `land_contours`/`contour_tech_profile`.
- Backfill контуров из object_geometries/contours.json; связи `linked_objects`.
- Реализацию земель/контуров согласовать с граф-схемой соседнего чата (contracts/db).

## От заказчика
Образец техкарты (техдолг) → снять заглушку `agro_techcard`. Подтвердить
датирование (ADR-006 F) и словарь (H).
