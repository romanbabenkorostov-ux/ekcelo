# -*- coding: utf-8 -*-
"""Валидация УПД-XML по XSD ФНС (ON_NSCHFDOPPR_*.xsd).

XSD bundle хранится в `parser/schema/xsd/upd/`. Если файл XSD
отсутствует — validator вернёт single error «XSD не найден».
"""

from __future__ import annotations

from pathlib import Path

XSD_DIR = Path(__file__).resolve().parents[1] / "schema" / "xsd" / "upd"


def _find_xsd() -> Path | None:
    if not XSD_DIR.is_dir():
        return None
    files = sorted(XSD_DIR.glob("ON_NSCHFDOPPR_*.xsd"))
    return files[-1] if files else None


def validate(xml_path: Path, xsd_path: Path | None = None) -> list[str]:
    """Валидация. Возвращает список ошибок (пустой = ОК).

    Если `xsd_path` не задан — берём самый свежий ON_NSCHFDOPPR_*.xsd
    из bundled-папки.
    """
    if not xml_path.exists():
        return [f"XML не найден: {xml_path}"]

    if xsd_path is None:
        xsd_path = _find_xsd()
    if xsd_path is None or not xsd_path.exists():
        return [
            f"XSD не найден в {XSD_DIR}. "
            "Положите ON_NSCHFDOPPR_*.xsd и повторите запуск."
        ]

    try:
        from lxml import etree  # type: ignore
    except ImportError:
        return ["lxml не установлен: pip install lxml"]

    try:
        schema_doc = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(schema_doc)
    except etree.XMLSchemaParseError as e:
        return [f"XSD parse error: {e}"]

    try:
        xml_doc = etree.parse(str(xml_path))
    except etree.XMLSyntaxError as e:
        return [f"XML syntax error: {e}"]

    if schema.validate(xml_doc):
        return []
    return [str(err) for err in schema.error_log]
