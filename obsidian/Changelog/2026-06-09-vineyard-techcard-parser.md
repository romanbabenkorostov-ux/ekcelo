# 2026-06-09 — A: парсер техкарты виноградника (образец получен)

Образец техкарты получен (`fixtures/agro/vineyard_techcard_sample.xlsx`) — реализован
трек A. По указанию заказчика: **только виноградники** (работы по другим культурам не
обрабатываются; структура листов переиспользуема).

## Реализовано (`agro_techcard.py`, замена заглушки)
- **Виноград-гейт:** `parse_workbook` → `is_vineyard`; не-виноград → пустые записи.
- **3 типа листов:** смета-операции (Посадка/Шпалера/Уходные: код|работа|ед|стоим/ед|
  год|ИТОГО), СЗР+удобрения (препарат|цена|расход на 1 га), плодоносящие (проверка).
- **Маппинг (ADR-006):** meta(площадь/саженцы) → `agro_parcel`; виноград(perennial,
  закладка в `sow_date`) → `agro_crop_cycle(plan)`; операции → `agro_event(operation)`;
  пестициды СЗР → `agro_event(treatment)` с `active_substances[{name,rate,unit}]`;
  удобрения → `operation`.
- **`ingest`** пишет в агро-слой (миграция 0005), валидирует attrs через
  `validate_event_attrs` (D); невалидные считаются (план не отбраковывается).
- Профиль **`operation`** добавлен в `agro_event_profiles` (обобщённая агро-операция).

## Проверено на реальном образце
- is_vineyard=True; площадь закладки 204 га; саженцев 560 000.
- 54 операции (годы 2024/2025), 12 пестицидов (Полирам rate=2.5…) + 8 удобрений.
- ingest: 1 parcel + 1 cycle (perennial, sow_date=2024) + 74 события (54 операции +
  20 веществ), invalid=[].

## Тесты
- `tests/test_agro_techcard.py` (+7): гейт, meta, счётчики операций/веществ, маппинг,
  ingest в агро-слой, отсев не-винограда (пшеница/кукуруза).
- Устаревший `test_techcard_stub_raises` → `test_techcard_parser_implemented`.
- Полный агро+земля прогон → **59 passed**.

## Docs
- SPEC §12 — парсер техкарты (виноградники) ✅.
- roadmap — A закрыт; остаётся: карты со сборами (harvest по сортам), H-viewer,
  другие культуры по запросу.

## Файлы
- `parser/egrn_parser/parsers/agro_techcard.py` (реализация)
- `parser/egrn_parser/parsers/agro_event_profiles.py` (+профиль operation)
- `parser/tests/test_agro_techcard.py` (новый)
- `parser/tests/fixtures/agro/vineyard_techcard_sample.xlsx` (образец)
- `parser/tests/test_land_layout.py` (актуализирован тест заглушки)
- `docs/specs/SPEC_parser.md`, `obsidian/Architecture/roadmap-land-agro-graph.md`
