"""
egrn_parser/parsers/docx_parser.py — парсер DOCX-перечней имущества.

Ищет таблицы с колонкой «Кадастровый номер» и извлекает данные об объектах.
DOCX-фотоотчёты (содержащие «-фотоотчёт» в имени или много изображений)
отфильтровываются ДО вызова этого модуля (utils/filename_filter.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from egrn_parser.parsers._common import normalize_cad_number, normalize_whitespace, is_absent

log = logging.getLogger(__name__)

# Заголовки колонок, которые считаются «кадастровым номером»
CAD_NUMBER_HEADERS = frozenset({
    "кадастровый номер",
    "кадастровый №",
    "кадастровый номер объекта",
    "кад. номер",
    "№ кадастровый",
})


def parse_docx_inventory(path: Path | str) -> dict:
    """
    Разобрать DOCX-перечень имущества.

    Ищет таблицы с кадастровыми номерами и возвращает список объектов.
    Возвращает dict с ключами:
      objects:  list[dict] — найденные объекты
      warnings: list[str]
      source_file: str
    """
    path = Path(path)
    result: dict[str, Any] = {
        "objects":    [],
        "warnings":   [],
        "source_file": path.name,
    }

    try:
        import docx  # python-docx
        doc = docx.Document(str(path))
    except Exception as e:
        log.error("Не удалось открыть DOCX %s: %s", path.name, e)
        result["warnings"].append(f"Ошибка открытия: {e}")
        return result

    for table_idx, table in enumerate(doc.tables):
        # Найти строку-заголовок (первая или вторая строка)
        header_row = None
        for row in table.rows[:3]:
            cells = [c.text.strip().lower() for c in row.cells]
            if any(any(h in c for h in CAD_NUMBER_HEADERS) for c in cells):
                header_row = cells
                break

        if header_row is None:
            continue

        # Определить индексы колонок
        cad_col = next(
            (i for i, h in enumerate(header_row)
             if any(kw in h for kw in CAD_NUMBER_HEADERS)),
            None,
        )
        if cad_col is None:
            continue

        # Дополнительные колонки (если есть)
        name_col = next((i for i, h in enumerate(header_row)
                         if "наименование" in h or "объект" in h), None)
        addr_col = next((i for i, h in enumerate(header_row)
                         if "адрес" in h or "местоположение" in h), None)
        area_col = next((i for i, h in enumerate(header_row)
                         if "площадь" in h), None)

        # Читать строки данных (пропускаем заголовок)
        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if cad_col >= len(cells):
                continue

            cad_raw = cells[cad_col]
            cad_number = normalize_cad_number(cad_raw)
            if not cad_number:
                continue

            obj: dict[str, Any] = {
                "cad_number":  cad_number,
                "data_source": path.name,
            }
            if name_col is not None and name_col < len(cells):
                obj["name"] = normalize_whitespace(cells[name_col]) or None
            if addr_col is not None and addr_col < len(cells):
                obj["address"] = normalize_whitespace(cells[addr_col]) or None
            if area_col is not None and area_col < len(cells):
                from egrn_parser.parsers._common import parse_number
                obj["area"] = parse_number(cells[area_col])

            result["objects"].append(obj)

    if not result["objects"]:
        result["warnings"].append("Таблицы с кадастровыми номерами не найдены")

    log.info("✓ DOCX %s: %d объектов", path.name, len(result["objects"]))
    return result
