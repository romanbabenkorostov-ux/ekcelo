"""tests/test_holder_identity.py — различение физлиц без хранения ФИО.

Сторожится ошибка, которая в отчёте выглядит правдоподобно и потому не
замечается: два физлица с долями по 1/2 склеивались в ОДНОГО собственника,
потому что seed их `subject_uuid` был общей строкой «unknown_individual» —
ФИО-то парсер не сохраняет.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers.xml_parser import hash_snils, mask_snils   # noqa: E402


def test_mask_hides_second_and_next_to_last_sign():
    assert mask_snils("213-591-004 29") == "2*3-591-004 *9"
    assert mask_snils("199-042-745 04") == "1*9-042-745 *4"


def test_mask_keeps_the_string_recognisable_to_its_owner():
    """Маска скрывает два знака из четырнадцати — этого хватает, чтобы не
    перепутать двух совладельцев, и мало, чтобы опознать человека."""
    masked = mask_snils("213-591-004 29")
    assert masked.count("*") == 2
    assert len(masked) == len("213-591-004 29")


def test_mask_survives_garbage():
    assert mask_snils(None) is None
    assert mask_snils("") is None
    assert mask_snils("12") is None


def test_hash_is_stable_and_separates_people():
    first = hash_snils("213-591-004 29")
    assert first == hash_snils("21359100429")      # разделители не важны
    assert first != hash_snils("199-042-745 04")
    assert len(first) == 16


def test_hash_refuses_short_input():
    """Обрывок СНИЛС ключом быть не может: он склеит разных людей."""
    assert hash_snils("213-59") is None
    assert hash_snils(None) is None


def test_snils_itself_never_leaves_the_parser():
    """Ни маска, ни хеш не содержат исходного номера целиком."""
    snils = "213-591-004 29"
    digits = snils.replace("-", "").replace(" ", "")
    assert digits not in (mask_snils(snils) or "")
    assert digits not in (hash_snils(snils) or "")
