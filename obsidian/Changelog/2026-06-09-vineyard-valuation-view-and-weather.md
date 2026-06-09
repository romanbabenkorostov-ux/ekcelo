# 2026-06-09 — Оценочная вьюха винограда + накопленная погода (Open-Meteo)

Два трека по ADR-006 §J (ценообразующий профиль насаждения на контуре ЗУ).

## Оценочная вьюха винограда (задача 2)
- **Миграция `0009_vineyard_valuation.sql`** + `agro_reports.vineyard_valuation`:
  вьюха `v_vineyard_valuation` собирает по насаждению —
  - контур ЗУ (`land_contours` по `land_cad`): Σ площадь, центроид (геоточка);
  - насаждение (`agro_parcel`/`agro_crop_cycle`): сорт, год высадки, **возраст**
    (`strftime('%Y','now') − год`), площадь, кусты, фед.реестр, подвой (из attrs);
  - уход (`agro_event`): число операций и обработок.
- `ensure_valuation_view` создаёт `land_contours` при отсутствии (работает без земли).

## Накопленная погода по геоточке (задача 3)
- **`weather_open_meteo.py`** — бесплатный **Open-Meteo Archive** (без ключа):
  - `build_archive_url`/`fetch_archive` (сеть) — daily: t max/min/mean,
    осадки, суммарная радиация (МДж/м²), ветер, порывы;
  - `parse_daily` (ответ → по дням), `accumulate` (GDD база 10°C, Σ осадки,
    Σ радиация, max ветра/порывов, средняя t, n дней) — чистые, офлайн;
  - `accumulated_since_planting(lat, lon, planting_year)` — агрегат с
    `{год}-01-01` по сегодня (геоточка = центроид контура из оценочной вьюхи).
- Сеть среды наружу закрыта → fetch отделён от parse; parse+accumulate тестируются
  на сохранённом JSON (`fixtures/weather/open_meteo_archive_sample.json`).

## Связь (ADR-006 §J)
Оценочная вьюха даёт геоточку насаждения → погодный парсер считает накопленные
условия с момента посадки. Вместе: контур(земля) × насаждение(сорт/возраст/кусты)
× уход × погода — ценообразующий профиль (урожай/почва — следующие слои).

## Тесты
- `tests/test_weather_open_meteo.py` (+5): url, parse, accumulate (GDD=41.9,
  осадки=17.5, радиация=74.1, max ветра/порывов), fallback mean из min/max, пусто.
- `tests/test_vineyard_valuation.py` (+2): сбор земля×насаждение×уход; без контура.
- Полный агро+земля+погода → **71 passed**.

## Файлы
- `parser/egrn_parser/parsers/weather_open_meteo.py` (новый)
- `parser/egrn_parser/parsers/agro_reports.py` (+оценочная вьюха)
- `schema/migrations/0009_vineyard_valuation.sql` (новый)
- `parser/tests/test_weather_open_meteo.py`, `parser/tests/test_vineyard_valuation.py` (новые)
- `parser/tests/fixtures/weather/open_meteo_archive_sample.json` (образец)
- `docs/specs/SPEC_parser.md`, `obsidian/Architecture/roadmap-land-agro-graph.md`
