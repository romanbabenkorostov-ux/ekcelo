"""tests/test_encumbrance_mapper.py — маппинг типа обременения в текст влияния."""
from __future__ import annotations

import pytest

from parser.exporters.etp.encumbrance_mapper import known_types, map_encumbrance


def test_known_types_returns_sorted_tuple():
    types = known_types()
    assert isinstance(types, tuple)
    assert types == tuple(sorted(types))
    assert "ипотека" in types
    assert "арест" in types


@pytest.mark.parametrize("restrict_type", [
    "ипотека", "залог", "аренда", "сервитут", "арест",
    "доверительное управление", "okn_territory",
])
def test_known_types_have_non_empty_influence(restrict_type):
    out = map_encumbrance(restrict_type)
    assert out and len(out) > 10


def test_substring_match_for_legal_phrase():
    """«ипотека в силу закона» матчится на ключ «ипотека»."""
    out = map_encumbrance("Ипотека в силу закона")
    assert out is not None
    assert "продаже" in out


def test_unknown_type_returns_none():
    assert map_encumbrance("blablabla unknown") is None


def test_none_and_empty_return_none():
    assert map_encumbrance(None) is None
    assert map_encumbrance("") is None
    assert map_encumbrance("   ") is None


def test_case_insensitive():
    assert map_encumbrance("ИПОТЕКА") == map_encumbrance("ипотека")
    assert map_encumbrance("Арест") == map_encumbrance("арест")


def test_ipoteka_text_contains_key_phrases():
    out = map_encumbrance("ипотека")
    assert "не препятствует" in out
    assert "торгов" in out


def test_arest_blocks_transfer():
    out = map_encumbrance("арест")
    assert "препятствует" in out
