# 2026-06-09 — Погода в БД + в оценочной вьюхе винограда (ADR-006 §J)

Достроен профиль §J: к «контур × насаждение × уход» добавлена **погода** (офлайн-пайп
готов; сетевой прогон наполнит реальными числами позже). Карт со сборами/почвы нет —
эти слои ждут источники.

## Реализовано
- **`weather_open_meteo.py`** (+персистентность): `ensure_schema` +
  `store_accumulated(conn, acc, parcel_id=…)` — снимок накопленной погоды на
  насаждение, идемпотентно по `(parcel_id, start, end)`.
- **Миграция `0010_weather_accumulated.sql`:** таблица `weather_accumulated`
  (GDD/осадки/радиация/ветер/порывы/средняя t, период, геоточка, base_temp) +
  пересоздание `v_vineyard_valuation` с колонками `accum_gdd`/`accum_precip_mm`/
  `accum_radiation_mj`/`weather_days` (последний снимок на насаждение, window).
- **`agro_reports.vineyard_valuation`** — вьюха обновлена (drop+create), ensure
  создаёт `land_contours`/`weather_accumulated` при отсутствии.

## Тесты
- `test_weather_open_meteo.py` +`test_store_accumulated_idempotent` (повтор → апдейт).
- `test_vineyard_valuation.py` — погоды нет → `accum_gdd` NULL; после
  `store_accumulated` по геоточке → колонки погоды в оценке.
- Полный агро+земля+погода → **72 passed**. Миграции 0005→0009→0010 чейнятся.

## Файлы
- `parser/egrn_parser/parsers/weather_open_meteo.py` (+ensure_schema/store_accumulated)
- `parser/egrn_parser/parsers/agro_reports.py` (вьюха + ensure с погодой)
- `schema/migrations/0010_weather_accumulated.sql` (новый)
- `parser/tests/test_weather_open_meteo.py`, `parser/tests/test_vineyard_valuation.py`
- `docs/specs/SPEC_parser.md`, `obsidian/Architecture/roadmap-land-agro-graph.md`,
  `obsidian/Decisions/ADR-006-...md` (§J)

## Остаток (внешние зависимости)
Урожай (сборы), почва/агротех-нормы, сетевой прогон погоды, H-viewer.
