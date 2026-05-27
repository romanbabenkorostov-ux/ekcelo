# -*- coding: utf-8 -*-
"""ekcelo · fuzzy matching имён папок.

Используется в `pirushin_sosn_rocha_07_init_project_v3.py` для walk-mode:
обнаружения существующих папок, чьи имена не совпадают с эталоном
буква-в-букву, но семантически означают то же.

Покрывает три типичных случая:
  • Регистр / разделители: «Выписки PDF» ≈ «Выписки_PDF»
  • Раскладка ЙЦУКЕН↔QWERTY (двинули раскладку и не заметили):
    «Dsgbcrb_PDF» (qwerty-набор «Выписки_PDF») → распознаётся.
  • Опечатки / перестановки: «Вписки_PDF» → score ≥ 0.7.

API:
  normalize_name(s)         → str
  detect_layout_swap(s)     → str | None
  name_similarity(a, b)     → float (0.0…1.0)
"""

from __future__ import annotations

import difflib
import re


_SEP_RE = re.compile(r"[\s_\-]+")


def normalize_name(s: str) -> str:
    """Lowercase, ё→е, удаление пробелов / `_` / `-`."""
    return _SEP_RE.sub("", s.lower().replace("ё", "е"))


# Раскладка ЙЦУКЕН ↔ QWERTY (33 пары русских букв + ёЁ + знаки).
# Стандартная Windows-русская раскладка ЙЦУКЕН.
_RU = "йцукенгшщзхъфывапролджэячсмитьбю.ёЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"
_RU2EN = str.maketrans(_RU, _EN)
_EN2RU = str.maketrans(_EN, _RU)

# Признак «строка содержит кириллицу».
_CYR_RE = re.compile(r"[А-Яа-яЁё]")
_LAT_RE = re.compile(r"[A-Za-z]")


def detect_layout_swap(s: str) -> str | None:
    """Если строка целиком латиница и её raw-перевод даёт ≥3 кириллических
    подряд символов — возвращаем перевод. Аналогично в обратную сторону.
    Иначе None.
    """
    if not s:
        return None
    # Считаем «алфавитные» символы.
    cyr = len(_CYR_RE.findall(s))
    lat = len(_LAT_RE.findall(s))
    if lat > 0 and cyr == 0:
        return s.translate(_EN2RU)
    if cyr > 0 and lat == 0:
        return s.translate(_RU2EN)
    return None


def name_similarity(a: str, b: str) -> float:
    """Максимум из:
       • SequenceMatcher на нормализованных строках,
       • SequenceMatcher после layout-swap (если применим),
       • 1.0 если нормализованные сортированные мультимножества букв равны
         (анаграмма).
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    score = difflib.SequenceMatcher(None, na, nb).ratio()
    # Layout-swap: пытаемся перевести `a` и сравнить с `b`.
    swap_a = detect_layout_swap(a)
    if swap_a is not None:
        swap_score = difflib.SequenceMatcher(
            None, normalize_name(swap_a), nb
        ).ratio()
        score = max(score, swap_score)
    # Анаграмма (буквы те же, перестановка).
    if sorted(na) == sorted(nb):
        score = max(score, 1.0)
    return score


def best_match(
    candidate: str, pool: list[str], threshold: float = 0.7
) -> tuple[str, float] | None:
    """Из `pool` ищет имя, наиболее похожее на `candidate`. Возвращает
    (name, score) если score ≥ threshold, иначе None.
    """
    best: tuple[str, float] | None = None
    for p in pool:
        sc = name_similarity(candidate, p)
        if sc >= threshold and (best is None or sc > best[1]):
            best = (p, sc)
    return best
