"""
egrn_parser/parsers/agro_techcard.py — ЗАГЛУШКА парсера технологической карты
(агро) → нормализованные записи `agro_parcel` + `agro_event` (ADR-006).

СТАТУС: не реализовано. Блокер — нет образца техкарты (техдолг заказчика).
Контракт (ТЗ) ниже фиксирует ожидаемый вход/выход, чтобы при появлении образца
(`fixtures/agro/`) реализация была однозначной. Полное ТЗ: `fixtures/agro/TZ_techcard.md`.

ТЗ (кратко)
----------
Вход: техкарта (Excel/CSV) экономиста. Строки — поля/участки за сезон, напр.:
    «Виноград уч.519 "Одесский Чёрный" 2021 г. — 4,06 га»
    «Виноград уч.714 "Мерло" 2022 г. — 11,39 га»
плюс листы/блоки обработок (дата, препарат, действующие вещества, норма ед/га)
и сборов (дата, сорт, объём, кислотность, сахар).

Выход — нормализованные записи (ADR-006 §A,C,F):
    {
      "parcels": [ {parcel_code, season_year, crop, variety, lifecycle,
                    planting_year, area_ha, valid_from?, known_from?, ...} ],
      "events":  [ {parcel_code, season_year, event_type, event_date,
                    attrs{...}, asset_ref?} ],
    }
event_type ∈ {harvest, treatment, observation, phenology}; attrs — JSON-профиль:
  harvest:   {variety, volume_kg, acidity_g_l, sugar_brix, grade}
  treatment: {kind, preparation, active_substances:[{name, rate, unit}], target}
Запись в БД — через будущий `agro_db.upsert_*` (миграция 0004_agro_layer.sql).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_techcard(path: Path | str) -> dict[str, Any]:
    """ЗАГЛУШКА. Реализация ждёт образец техкарты (`fixtures/agro/`).

    При вызове бросает NotImplementedError с пояснением. Сигнатура и форма
    результата зафиксированы в docstring модуля / `fixtures/agro/TZ_techcard.md`.
    """
    raise NotImplementedError(
        "Парсер техкарты не реализован: нужен образец в fixtures/agro/ "
        "(см. ТЗ в docstring и fixtures/agro/TZ_techcard.md). "
        "Ожидаемый выход: {'parcels': [...], 'events': [...]} (ADR-006)."
    )


# Ожидаемая форма нормализованной записи (для будущего agro_db / тестов).
def empty_agro_result() -> dict[str, list]:
    return {"parcels": [], "events": []}
