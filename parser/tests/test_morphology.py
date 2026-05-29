"""tests/test_morphology.py — pymorphy3 фильтры склонения для Jinja."""
from __future__ import annotations

import pytest

from parser.exporters.etp.morphology import (
    inflect,
    inflect_gen,
    inflect_ins,
    inflect_loc,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Базовые случаи
# ─────────────────────────────────────────────────────────────────────────────

def test_inflect_loc_singleword():
    assert inflect_loc("зона") == "зоне"
    assert inflect_loc("сеть") == "сети"


def test_inflect_gen_singleword():
    assert inflect_gen("собственность") == "собственности"


def test_inflect_ins_phrase_agreement():
    """«Российская Федерация» в творительном → «Российской Федерацией»."""
    out = inflect_ins("Российская Федерация")
    assert out == "Российской Федерацией"


def test_inflect_gen_phrase():
    """«офис» в gen → «офиса»."""
    assert inflect_gen("офис") == "офиса"


def test_capitalization_preserved():
    """Первая буква заглавная в источнике → остаётся заглавной."""
    assert inflect_loc("Зона").startswith("З")
    assert inflect_ins("Российская")[0] == "Р"


def test_lowercase_stays_lowercase():
    assert inflect_loc("зона")[0].islower()


# ─────────────────────────────────────────────────────────────────────────────
#  Фразы с разделителями
# ─────────────────────────────────────────────────────────────────────────────

def test_phrase_preserves_separators():
    out = inflect_loc("удовлетворительная сеть")
    assert " " in out  # пробел сохраняется
    # И слова склонились в loc.
    assert "удовлетворительной" in out
    assert "сети" in out


def test_multiword_with_comma():
    out = inflect_loc("зона смешанной жилой застройки")
    # Запятых нет; проверяем, что хотя бы одно слово склонилось корректно.
    assert "зоне" in out


# ─────────────────────────────────────────────────────────────────────────────
#  Безопасные fallback'и
# ─────────────────────────────────────────────────────────────────────────────

def test_none_returns_empty():
    assert inflect(None, "loc") == ""


def test_empty_string_passes_through():
    assert inflect("", "loc") == ""
    assert inflect("   ", "loc") == "   "


def test_numbers_not_inflected():
    """Числа должны оставаться без изменений."""
    out = inflect("123", "loc")
    assert "123" in out


def test_unknown_word_returns_self():
    """Неизвестное слово → возвращается как есть."""
    out = inflect("kjfsdhfkjsdhfk", "loc")
    assert "kjfsdhfkjsdhfk" in out


def test_uppercase_abbrev_passes_through():
    """Аббревиатуры из заглавных (НСПД, КН) — не склоняем."""
    out = inflect("НСПД", "loc")
    assert "НСПД" in out


def test_case_short_or_full_form():
    """Короткие имена ('loc') и полные ('loct') работают одинаково."""
    assert inflect("зона", "loc") == inflect("зона", "loct")


def test_unknown_case_returns_self():
    """Неизвестный падеж → fallback к исходнику без падения."""
    assert "зона" in inflect("зона", "xxxx")
