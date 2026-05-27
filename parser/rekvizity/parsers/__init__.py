# -*- coding: utf-8 -*-
"""ekcelo · парсеры разных форматов источников реквизитов.

Dispatch по имени файла:
  *ВТБ*.doc / *vtb*.doc                → bank_vtb.parse
  *.doc / *.docx (generic)             → doc_parser.parse_generic
  (другие — добавляются по мере появления реальных образцов)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import bank_vtb, doc_parser


def detect_parser(path: Path) -> Callable[[Path], dict]:
    """Возвращает функцию-парсер по эвристике имени файла."""
    name = path.name.lower()
    suffix = path.suffix.lower()
    if "втб" in name or "vtb" in name:
        return bank_vtb.parse
    if suffix in (".doc", ".docx"):
        return doc_parser.parse_generic
    raise ValueError(f"Нет парсера для {path}: расширение {suffix}")
