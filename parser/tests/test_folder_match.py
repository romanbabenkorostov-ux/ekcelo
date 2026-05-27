# -*- coding: utf-8 -*-
"""Tests for parser.utils.folder_match."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.utils.folder_match import (
    best_match,
    detect_layout_swap,
    name_similarity,
    normalize_name,
)


def test_normalize_basic():
    assert normalize_name("Выписки_PDF") == "выпискиpdf"
    assert normalize_name("Выписки PDF") == "выпискиpdf"
    assert normalize_name("Выписки-PDF") == "выпискиpdf"
    assert normalize_name("ЁЛКА") == "елка"


def test_case_insensitive_match():
    sc = name_similarity("Выписки_PDF", "выписки pdf")
    assert sc == 1.0


def test_anagram_match():
    # Перестановка букв (искусственный кейс).
    sc = name_similarity("abc", "cba")
    assert sc == 1.0


def test_layout_swap_ru_to_en():
    # «Vshbcrb» на qwerty при включённой русской раскладке = «Мысбскб»
    # (типичная ошибка пользователя). Проверяем что детектор хотя бы
    # возвращает не-None для чистой латиницы.
    swap = detect_layout_swap("Dsgbcrb")
    assert swap is not None
    # Перевод не обязан давать осмысленное русское слово — проверяем сам факт.


def test_layout_swap_no_op_on_mixed():
    assert detect_layout_swap("hello123мир") is None
    assert detect_layout_swap("") is None


def test_low_similarity():
    sc = name_similarity("Выписки_PDF", "Фотографии")
    assert sc < 0.7


def test_best_match_picks_winner():
    canonical = [
        "Выписки_PDF",
        "Документы_JPG",
        "Не_распределено",
        "Фотографии",
    ]
    match = best_match("выписки pdf", canonical, threshold=0.7)
    assert match is not None
    assert match[0] == "Выписки_PDF"


def test_best_match_below_threshold():
    canonical = ["Выписки_PDF", "Документы_JPG"]
    assert best_match("совершенно_другое", canonical, threshold=0.7) is None
