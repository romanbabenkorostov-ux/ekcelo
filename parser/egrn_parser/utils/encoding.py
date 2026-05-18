"""
egrn_parser/utils/encoding.py — автоопределение кодировки файлов.
Перенесено из pirushin_sosn_rocha_02.
"""

from __future__ import annotations

from pathlib import Path


ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1251", "cp1252")


def detect_encoding(file_path: Path | str) -> str | None:
    """
    Автоопределение кодировки: перебирает UTF-8-sig, UTF-8, CP1251, CP1252.
    Возвращает первую подходящую или None.
    """
    for enc in ENCODINGS_TO_TRY:
        try:
            with open(file_path, "r", encoding=enc) as f:
                f.read()
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def read_text_auto(file_path: Path | str) -> str:
    """Прочитать текстовый файл с автоопределением кодировки."""
    enc = detect_encoding(file_path)
    if enc is None:
        raise UnicodeDecodeError(
            f"Не удалось определить кодировку файла: {file_path}",
            b"", 0, 1, "unknown encoding",
        )
    return Path(file_path).read_text(encoding=enc)
