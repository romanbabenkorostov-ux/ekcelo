"""morphology: склонение русских слов и фраз для Jinja-шаблонов ЭТП.

Закрывает падежные баги шаблона `torgi_long_description.j2`:
- «Право собственность» → «Право собственности» (gen)
- «зарегистрировано за Российская Федерация» → «…за Российской Федерацией» (ins)
- «в зона смешанной...» → «в зоне смешанной...» (loc)
- «по удовлетворительная улично-дорожной сети» → «...удовлетворительной...» (loc)
- «помещение офис назначения» → «помещение офисного назначения» (gen)

Регистрируется как набор Jinja-фильтров в `text_render.py`:
  {{ "Российская Федерация" | inflect_ins }}  → «Российской Федерацией»
  {{ "удовлетворительная"  | inflect_loc }}   → «удовлетворительной»

Падежи (pymorphy3 grammemes):
  inflect_nom — nomn — именительный (default)
  inflect_gen — gent — родительный
  inflect_dat — datv — дательный
  inflect_acc — accs — винительный
  inflect_ins — ablt — творительный
  inflect_loc — loct — предложный

Поведение fallback:
- Слова без морфологии (числа, даты, аббревиатуры) → возвращаются как есть.
- Многословные фразы → склоняем каждое слово (адъектив+существительное
  должны согласовываться по роду/числу падежу автоматически через pymorphy3).
- Сохраняется регистр первой буквы каждого слова.

Singleton MorphAnalyzer — инициализируется лениво, ~100 МБ в RSS на первый
вызов. Используется по одному анализатору на процесс.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

# ЗАВИСИМОСТЬ НЕОБЯЗАТЕЛЬНАЯ, И ЭТО НЕ ПОБЛАЖКА. `pymorphy3` тянет словарь на
# сотню мегабайт и нужен ровно одному делу — согласованию падежей в текстах
# ЭТП. Жёсткий импорт делал модуль обязательным для ВСЕГО парсера: в окружении
# без словаря переставали собираться шестнадцать тестовых модулей, ни один из
# которых склонений не касается, а разбор выписок ЕГРН — тем более.
#
# Без словаря фразы возвращаются как есть, в именительном падеже, и об этом
# один раз пишется в лог. Текст с неверным падежом читается коряво, но остаётся
# верным по существу; упавший экспорт не оставляет ничего.
try:
    import pymorphy3
except ImportError:                                            # pragma: no cover
    pymorphy3 = None


_CASE_MAP = {
    "nom": "nomn",
    "gen": "gent",
    "dat": "datv",
    "acc": "accs",
    "ins": "ablt",
    "loc": "loct",
}

# Слова, которые НЕ склоняем (служебные, аббревиатуры, числа).
_SKIP_RE = re.compile(r"^[\d\W_]+$|^[A-ZА-ЯЁ]{2,}$")

# Сохраняем разделители при разбиении фразы.
_TOKEN_RE = re.compile(r"(\w+|\s+|[^\w\s]+)", re.UNICODE)


_morph = None
_warned = False


def available() -> bool:
    """Есть ли словарь морфологии. Вызывающий может спросить заранее."""
    return pymorphy3 is not None


def _analyzer():
    """Анализатор или None. Инициализация ленивая: ~100 МБ на первый вызов."""
    global _morph, _warned
    if pymorphy3 is None:
        if not _warned:
            log.warning("pymorphy3 не установлен — падежи не согласуются, "
                        "фразы выводятся в именительном (pip install pymorphy3)")
            _warned = True
        return None
    if _morph is None:
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def inflect(phrase: Any, case: str) -> str:
    """Склонить фразу в указанный падеж.

    Args:
        phrase: строка (или None — вернёт пустую).
        case: short-имя падежа ('nom'|'gen'|'dat'|'acc'|'ins'|'loc')
              или полное pymorphy3 grammeme ('nomn'/'gent'/...).

    Returns:
        Склонённая фраза с сохранением регистра первой буквы каждого слова.
        Если склонение невозможно — возвращается оригинал.
    """
    if phrase is None:
        return ""
    text = str(phrase)
    if not text.strip():
        return text

    target = _CASE_MAP.get(case, case)
    out: list[str] = []
    for token in _TOKEN_RE.findall(text):
        if token.isalpha() and not _SKIP_RE.match(token):
            inflected = _inflect_word(token, target)
            out.append(inflected)
        else:
            out.append(token)
    return "".join(out)


@lru_cache(maxsize=4096)
def _inflect_word(word: str, target_case: str) -> str:
    """Склонить одно слово (с кешированием).

    Smart-skip: если слово уже стоит в родительном падеже (gent), не
    трогаем — это типичное зависимое слово в составных фразах вроде
    «центральной части города» (`города` — gent от `город`), где
    склонение всей фразы в loc испортило бы согласование.
    Внешние loc/ins/dat применяются к голове, а зависимые в gen остаются.
    """
    morph = _analyzer()
    if morph is None:
        # Словаря нет — слово остаётся как есть, в именительном.
        return word
    parses = morph.parse(word)
    if not parses:
        return word
    parsed = parses[0]
    # Skip gent-формы при склонении в иной не-gent падеж.
    if target_case != "gent" and parsed.tag.case == "gent":
        return word
    try:
        result = parsed.inflect({target_case})
    except (ValueError, KeyError):
        return word
    if result is None:
        return word
    return _restore_case(result.word, word)


def _restore_case(new_word: str, source_word: str) -> str:
    """Восстановить регистр первой буквы из исходника."""
    if not new_word:
        return new_word
    if source_word and source_word[0].isupper():
        return new_word[0].upper() + new_word[1:]
    return new_word


# ─────────────────────────────────────────────────────────────────────────────
#  Удобные шорткаты — для Jinja фильтров
# ─────────────────────────────────────────────────────────────────────────────

def inflect_nom(phrase: Any) -> str:
    return inflect(phrase, "nom")


def inflect_gen(phrase: Any) -> str:
    return inflect(phrase, "gen")


def inflect_dat(phrase: Any) -> str:
    return inflect(phrase, "dat")


def inflect_acc(phrase: Any) -> str:
    return inflect(phrase, "acc")


def inflect_ins(phrase: Any) -> str:
    return inflect(phrase, "ins")


def inflect_loc(phrase: Any) -> str:
    return inflect(phrase, "loc")


JINJA_FILTERS = {
    "inflect_nom": inflect_nom,
    "inflect_gen": inflect_gen,
    "inflect_dat": inflect_dat,
    "inflect_acc": inflect_acc,
    "inflect_ins": inflect_ins,
    "inflect_loc": inflect_loc,
}
