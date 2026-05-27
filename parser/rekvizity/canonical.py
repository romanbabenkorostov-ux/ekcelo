# -*- coding: utf-8 -*-
"""Каноническая схема реквизитов юридического лица / ИП.

Schema version: 1 (см. поле `_schema_version`).

Поля, помеченные `optional`, могут отсутствовать в источнике; merge.py
гарантирует, что отсутствующее поле не затирает уже известное значение.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1

# Каноническое множество ключей верхнего уровня. Источник: ФНС-выписки + банковские .doc.
TOP_LEVEL_KEYS = {
    "inn",          # str: 10 (ЮЛ) или 12 (ИП) цифр
    "kpp",          # str | None: 9 цифр (только ЮЛ)
    "ogrn",         # str | None: 13 цифр (только ЮЛ)
    "ogrnip",       # str | None: 15 цифр (только ИП)
    "type",         # str: "ООО" | "ОАО" | "АО" | "ПАО" | "ЗАО" | "ГУП" | "ИП" | ...
    "name_full",
    "name_short",
    "address_legal",
    "address_actual",   # None если совпадает с legal
    "bank",         # dict: {name, bic, ks, rs}
    "signatory",    # dict: {fio, position, basis}
    "phones",       # list[str]
    "emails",       # list[str]
    "site",
}

BANK_KEYS = {"name", "bic", "ks", "rs"}
SIGNATORY_KEYS = {"fio", "position", "basis"}


def empty_canonical() -> dict[str, Any]:
    """Пустой canonical (все поля None / пустые списки / пустые dict-ы)."""
    return {
        "_schema_version": SCHEMA_VERSION,
        "inn": None,
        "kpp": None,
        "ogrn": None,
        "ogrnip": None,
        "type": None,
        "name_full": None,
        "name_short": None,
        "address_legal": None,
        "address_actual": None,
        "bank": {"name": None, "bic": None, "ks": None, "rs": None},
        "signatory": {"fio": None, "position": None, "basis": None},
        "phones": [],
        "emails": [],
        "site": None,
        "_sources": [],
        "_updated_at": None,
    }


# Приоритет источников при merge (выше = надёжнее).
SOURCE_PRIORITY = {
    "pdf_egrul": 100,
    "pdf_egrip": 95,
    "doc_bank_vtb": 85,     # банковские реквизиты — самый надёжный источник для bank.*
    "doc_bank_sber": 85,
    "doc_bank_tinkoff": 85,
    "doc_bank_generic": 70,
    "doc_generic": 60,
    "json_manual": 50,
    "sqlite_export": 40,
}


def source_score(source_type: str) -> int:
    return SOURCE_PRIORITY.get(source_type, 0)


def validate(rek: dict[str, Any]) -> list[str]:
    """Базовая валидация — возвращает список ошибок (пустой = ОК)."""
    errors: list[str] = []
    inn = rek.get("inn")
    if inn is None:
        errors.append("inn: обязательное поле, не задано")
    elif not (isinstance(inn, str) and inn.isdigit() and len(inn) in (10, 12)):
        errors.append(f"inn: ожидается строка 10 или 12 цифр, получено {inn!r}")
    if rek.get("ogrn") and not (
        isinstance(rek["ogrn"], str) and rek["ogrn"].isdigit() and len(rek["ogrn"]) == 13
    ):
        errors.append(f"ogrn: ожидается 13 цифр, получено {rek['ogrn']!r}")
    if rek.get("ogrnip") and not (
        isinstance(rek["ogrnip"], str)
        and rek["ogrnip"].isdigit()
        and len(rek["ogrnip"]) == 15
    ):
        errors.append(f"ogrnip: ожидается 15 цифр, получено {rek['ogrnip']!r}")
    if rek.get("kpp") and not (
        isinstance(rek["kpp"], str) and rek["kpp"].isdigit() and len(rek["kpp"]) == 9
    ):
        errors.append(f"kpp: ожидается 9 цифр, получено {rek['kpp']!r}")
    bank = rek.get("bank") or {}
    if bank.get("bic") and not (
        isinstance(bank["bic"], str) and bank["bic"].isdigit() and len(bank["bic"]) == 9
    ):
        errors.append(f"bank.bic: ожидается 9 цифр, получено {bank['bic']!r}")
    for k in ("ks", "rs"):
        if bank.get(k) and not (
            isinstance(bank[k], str) and bank[k].isdigit() and len(bank[k]) == 20
        ):
            errors.append(
                f"bank.{k}: ожидается 20 цифр, получено {bank[k]!r}"
            )
    return errors
