# -*- coding: utf-8 -*-
"""Парсер выписки реквизитов с сайта ВТБ (.doc, Word 97-2003).

Проверено на реальном фикстуре `vtb_nekso_2026.doc` — извлекает 4
банковских поля (name, bic, ks, rs) + ИНН/КПП/ОГРН + ФИО подписанта +
email.

Источник распознавания: имя файла содержит «ВТБ» / «vtb»
(см. parsers/__init__.py::detect_parser).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .doc_parser import doc_to_text


_RX = {
    "bic":       re.compile(r"БИК\s*:?\s*(\d{9})"),
    "ks":        re.compile(r"К/с\s*:?\s*№?\s*(\d{20})"),
    "rs":        re.compile(r"Р/с\s*:?\s*№?\s*(\d{20})"),
    # «в ФИЛИАЛ "ЦЕНТРАЛЬНЫЙ" БАНКА ВТБ (ПАО), Москва К/с …»
    "bank_name": re.compile(
        r"в\s+(ФИЛИАЛ\s+\"[^\"]+\"\s+БАНКА\s+ВТБ\s+\(ПАО\)[^К]*?)К/с"
    ),
    "inn":       re.compile(r"ИНН\s*:?\s*(\d{10,12})"),
    "kpp":       re.compile(r"КПП\s*:?\s*(\d{9})"),
    "ogrn":      re.compile(r"(?:^|[^И])ОГРН(?!ИП)\s*:?\s*(\d{13})"),
    "signatory": re.compile(
        r"(Генеральный директор|Директор|И\.?О\. директора|"
        r"Индивидуальный предприниматель)"
        r"\s+([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)"
    ),
    "email":     re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    # Адрес: «Юридический адрес и Фактический адрес: 195112 …»
    "address":   re.compile(
        r"(?:Юридический\s+адрес(?:\s+и\s+Фактический\s+адрес)?|Адрес)\s*:?\s*"
        r"(\d{6}[^\n]*?)(?=\s+Телефон|\s+email|\s+e-?mail|\s+ИНН|\s*$)",
        re.IGNORECASE,
    ),
    # Полное наименование (в кавычках после "Общество с ограниченной …").
    "name_full": re.compile(
        r"«([^»]+?)»|\"([^\"]+?)\""
    ),
    # Краткое наименование: «ООО "НЭКСО"» / «АО "…"» / «ИП Иванов И. И.»
    "name_short": re.compile(
        r"((?:ООО|ОАО|АО|ПАО|ЗАО|ГУП|ИП)\s+[«\"][^»\"]+[»\"])"
    ),
}


def parse(path: Path) -> dict:
    """ВТБ-выписка реквизитов → фрагмент canonical-схемы."""
    text = doc_to_text(path)
    out: dict = {
        "bank": {},
        "_sources": [{
            "type": "doc_bank_vtb",
            "file": str(path),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }],
    }

    if m := _RX["bank_name"].search(text):
        out["bank"]["name"] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",")
    for k in ("bic", "ks", "rs"):
        if m := _RX[k].search(text):
            out["bank"][k] = m.group(1)

    if m := _RX["inn"].search(text):
        inn = m.group(1)
        out["inn"] = inn
        if len(inn) == 12:
            out["type"] = "ИП"
    if m := _RX["kpp"].search(text):
        out["kpp"] = m.group(1)
    if m := _RX["ogrn"].search(text):
        out["ogrn"] = m.group(1)

    if m := _RX["signatory"].search(text):
        out["signatory"] = {
            "position": m.group(1),
            "fio": m.group(2),
            "basis": "Устав",
        }
    if m := _RX["email"].search(text):
        out["emails"] = [m.group(0)]
    if m := _RX["address"].search(text):
        out["address_legal"] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",")

    # Краткое наименование (если в файле есть «ООО "НЭКСО"» или подобное).
    if m := _RX["name_short"].search(text):
        out["name_short"] = m.group(1).strip()
        # Тип юр. лица — первое слово краткого имени.
        first = m.group(1).split()[0].upper()
        if first in {"ООО", "ОАО", "АО", "ПАО", "ЗАО", "ГУП"}:
            out["type"] = first

    return out
