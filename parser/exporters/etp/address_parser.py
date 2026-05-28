"""address_parser: разбор plain-адреса из ЕГРН в компоненты SPEC §3.

Закрывает гэп §10 (компонентный адрес). Региональный формат адреса:
- "г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII"
- "Ростовская обл., с. Иваново, уч. 7"
- "г. Москва, ЦАО, ул. Пушкина, 10, стр. 1, помещение VII"

Подход: токенизация по запятой + классификация по префиксам и
типам токенов. Парсер не претендует на полную точность (используем
libpostal в случае production); цель — заполнить компоненты для
читаемой подписи в карточке ЭТП.
"""
from __future__ import annotations

import re
from typing import Final


_COMPONENT_KEYS: Final = (
    "region", "municipality", "locality",
    "street", "house", "building", "room",
)


# Префиксы локалити (населённого пункта)
_LOCALITY_PREFIXES = (
    "г.", "город", "пос.", "посёлок", "поселок",
    "с.", "село", "д.", "деревня",
    "пгт.", "пгт", "ст-ца", "станица",
    "х.", "хутор", "снт", "тер.",
)

# Регионы / субъекты РФ
_REGION_PATTERNS = (
    # "Ростовская обл.", "Краснодарский край", "Иркутская область"
    re.compile(r"^[А-ЯЁ][а-яё-]+\s+(?:обл\.|область|край|респ\.|республика)(?:\s|$)", re.IGNORECASE),
    # "Республика Татарстан", "Республика Крым"
    re.compile(r"^[Рр]еспублика\s+[А-ЯЁ][а-яё-]+\b"),
    # автономные округа
    re.compile(r"^(?:АО|автономн\w+\s+округ|автономн\w+\s+область)\b", re.IGNORECASE),
)

# Города федерального значения — одновременно region и locality
_FEDERAL_CITIES = {"г. москва", "г. санкт-петербург", "г. севастополь",
                   "москва", "санкт-петербург", "севастополь"}

# Префиксы улиц/проездов
_STREET_PREFIXES = (
    "ул.", "улица", "пр-кт", "пр.", "проспект", "просп.",
    "пер.", "переулок", "ш.", "шоссе", "наб.", "набережная",
    "б-р", "бульвар", "пл.", "площадь", "тупик",
    "проезд", "линия", "аллея", "тракт", "мкр.", "микрорайон",
)

# Префиксы дома / строения / квартиры / помещения / участка
_HOUSE_PREFIX = re.compile(r"^(?:д\.|дом|вл\.|владение|зд\.|здание|корп\.|корпус|стр\.|строение|литера?|лит\.|уч\.|участок|поз\.|позиция)\s*", re.IGNORECASE)
_ROOM_PREFIX = re.compile(r"^(?:кв\.|квартира|пом\.|помещение|оф\.|офис|комн\.|комната|каб\.|кабинет|секц\.|секция)\s+", re.IGNORECASE)
_BUILDING_PREFIX = re.compile(r"^(?:корп\.|корпус|стр\.|строение|лит\.|литера?)\s*", re.IGNORECASE)

# Голый дом — число с возможной буквой или дробью: "111", "12А", "12/3"
_BARE_HOUSE = re.compile(r"^[0-9]+[А-ЯЁа-яё]?(?:[/\\-][0-9]+[А-ЯЁа-яё]?)?$")


def parse_address(raw: str | None) -> dict[str, str | None]:
    """Разобрать plain-адрес в компоненты SPEC §3.

    Возвращает dict с 7 ключами; неузнанные части — None. При полном
    провале распознавания region остаётся None, остальные могут быть
    заполнены частично. Полный raw-адрес всегда доступен в ctx.location.address_raw.
    """
    result: dict[str, str | None] = {k: None for k in _COMPONENT_KEYS}
    if not raw or not raw.strip():
        return result

    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    used = [False] * len(tokens)

    for i, t in enumerate(tokens):
        if used[i]:
            continue

        # 1. Регион
        if result["region"] is None and _is_region(t):
            result["region"] = t
            used[i] = True
            continue

        # 2. Город федерального значения (одновременно region + locality)
        if t.lower() in _FEDERAL_CITIES:
            if result["region"] is None:
                result["region"] = t
            if result["locality"] is None:
                result["locality"] = t
            used[i] = True
            continue

        # 3. Локалити (нас. пункт). Дисамбигуация "д.": "д. Иваново" = деревня,
        # "д. 5" = дом (число после префикса → house, не locality).
        if result["locality"] is None and _starts_with_any(t, _LOCALITY_PREFIXES):
            if not _is_house_with_letter_prefix(t):
                result["locality"] = t
                used[i] = True
                continue

        # 4. Улица
        if result["street"] is None and _starts_with_any(t, _STREET_PREFIXES):
            result["street"] = t
            used[i] = True
            continue

        # 5. Корпус/строение (отдельный токен)
        if result["building"] is None and _BUILDING_PREFIX.match(t):
            result["building"] = t
            used[i] = True
            continue

        # 6. Помещение / квартира / офис
        if result["room"] is None and _ROOM_PREFIX.match(t):
            result["room"] = t
            used[i] = True
            continue

        # 7. Дом (с префиксом или голое число)
        if result["house"] is None and (_HOUSE_PREFIX.match(t) or _BARE_HOUSE.match(t)):
            # Префикс "уч." (участок) — это house для земельного участка.
            result["house"] = t
            used[i] = True
            continue

    # Municipality: «округ» / «район» или короткие аббревиатуры округов
    # типа ЦАО, ЮВАО (две заглавные кириллицы + АО).
    for i, t in enumerate(tokens):
        if used[i] or result["municipality"] is not None:
            continue
        if re.search(r"(?:округ|район|\bАО\b)", t, re.IGNORECASE) or _is_district_abbrev(t):
            result["municipality"] = t
            used[i] = True

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_region(token: str) -> bool:
    return any(p.match(token) for p in _REGION_PATTERNS)


def _starts_with_any(token: str, prefixes: tuple[str, ...]) -> bool:
    low = token.lower()
    return any(low.startswith(p) for p in prefixes)


# Префикс "д." за которым идёт число — это дом, а не деревня.
_HOUSE_AFTER_D = re.compile(r"^д\.\s*\d", re.IGNORECASE)

def _is_house_with_letter_prefix(token: str) -> bool:
    return bool(_HOUSE_AFTER_D.match(token))


# Аббревиатура округа Москвы / СПб: ЦАО, ЮВАО, СЗАО и т.п. — 2-4 заглавные
# кириллицы, заканчивающиеся на АО.
_DISTRICT_ABBREV = re.compile(r"^[А-ЯЁ]{1,3}АО$")

def _is_district_abbrev(token: str) -> bool:
    return bool(_DISTRICT_ABBREV.match(token))
