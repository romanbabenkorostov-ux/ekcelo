# Аспекты выписки ЕГРН → проверка схемы C2

> Систематизация состава выписки (Приказ Росреестра П/0329 от 04.09.2020) по
> приложенному образцу `extract_about_property_room` + land-форме, и сверка покрытия
> схемой C2. Дата: 2026-06-05.

## Аспект → раздел выписки → таблица/поле C2 → статус

| Аспект | Поля выписки (XML) | C2 | Статус |
|--------|--------------------|----|--------|
| Реквизиты выписки | `organ_registr_rights`, `date_formation`, `registration_number` | `extracts(extract_number, extract_date, document_type)` | ✅ (орган — не хранится, minor) |
| Идентификация | `cad_number`, `type` | `objects.cad_number`, `object_type` | ✅ |
| Квартал | `quarter_cad_number` | — | ❌ gap |
| Старые номера | `old_numbers` (условный/инвентарный) | — | ❌ gap |
| Связь объектов | `cad_links.parent_cad_number` | `relations[spatial/CONTAINS]` | ✅ (как ребро); поле — ❌ в `objects` |
| Характеристики | `area`, `permitted_uses`, `purpose`, `name` | `objects.area/permitted_use/purpose` + `entities.label` | ✅ |
| Этаж (помещение) | `location_in_build.level.floor` | — (`objects.floors` ≠ `floor`) | ❌ gap |
| Адрес (читаемый) | `readable_address` | `objects.address` | ✅ |
| Адрес (структ.) | `okato`, `kladr`, `fias`, `region` | — | ❌ gap |
| Кадастровая стоимость | `cost.value` | — | ❌ gap |
| Права | `right_type`, `right_number`, holder `name/inn/ogrn` | `rights` + `relations[legal]` + `subjects` | ✅ |
| Контакты правообладателя | `email`, `mailing_addess` | — | ❌ gap |
| Ограничения | `restrictions` (ЗОУИТ/ОКН), `special_notes` | `object_restrictions` | ✅ |
| Геометрия/контур | координаты (land/контур) | `geometries` (WKT/GeoJSON, МСК→4326) | ✅ |
| Статус сведений | `status` («актуальные, ранее учтённые») | — | ❌ gap (`status_egrn`) |

## Вывод
Граф/права/геометрия/ограничения — **покрыты**. Пробелы — в §1 `objects` (атрибутивные
поля, которые парсер уже извлекает, но C2-`objects` не хранит). Совпадает с
`SCHEMA_SPEC §8 DIFF`.

## Рекомендация — миграция `0004` (расширение `objects` + контакты)
Добавить в `objects`: `quarter_cad_number`, `inventory_number`, `conditional_number`,
`parent_cad_number`, `cadastral_value`, `floor`, `okato`, `kladr`, `fias_guid`,
`status_egrn`. Контакты правообладателя (`email`, `mailing_address`) → в
`legal_relation` или `subjects`. Все поля nullable; импортёр Block-2 заполнит из
`land_objects`/`building_objects` (они эти поля уже содержат — см. schema.sql).

> Это аддитивная миграция (без потери данных). Делать после согласования —
> синхронно обновить `import_block2` (маппинг новых полей).
