# -*- coding: utf-8 -*-
"""Извлечение текста из .doc / .docx без внешних бинарей.

  • .docx → python-docx (если установлен)
  • .doc  → olefile + UTF-16LE decode из WordDocument-stream

Стратегия проверена на реальном ВТБ-фикстуре (Word 97-2003, CP1251):
все банковские поля извлекаются регексами над plain-text выводом.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_PRINTABLE_RE = re.compile(r"[^\x20-\x7eА-Яа-яЁё0-9№.,/():;«»\-\s@+]")


def doc_to_text(path: Path) -> str:
    """Извлекает читаемый текст из .doc / .docx → plain string."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Для .docx требуется python-docx: pip install python-docx"
            ) from e
        return "\n".join(p.text for p in Document(str(path)).paragraphs)

    if suffix == ".doc":
        try:
            import olefile  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Для .doc (Word 97-2003) требуется olefile: pip install olefile"
            ) from e
        ole = olefile.OleFileIO(str(path))
        try:
            raw = ole.openstream("WordDocument").read()
        finally:
            ole.close()
        # WordDocument-stream хранит юникод в UTF-16LE.
        text = raw.decode("utf-16-le", errors="ignore")
        text = _PRINTABLE_RE.sub(" ", text)
        return re.sub(r"\s+", " ", text).strip()

    raise ValueError(f"Неподдерживаемое расширение: {suffix}")


# ─── Generic regex-парсер (fallback для документов без явного источника) ──


_GENERIC_RX = {
    "inn":  re.compile(r"ИНН\s*:?\s*(\d{10,12})"),
    "kpp":  re.compile(r"КПП\s*:?\s*(\d{9})"),
    "ogrn": re.compile(r"(?:^|[^И])ОГРН(?!ИП)\s*:?\s*(\d{13})"),
    "ogrnip": re.compile(r"ОГРНИП\s*:?\s*(\d{15})"),
    "bic":  re.compile(r"БИК\s*:?\s*(\d{9})"),
    "ks":   re.compile(r"К/с\s*:?\s*№?\s*(\d{20})|корр(?:есп)?\.?\s*счет\s*:?\s*№?\s*(\d{20})", re.IGNORECASE),
    "rs":   re.compile(r"Р/с\s*:?\s*№?\s*(\d{20})|расч(?:ет|ёт)?(?:ный)?\s*счет\s*:?\s*№?\s*(\d{20})", re.IGNORECASE),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
}


def parse_generic(path: Path) -> dict:
    """Generic-парсер: извлекает только то, что распознают универсальные
    regex'ы. Возвращает фрагмент canonical-схемы. Незаполненные поля —
    отсутствуют (merge сольёт с эталонными значениями из других
    источников).
    """
    from .. import canonical

    text = doc_to_text(path)
    out: dict = {"bank": {}, "_sources": [{
        "type": "doc_generic",
        "file": str(path),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }]}
    if m := _GENERIC_RX["inn"].search(text):
        inn = m.group(1)
        out["inn"] = inn
        # 12 цифр — ИП.
        if len(inn) == 12:
            out["type"] = "ИП"
    if m := _GENERIC_RX["kpp"].search(text):
        out["kpp"] = m.group(1)
    if m := _GENERIC_RX["ogrn"].search(text):
        out["ogrn"] = m.group(1)
    if m := _GENERIC_RX["ogrnip"].search(text):
        out["ogrnip"] = m.group(1)
    for k in ("bic", "ks", "rs"):
        if m := _GENERIC_RX[k].search(text):
            # У ks/rs два варианта групп (К/с № и корр. счет).
            val = next((g for g in m.groups() if g), None)
            if val:
                out["bank"][k] = val
    if m := _GENERIC_RX["email"].search(text):
        out["emails"] = [m.group(0)]
    _ = canonical  # для статических анализаторов: импорт нужен потребителям.
    return out
