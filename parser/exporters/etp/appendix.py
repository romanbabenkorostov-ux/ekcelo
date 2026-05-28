"""appendix: PDF-приложение для лота (формат — Markdown).

SPEC §6 предполагает `lot_appendix.pdf`. На текущем этапе генерируем
Markdown — конверсия в PDF идёт через существующий пайплайн
python-docx → LibreOffice → Word (см. dev/SPEC_TEMPORAL_REPORTS.md
§MD→DOCX util fallback).

Содержимое: сводка по лоту + ссылка на отчёт оценщика + инвентарь
документов / связанных КН. Один файл на лот (не на платформу).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def build_lot_appendix(conn: sqlite3.Connection, lot_id: str) -> str:
    """Собрать Markdown-приложение для лота.

    Содержит:
    - Заголовок и идентификацию лота.
    - Сводку платформ-получателей и процедуры.
    - Состав лота (таблица lot_items с ролями).
    - Базовые ЕГРН-данные по primary КН.
    - Указание на сторонние документы (отчёт оценщика, техдокументация).

    Args:
        conn: открытое соединение с БД (миграция 0001 применена).
        lot_id: идентификатор лота.

    Returns:
        Markdown-текст (без trailing newline кроме одного в конце).

    Raises:
        LookupError: если лот не найден.
    """
    conn.row_factory = sqlite3.Row
    lot = conn.execute("SELECT * FROM lots WHERE lot_id = ?", (lot_id,)).fetchone()
    if not lot:
        raise LookupError(f"Lot not found: {lot_id!r}")

    items = list(conn.execute(
        "SELECT li.cad_number, li.role, li.ord, o.object_type, o.address, o.area "
        "FROM lot_items li LEFT JOIN objects o ON o.cad_number = li.cad_number "
        "WHERE li.lot_id = ? ORDER BY li.ord, li.cad_number",
        (lot_id,),
    ))

    parts: list[str] = []
    parts.append(f"# Приложение к лоту {lot_id}\n")
    parts.append(f"**{lot['name']}**\n")

    parts.append("## Параметры процедуры\n")
    parts.append(_kv_table([
        ("Идентификатор лота", lot["lot_id"]),
        ("Тип сделки", lot["deal_type"] or "не указан"),
        ("Тип процедуры", lot["procedure_type"] or "не указан"),
        ("Целевые ЭТП", _format_platforms(lot["platform_targets"])),
        ("Основной КН", lot["primary_cad_number"] or "—"),
        ("Дата формирования лота", lot["created_at"] or "—"),
    ]))

    parts.append("## Состав лота\n")
    if items:
        parts.append("| № | Кадастровый номер | Роль | Тип ЕГРН | Адрес | Площадь (м²) |")
        parts.append("|---|---|---|---|---|---|")
        for row in items:
            parts.append(
                f"| {row['ord']} | {row['cad_number']} | {row['role']} | "
                f"{row['object_type'] or '—'} | {_escape(row['address']) or '—'} | "
                f"{_format_area(row['area'])} |"
            )
        parts.append("")
    else:
        parts.append("_Состав лота не задан._\n")

    if lot["notes_md"]:
        parts.append("## Пометки экономиста\n")
        parts.append(lot["notes_md"])
        parts.append("")

    parts.append("## Документы\n")
    parts.append(
        "Подробные сведения об объектах лота — в составе документации:\n\n"
        "- Отчёт об оценке (см. файлы документации лота на ЭТП).\n"
        "- Техническая документация (техпаспорта, техпланы, выписки ЕГРН).\n"
        "- Правоустанавливающие документы.\n"
    )

    return "\n".join(parts).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kv_table(rows: list[tuple[str, Any]]) -> str:
    out = ["| Параметр | Значение |", "|---|---|"]
    for k, v in rows:
        out.append(f"| {k} | {_escape(v)} |")
    out.append("")
    return "\n".join(out)


def _format_platforms(raw_json: str | None) -> str:
    if not raw_json:
        return "—"
    try:
        items = json.loads(raw_json)
    except (TypeError, ValueError):
        return raw_json
    if isinstance(items, list) and items:
        return ", ".join(str(x) for x in items)
    return "—"


def _format_area(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))


def _escape(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("|", "\\|")
