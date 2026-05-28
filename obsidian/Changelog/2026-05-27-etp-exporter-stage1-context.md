# 2026-05-27 — ЭТП-экспортёр Stage 1: build_lot_context

## Итог
Каркас экспортёра в `parser/exporters/etp/` и первая функция `build_lot_context(conn, lot_id)` — читает БД (миграция 0001) и собирает ctx dict по SPEC §3 для одного лота.

## Артефакты
- `parser/exporters/__init__.py` — namespace.
- `parser/exporters/etp/__init__.py` — экспортирует `build_lot_context`.
- `parser/exporters/etp/build_lot_context.py` — загрузчики из БД + сборщики 7 секций ctx (meta / identity / location / building / layout_and_condition / legal / risks / extras).
- `parser/tests/test_build_lot_context.py` — 15 тестов.

## Поведение
- `target_cad_number` опционально (по умолчанию `lots.primary_cad_number`).
- Multi-cad лоты: ctx строится для primary КН; остальные КН лота упоминаются в `extras.notes`.
- Земельные участки: `building` и `layout_and_condition` возвращают `{}`, `area_land_sqm` заполнен.
- Помещения / квартиры: `area_total_sqm` + `floor`; `floors_total` только у зданий.
- Объекты с `profile.source='llm', confidence<0.5` и пустыми JSON-полями: соответствующие секции ctx пустые.
- Ошибки: `LookupError` на несуществующий `lot_id`; `ValueError` если у лота нет ни `primary_cad_number`, ни items.

## Известные гэпы (закроются в следующих PR)
- `location.region/.../room` (компонентный адрес) — None. Нужен `address_parser.py`.
- `legal.use_type_permitted` — None. Нужен NSPD enrichment.
- `legal.encumbrances[].influence` — None. Нужен `encumbrance_mapper.py` с маппингом типа→текст.
- `building.building_type, year_built` — None. Нужен NSPD/EXIF enrichment.

## Тесты (15/15 pass)
- ctx содержит 9 секций по SPEC §3.
- meta переносит `platform` / `platform_mode` / `procedure_type` / `deal_type` / `locale`.
- Identity корректна для room (case A) и land (case C).
- Location использует `location_extra` из профиля, address_raw из ЕГРН.
- Building/Layout пусты для земли и low-confidence профиля.
- Legal: право собственности из ЕГРН + zoning из профиля + encumbrances из object_restrictions.
- Risks passthrough из профиля.
- Extras.notes для multi-cad лотов перечисляет остальные КН.
- LookupError на unknown lot; ValueError на пустой лот.

## Следующий шаг (Stage 2)
`text_render.py` — Jinja-движок (импортирует `torgi_long_description.j2` из `docs/etp_export/05_*.md`) + 6 golden-файлов (3 платформы × 2 mode).
