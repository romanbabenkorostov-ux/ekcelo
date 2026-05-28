# 2026-05-28 — ЭТП-экспортёр: address_parser + encumbrance_mapper

## Итог
Закрыты два гэпа из §10 SPEC: компонентный разбор адреса и человекочитаемый текст влияния обременения. Интегрировано в `build_lot_context`.

## Артефакты
- `parser/exporters/etp/address_parser.py` — `parse_address(raw) → dict` (7 ключей: region, municipality, locality, street, house, building, room).
- `parser/exporters/etp/encumbrance_mapper.py` — `map_encumbrance(restrict_type) → str | None`. 17 канонических типов + substring-fallback.
- `parser/exporters/etp/build_lot_context.py` — интеграция в `_build_location` и `_encumbrance_from_row`.
- `parser/tests/test_address_parser.py` — 12 тестов (федеральные города, регионы с разными суффиксами, дома с буквами/дробями, дисамбигуация «д. 5» vs «д. Иваново»).
- `parser/tests/test_encumbrance_mapper.py` — 14 тестов (известные типы, substring «ипотека в силу закона», case-insensitive).
- `parser/tests/test_build_lot_context.py` — обновлён `test_location_uses_etp_profile_extras` под новые компоненты.
- `parser/tests/golden/etp/caseB_storage_sberbank_ast_ru_full.txt` — регенерирован (добавилось `— не препятствует продаже…` после `ипотека`).

## Что закрыто из §10 SPEC
- ✅ Компонентный адрес (`location.region/.../room`).
- ✅ `legal.encumbrances[].influence` для 17 типов.

## Что осталось из §10
- `building.building_type`, `year_built`, `legal.use_type_permitted` — нужен NSPD-enrichment.
- Грамматические шероховатости Jinja-шаблона.

## Тесты (71/71 pass)
- 12 schema + 15 build_lot_context + 18 text_render + 12 address_parser + 14 encumbrance_mapper.

## Влияние на golden-файлы
Только `caseB_storage_sberbank_ast_ru_full.txt` изменился (+1 строка про влияние ипотеки). Остальные 7 — байт-в-байт идентичны, т.к. адрес case A после компонентного разбора собирается обратно через `full_address` макрос в тот же текст.

## Следующий шаг
NSPD-enrichment (building_type / year_built / use_type_permitted) либо ETL ОСВ → БД.
