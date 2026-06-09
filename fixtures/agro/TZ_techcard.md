# ТЗ — парсер технологической карты (агро) → agro_parcel / agro_event

> Контракт на будущую реализацию `egrn_parser/parsers/agro_techcard.py`
> (сейчас заглушка). Реализуется по получении обезличенного образца техкарты
> в этой папке. Модель — ADR-006.

## Назначение
Техкарта экономиста (Excel/CSV) → нормализованные записи полей и агро-событий
(посадки, обработки, сборы) для §6-слоя (ADR-001: source+confidence, не из ЕГРН).

## Ожидаемый вход (образец — техдолг заказчика)
Поля/участки за сезон, например:
- «Виноград уч.519 "Одесский Чёрный" 2021 г. — 4,06 га»
- «Виноград уч.714 "Мерло" 2022 г. — 11,39 га»

Блоки/листы:
- **Поля:** № участка, культура, сорт, год закладки/посева, площадь (га).
- **Обработки:** дата, препарат, действующие вещества + норма (ед/га), цель, техника.
- **Сборы:** дата, сорт, объём (кг/т), кислотность (г/л), сахар (°Brix), сорт-класс.

## Ожидаемый выход
```json
{
  "parcels": [
    {"parcel_code":"уч.519","season_year":2025,"crop":"виноград",
     "variety":"Одесский Чёрный","lifecycle":"perennial","planting_year":2021,
     "area_ha":4.06,"valid_from":null,"known_from":null}
  ],
  "events": [
    {"parcel_code":"уч.519","season_year":2025,"event_type":"treatment",
     "event_date":"2025-05-12",
     "attrs":{"preparation":"…","active_substances":[{"name":"…","rate":1.2,"unit":"л/га"}]},
     "asset_ref":"Опрыскиватель …"},
    {"parcel_code":"уч.519","season_year":2025,"event_type":"harvest",
     "event_date":"2025-09-20",
     "attrs":{"variety":"Одесский Чёрный","volume_kg":40600,"acidity_g_l":7.2,"sugar_brix":21.5}}
  ]
}
```

## Правила
- `event_type ∈ {harvest, treatment, observation, phenology}`; `attrs` — JSON по профилю.
- Идемпотентность: `parcel` по `(parcel_code, season_year)`; `event` по
  `(parcel_code, event_type, event_date, ключевой attr)`.
- `asset_ref` → связь с `fixed_asset` (ОСВ, ADR-006 §G), если обработка техникой.
- Единицы фиксируются в `agro_attribute_dict` (ADR-006 §H).

## Что нужно от заказчика
1 обезличенный образец техкарты (Excel/CSV) в эту папку → по нему пишутся парсер,
golden-тест и `agro_db.upsert_*` (миграция `0004_agro_layer.sql`).
