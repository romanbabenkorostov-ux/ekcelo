"""
egrn_parser/utils/personal_data_filter.py

Реализация алгоритма из Приложения A ТЗ v1.10.
Обязательно вызывается в каждом парсере ДО возврата словаря на верхний уровень
и ДО записи в БД.

Жёсткое ограничение: поле «Сведения о возможности предоставления
третьим лицам персональных данных физического лица» НИКОГДА не сохраняется
ни в SQLite, ни в JSON, ни в XLSX, ни в graph.json.
"""

from __future__ import annotations

import re


# ─────────────────────────────────────────────────────────────────────────────
#  Строки-ключи к исключению (заглавный регистр при поиске игнорируется)
# ─────────────────────────────────────────────────────────────────────────────
PERSONAL_DATA_FIELDS_TO_DROP: frozenset[str] = frozenset({
    "Сведения о возможности предоставления третьим лицам персональных данных физического лица",
    "Сведения о возможности предоставления третьим лицам персональных данных",
    "сведения о возможности предоставления третьим лицам персональных данных физического лица",
    "сведения о возможности предоставления третьим лицам персональных данных",
})

# Регулярное выражение для очистки сырого PDF-текста перед парсингом раздела 2.
# Применяется к тексту подпункта правообладателя.
PERSONAL_CONSENT_RE = re.compile(
    r"Сведения о возможности предоставления третьим лицам персональных данных.*?"
    r"(?=\n\d+\s|\nИНН:|\nОГРН:|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def filter_personal_data(parsed_dict: dict) -> dict:
    """
    Рекурсивно удалить все поля из PERSONAL_DATA_FIELDS_TO_DROP.

    Применяется к любому dict/list до записи в БД или возврата из парсера.
    """
    if not isinstance(parsed_dict, dict):
        return parsed_dict
    return {
        k: filter_personal_data(v) if isinstance(v, (dict, list)) else v
        for k, v in parsed_dict.items()
        if k not in PERSONAL_DATA_FIELDS_TO_DROP
    }


def clean_personal_data_from_text(raw_text: str) -> str:
    """
    Очистить сырой текст (PDF раздел 2) от блоков «Сведения о возможности…».
    Применяется перед парсингом блока правообладателя.
    """
    return PERSONAL_CONSENT_RE.sub("", raw_text)


def assert_no_personal_data(data: dict | list | str) -> None:
    """
    Валидатор для тестов (ТЗ раздел 17.4).
    Вызывает AssertionError если обнаружена фраза о персональных данных.
    """
    FORBIDDEN_PHRASE = "возможности предоставления третьим лицам"
    text_repr = str(data)
    if FORBIDDEN_PHRASE.lower() in text_repr.lower():
        raise AssertionError(
            f"Обнаружена запрещённая фраза о персональных данных в выгрузке:\n"
            f"  «{FORBIDDEN_PHRASE}»"
        )
