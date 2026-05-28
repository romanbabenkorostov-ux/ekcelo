"""tests/test_address_parser.py — компонентный разбор адресов ЕГРН."""
from __future__ import annotations

import pytest

from parser.exporters.etp.address_parser import parse_address


def test_empty_and_none_return_all_none():
    for v in (None, "", "   "):
        out = parse_address(v)
        assert all(val is None for val in out.values())


def test_rostov_office_address():
    out = parse_address("г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII")
    assert out["locality"] == "г. Ростов-на-Дону"
    assert out["street"] == "ул. Б.Садовая"
    assert out["house"] == "111"
    assert out["room"] == "пом. VII"


def test_rural_land_plot():
    out = parse_address("Ростовская обл., с. Иваново, уч. 7")
    assert out["region"] == "Ростовская обл."
    assert out["locality"] == "с. Иваново"
    assert out["house"] == "уч. 7"


def test_moscow_federal_city():
    """Москва — одновременно region и locality."""
    out = parse_address("г. Москва, ЦАО, ул. Пушкина, 10, стр. 1, помещение VII")
    assert out["region"] == "г. Москва"
    assert out["locality"] == "г. Москва"
    assert out["municipality"] == "ЦАО"
    assert out["street"] == "ул. Пушкина"
    assert out["house"] == "10"
    assert out["building"] == "стр. 1"
    assert out["room"] == "помещение VII"


def test_house_with_letter_suffix():
    out = parse_address("ул. Ленина, 12А")
    assert out["street"] == "ул. Ленина"
    assert out["house"] == "12А"


def test_house_with_fraction():
    out = parse_address("ул. Тверская, 12/3")
    assert out["house"] == "12/3"


def test_d_prefix_for_house():
    out = parse_address("ул. Мира, д. 5")
    assert out["house"].startswith("д.") or out["house"] == "д. 5"


def test_apartment():
    out = parse_address("г. Казань, ул. Баумана, 10, кв. 42")
    assert out["room"] == "кв. 42"


@pytest.mark.parametrize("raw,expected_region", [
    ("Краснодарский край, ст-ца Полтавская", "Краснодарский край"),
    ("Республика Татарстан, г. Казань", "Республика Татарстан"),
])
def test_region_patterns(raw, expected_region):
    out = parse_address(raw)
    assert out["region"] == expected_region


def test_unrecognized_garbage_falls_back_silently():
    """Если адрес не распознать — все компоненты None, исключений нет."""
    out = parse_address("какая-то непонятная строка")
    assert all(v is None for v in out.values())


def test_returns_seven_keys():
    out = parse_address("г. Москва")
    assert set(out.keys()) == {"region", "municipality", "locality",
                                "street", "house", "building", "room"}
