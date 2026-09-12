"""
egrn_parser/exporters/schema_doc.py — описание схемы БД из самой БД (Markdown).

ЗАЧЕМ. Схема живёт в трёх местах: `schema/egrn_current_schema.sql` (канон),
`schema/migrations/*.sql` (как база до него дошла) и `parser/.../db/schema.sql`
(внутренняя схема парсера). Рядом лежит рукописная документация в
`obsidian/Database/`. Четыре источника расходятся — не сразу, а через полгода,
и первым это обнаруживает фронт.

Модуль снимает описание **с живой базы**: что в ней фактически есть сейчас.
Такой документ не может врать про существующие таблицы по определению — он не
рассказ о схеме, а её отпечаток.

ЧТО ОН НЕ ЗАМЕНЯЕТ. Рукописные заметки в `obsidian/Database/` объясняют
ПОЧЕМУ схема такая: почему §8 отделён от §7, почему площади ЧЗУ нельзя
складывать, почему ключ идемпотентности вынесен в выражение-индекс. Этого из
`PRAGMA table_info` не извлечь никогда. Поэтому генератор подтягивает
человеческие пояснения из `SECTION_NOTES` и ссылается на заметки, а не пытается
их заменить: отпечаток отвечает на «что есть», заметка — на «почему так».

Комментарии из DDL (`-- …`) сюда не тянутся намеренно: SQLite не хранит их
отдельно, вытаскивать их пришлось бы регулярками по `sqlite_master.sql`, а
регулярка по SQL — это способ получить неверное описание вместо отсутствующего.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

__all__ = ["build_schema_doc", "export_schema_doc", "SECTION_NOTES"]

# Разделы БД и что о них нужно знать человеку. Ключ — имя таблицы/представления.
# Всё, чего здесь нет, попадает в раздел «Прочие таблицы» без пояснения: лучше
# честный список без комментария, чем придуманный комментарий.
SECTION_NOTES: dict[str, str] = {
    "egrn_contour": (
        "§8, ADR-007. Контуры из XML-выписок ЕГРН — **часть слепка ЕГРН**, "
        "воспроизводится из тех же выписок. Строки `kind='parcel'` и "
        "`kind='part'` (ЧЗУ) лежат вместе, но их площади складывать нельзя: "
        "ЧЗУ находится внутри участка. Агрегировать через "
        "`v_egrn_parcel_contour`. Подробно — obsidian/Database/egrn-geometry-8.md"
    ),
    "v_egrn_parcel_contour": "Только контуры участка, без ЧЗУ. Точка входа для любой агрегации площади.",
    "v_egrn_geometry_summary": "Сводка по объекту: сошлась ли площадь контура с заявленной (`area_check_ok`).",
    "land_contours": "ADR-005. Раскладка ЗУ/МКУ/ЕЗП. Пишется и из выписок, и из НСПД/ПКК — источник в `geom_source`.",
    "land_objects": "Карточка земельного участка из выписки (§1).",
    "building_objects": "Карточка ОКС из выписки (§1).",
    "object_geometries": "Витрина текущей геометрии по объекту, читают `xlsx_exporter` и `graph_json`.",
    "rights": "Права и обременения (§3). Правообладатели — в `right_holders`.",
    "right_holders": "Правообладатели. **Персональные данные**: в выгрузки и эссе не попадают.",
    "entity_registry": "Реестр правообладателей-юрлиц (§2).",
    "object_restrictions": "Ограничения и обременения, ЗОУИТ (§5).",
    "extracts": "История выписок: какой документ какие сведения принёс (§4).",
    "object_etp_profile": "§6, ADR-001. Не-ЕГРН слой: ОСВ экономиста, EXIF, НСПД, LLM. Из выписок НЕ восстанавливается.",
    "geo_entity": "§7, ADR-002. Не-ЕГРН гео: ручная обводка, KMZ, НСПД. Из выписок НЕ восстанавливается.",
}

# Порядок разделов в документе: сначала то, ради чего база существует.
_ORDER = ["egrn_contour", "v_egrn_parcel_contour", "v_egrn_geometry_summary",
          "land_objects", "building_objects", "land_contours",
          "object_geometries", "rights", "right_holders", "entity_registry",
          "object_restrictions", "extracts"]


def _objects(conn: sqlite3.Connection, kind: str) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT name, COALESCE(sql, '') FROM sqlite_master "
        " WHERE type = ? AND name NOT LIKE 'sqlite_%' ORDER BY name", (kind,)
    ).fetchall()


def _columns(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return conn.execute(f'PRAGMA table_info("{table}")').fetchall()


def _row_count(conn: sqlite3.Connection, table: str) -> Optional[int]:
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.OperationalError:
        return None


def _indexes(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? "
        "  AND name NOT LIKE 'sqlite_%' ORDER BY name", (table,)).fetchall()
    return [r[0] for r in rows]


def _table_block(conn: sqlite3.Connection, table: str) -> list[str]:
    columns = _columns(conn, table)
    if not columns:
        return []
    count = _row_count(conn, table)
    lines = [f"### `{table}`", ""]
    note = SECTION_NOTES.get(table)
    if note:
        lines += [note, ""]
    lines += [f"Строк на момент снятия: **{count}**." if count is not None else "", ""]
    lines += ["| Колонка | Тип | NOT NULL | По умолчанию | PK |", "|---|---|---|---|---|"]
    for _cid, name, ctype, notnull, default, pk in columns:
        lines.append(f"| `{name}` | {ctype or '—'} | {'да' if notnull else ''} | "
                     f"{f'`{default}`' if default is not None else ''} | "
                     f"{'да' if pk else ''} |")
    lines.append("")
    indexes = _indexes(conn, table)
    if indexes:
        lines += ["Индексы: " + ", ".join(f"`{i}`" for i in indexes), ""]
    return lines


def _view_block(conn: sqlite3.Connection, view: str) -> list[str]:
    lines = [f"### `{view}` (представление)", ""]
    note = SECTION_NOTES.get(view)
    if note:
        lines += [note, ""]
    columns = _columns(conn, view)
    if columns:
        lines += ["Колонки: " + ", ".join(f"`{c[1]}`" for c in columns), ""]
    return lines


def build_schema_doc(conn: sqlite3.Connection, *, db_name: str = "",
                     generated_on: Optional[str] = None) -> str:
    """Снять описание схемы с живой базы.

    `generated_on` фиксируется отдельным аргументом, чтобы два прогона на
    неизменной базе давали одинаковый файл: документ кладут в git, и каждый
    прогон не должен порождать diff из одной строки с датой.
    """
    tables = [name for name, _ in _objects(conn, "table")]
    views = [name for name, _ in _objects(conn, "view")]
    known = [t for t in _ORDER if t in tables or t in views]
    rest = sorted(set(tables + views) - set(known))

    day = generated_on or date.today().isoformat()
    lines = [
        f"# Схема БД{f' — {db_name}' if db_name else ''}",
        "",
        f"Снято с базы {day} генератором `egrn_parser.exporters.schema_doc`. ",
        "Документ — **отпечаток** фактической схемы, а не её проект: он "
        "отвечает на вопрос «что в базе есть». На вопрос «почему схема такая» "
        "отвечают ADR и заметки в `obsidian/Database/` — их этот файл не "
        "заменяет и заменить не может.",
        "",
        f"Всего таблиц: **{len(tables)}**, представлений: **{len(views)}**.",
        "",
        "## Основные объекты",
        "",
    ]
    for name in known:
        lines += _view_block(conn, name) if name in views else _table_block(conn, name)

    if rest:
        lines += ["## Прочие таблицы и представления", "",
                  "Без пояснений — они не описаны в `SECTION_NOTES`. "
                  "Придуманный комментарий хуже отсутствующего.", ""]
        for name in rest:
            columns = _columns(conn, name)
            count = _row_count(conn, name)
            kind = "представление" if name in views else "таблица"
            lines.append(f"- `{name}` ({kind}, колонок {len(columns)}"
                         + (f", строк {count}" if count is not None else "") + ")")
        lines.append("")

    lines += [
        "## Источники правды",
        "",
        "| Файл | Что в нём |",
        "|---|---|",
        "| `schema/egrn_current_schema.sql` | канон схемы для Python и фронта |",
        "| `schema/migrations/*.sql` | как база дошла до текущего состояния |",
        "| `parser/egrn_parser/db/schema.sql` | внутренняя схема парсера |",
        "| `obsidian/Database/*.md` | почему схема такая |",
        "| этот файл | что в базе фактически есть сейчас |",
        "",
    ]
    return "\n".join(lines)


def export_schema_doc(conn: sqlite3.Connection, out_path: Path | str,
                      **kwargs) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_schema_doc(conn, **kwargs), encoding="utf-8")
    return path
