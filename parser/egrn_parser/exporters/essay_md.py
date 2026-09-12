"""
egrn_parser/exporters/essay_md.py — эссе по объекту из БД (Markdown).

ЗАЧЕМ НЕ LLM. Меморандум по лоту уже пишет `lot_orchestrator` — через модель, с
рыночным анализом и оценочными суждениями. Здесь задача другая: изложить то, что
СКАЗАНО В ВЫПИСКЕ, без единого слова от себя. Такой текст должен быть
воспроизводимым (два прогона на одной базе дают одинаковый файл), проверяемым
построчно и не должен уметь ошибаться в цифрах. Модель для этого — лишний риск
без выигрыша: все данные уже разобраны и лежат в таблицах.

ЧТО ЭССЕ ОБЯЗАНО ГОВОРИТЬ ВСЛУХ. Не только факты, но и их качество:

  • сошлась ли площадь по контуру с заявленной (и на сколько);
  • какова заявленная погрешность точек — 0.1 м и 2.5 м это разные документы,
    и решение «строить забор по этой границе» от них зависит;
  • из какой выписки и на какое число взята каждая цифра.

Умолчать об этом — значит выдать читателю уверенность, которой у данных нет.
Поэтому раздел «Границы» стоит раньше раздела «Права»: цифра площади без
оговорки о точности хуже, чем её отсутствие.

ЧЕГО ЗДЕСЬ НЕТ. Персональных данных правообладателей-физлиц: ФИО, СНИЛС,
паспорт, дата и место рождения в эссе не попадают никогда, даже если лежат в
базе. Для физлица пишется «Физическое лицо» и вид права — этого достаточно,
чтобы понять обременённость объекта, и недостаточно, чтобы его разгласить.
Юридические лица называются: они публичны по ЕГРЮЛ.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Optional

__all__ = ["build_essay", "export_essay", "essay_filename", "list_objects"]


def _num(value: Optional[float], digits: int = 1, default: str = "—") -> str:
    if value is None:
        return default
    text = f"{float(value):.{digits}f}"
    # Хвостовые нули срезаются ТОЛЬКО в дробной части: у целого «15120» такой
    # rstrip отрезает разряд и превращает участок в 1512 кв.м. Ошибка тихая —
    # число остаётся правдоподобным, и заметить её можно лишь сверив с выпиской.
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _money(value: Optional[float]) -> str:
    """Рубли с разделителями разрядов — иначе 11198325.6 не читается глазами."""
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def _row(conn: sqlite3.Connection, sql: str, *args) -> Optional[tuple]:
    try:
        return conn.execute(sql, args).fetchone()
    except sqlite3.OperationalError:
        return None


def _rows(conn: sqlite3.Connection, sql: str, *args) -> list[tuple]:
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []


def list_objects(conn: sqlite3.Connection) -> list[str]:
    """КН, по которым в базе есть геометрия — то есть есть о чём писать."""
    return [r[0] for r in _rows(
        conn, "SELECT DISTINCT cad_number FROM egrn_contour ORDER BY cad_number")]


def _object_facts(conn: sqlite3.Connection, cad: str) -> dict[str, Any]:
    row = _row(conn,
               "SELECT address, area, land_category, permitted_uses, "
               "       cadastral_value, lifecycle_status_text, registration_date "
               "  FROM land_objects WHERE cad_number = ?", cad)
    keys = ("address", "area", "land_category", "permitted_uses",
            "cadastral_value", "status", "registration_date")
    return dict(zip(keys, row)) if row else {}


def _summary(conn: sqlite3.Connection, cad: str) -> dict[str, Any]:
    row = _row(conn,
               "SELECT contours, area_computed_sqm, area_declared_sqm, accuracy_m, "
               "       msk_zone, source_extract_number, extract_date, area_check_ok "
               "  FROM v_egrn_geometry_summary WHERE cad_number = ?", cad)
    keys = ("contours", "area_computed", "area_declared", "accuracy", "zone",
            "extract_number", "extract_date", "area_ok")
    return dict(zip(keys, row)) if row else {}


def _header(cad: str, facts: dict, summary: dict) -> list[str]:
    lines = [f"# Земельный участок {cad}", ""]
    if facts.get("address"):
        lines += [f"**Адрес:** {facts['address']}", ""]
    lines += [
        f"**Выписка:** {summary.get('extract_number') or '—'}"
        f" от {summary.get('extract_date') or '—'}",
        "",
    ]
    return lines


def _characteristics(facts: dict, summary: dict) -> list[str]:
    declared = facts.get("area") or summary.get("area_declared")
    return [
        "## Характеристики по выписке",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| Площадь | {_num(declared, 0)} кв.м |",
        f"| Категория земель | {facts.get('land_category') or '—'} |",
        f"| Разрешённое использование | {facts.get('permitted_uses') or '—'} |",
        f"| Кадастровая стоимость | {_money(facts.get('cadastral_value'))} |",
        f"| Статус сведений | {facts.get('status') or '—'} |",
        f"| Дата постановки на учёт | {(facts.get('registration_date') or '—')[:10]} |",
        "",
    ]


def _borders(conn: sqlite3.Connection, cad: str, summary: dict) -> list[str]:
    """Раздел о границах. Стоит раньше прав — см. преамбулу модуля."""
    if not summary:
        return ["## Границы", "", "Геометрия по этому объекту в базе отсутствует.", ""]

    contours = _rows(conn,
                     "SELECT contour_no, contour_cad, area_computed_sqm, accuracy_m, "
                     "       centroid_lat, centroid_lon "
                     "  FROM v_egrn_parcel_contour WHERE cad_number = ? "
                     " ORDER BY contour_no", cad)

    lines = ["## Границы", ""]
    computed = summary.get("area_computed")
    declared = summary.get("area_declared")
    if declared is not None and computed is not None:
        delta = computed - declared
        verdict = ("сходится с заявленной" if summary.get("area_ok")
                   else "**НЕ СХОДИТСЯ** с заявленной")
        lines += [
            f"Площадь, вычисленная по координатам контура, — **{_num(computed)} кв.м**; "
            f"в выписке заявлено {_num(declared, 0)} кв.м. Расхождение "
            f"{delta:+.1f} кв.м — {verdict}.",
            "",
        ]
    if not summary.get("area_ok") and declared is not None:
        lines += [
            "> Расхождение такого размера обычно означает, что параметры местной "
            "системы координат определены неверно либо перепутаны оси. Контур "
            "записан в базу принудительно и требует проверки человеком.",
            "",
        ]

    accuracy = summary.get("accuracy")
    if accuracy is not None:
        # Классы точности не выдуманы: 0.1 м — инструментальная съёмка,
        # 2.5 м — пересчёт из старых материалов. Разница определяет, можно ли
        # по этой границе что-то строить.
        note = ("инструментальная съёмка" if accuracy <= 0.3
                else "пересчёт из ранее учтённых материалов" if accuracy >= 2.0
                else "средняя точность")
        lines += [
            f"Заявленная погрешность положения характерных точек — "
            f"**{_num(accuracy, 2)} м** ({note}). Это характеристика документа, "
            "а не результата пересчёта.",
            "",
        ]

    if summary.get("zone"):
        lines += [
            f"Координаты в выписке даны в системе `{summary['zone']}` и пересчитаны "
            "в WGS-84 для карты и KML.",
            "",
        ]

    if len(contours) > 1:
        lines += [f"Участок многоконтурный — контуров {len(contours)}:", "",
                  "| № | Обособленный участок | Площадь, кв.м | Центр (широта, долгота) |",
                  "|---|---|---|---|"]
        for no, child, area, _acc, lat, lon in contours:
            centre = f"{lat:.5f}, {lon:.5f}" if lat and lon else "—"
            lines.append(f"| {no} | {child or '—'} | {_num(area)} | {centre} |")
        lines.append("")
    elif contours:
        _no, _child, _area, _acc, lat, lon = contours[0]
        if lat and lon:
            lines += [f"Центр участка: **{lat:.5f}, {lon:.5f}** (WGS-84).", ""]
    return lines


def _parts(conn: sqlite3.Connection, cad: str) -> list[str]:
    rows = _rows(conn,
                 "SELECT part_number, part_mnemonic, area_computed_sqm, "
                 "       area_declared_sqm "
                 "  FROM egrn_contour WHERE cad_number = ? AND kind = 'part' "
                 " ORDER BY CAST(part_number AS INTEGER), part_number", cad)
    if not rows:
        return []
    total = sum(r[2] or 0 for r in rows)
    lines = [
        "## Части участка (ЧЗУ)",
        "",
        f"В выписке описано частей: **{len(rows)}**, суммарной площадью "
        f"{_num(total)} кв.м.",
        "",
        "| № | Зона | Площадь по контуру, кв.м | По выписке, кв.м |",
        "|---|---|---|---|",
    ]
    for number, mnemonic, computed, declared in rows:
        lines.append(f"| {number or '—'} | {mnemonic or '—'} | "
                     f"{_num(computed)} | {_num(declared, 0)} |")
    lines += [
        "",
        "> Части расположены **внутри** участка, их площадь не прибавляется к его "
        "площади. Обычно это охранные зоны инженерных сетей и водоохранные полосы: "
        "они ограничивают использование, но не уменьшают площадь.",
        "",
    ]
    return lines


def _restriction_items(conn: sqlite3.Connection, cad: str) -> list[tuple[str, str]]:
    """Ограничения как (реестровый номер, описание).

    Хранятся они в двух разных видах, и это не небрежность, а два поколения
    схемы: во внутренней схеме парсера это JSON-колонка
    `land_objects.object_restrictions`, в каноне (§5) — отдельная таблица
    `object_restrictions`. Эссе читают обе базы, поэтому пробуются оба места:
    сначала таблица (она нормализована и точнее), потом JSON.
    """
    rows = _rows(conn,
                 "SELECT registry_number, description FROM object_restrictions "
                 " WHERE cad_number = ? ORDER BY registry_number", cad)
    if rows:
        return [(r[0] or "", r[1] or "") for r in rows]

    row = _row(conn, "SELECT object_restrictions FROM land_objects "
                     " WHERE cad_number = ?", cad)
    if not row or not row[0]:
        return []
    try:
        payload = json.loads(row[0])
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    items = [(str(item.get("registry_number") or ""),
              str(item.get("description") or ""))
             for item in payload if isinstance(item, dict)]
    return sorted(items)


def _restrictions(conn: sqlite3.Connection, cad: str) -> list[str]:
    rows = _restriction_items(conn, cad)
    if not rows:
        return []
    lines = ["## Ограничения и обременения", "",
             f"Зарегистрировано ограничений: **{len(rows)}**.", ""]
    for registry, description in rows:
        head = f"**{registry}**" if registry else "**Без реестрового номера**"
        text = description.strip()
        lines.append(f"- {head} — {text}" if text else f"- {head}")
    lines += ["", "> Реестровый номер зоны связывает ограничение с частью "
                  "участка (ЧЗУ) из раздела выше: у части в мнемонике стоит тот "
                  "же номер.", ""]
    return lines


def _rights(conn: sqlite3.Connection, cad: str) -> list[str]:
    """Права. Физлица не называются — см. преамбулу модуля."""
    rows = _rows(conn,
                 "SELECT right_type, right_number, right_date, right_category "
                 "  FROM rights WHERE object_key_value = ? AND is_active = 1 "
                 " ORDER BY right_category, right_date", cad)
    if not rows:
        return []
    lines = ["## Права", "",
             "| Вид права | Номер регистрации | Дата |", "|---|---|---|"]
    for right_type, number, right_date, _category in rows:
        lines.append(f"| {right_type or '—'} | {number or '—'} | "
                     f"{(right_date or '—')[:10]} |")
    lines += ["", "> Сведения о правообладателях-физических лицах в эссе не "
                  "приводятся: это персональные данные.", ""]
    return lines


def _sources(summary: dict, cad: str) -> list[str]:
    files = summary.get("extract_number")
    return [
        "## Источник сведений",
        "",
        f"Все цифры выше взяты из выписки ЕГРН {files or '—'} "
        f"от {summary.get('extract_date') or '—'} на объект {cad}. "
        "Геометрия извлечена из XML-раздела выписки, пересчитана из местной "
        "системы координат в WGS-84 и сверена по площади с той же выпиской.",
        "",
        "Эссе сформировано автоматически из базы; оценочных суждений не содержит.",
        "",
    ]


def build_essay(conn: sqlite3.Connection, cad_number: str) -> str:
    """Собрать эссе по одному объекту. Детерминировано: только данные из БД."""
    facts = _object_facts(conn, cad_number)
    summary = _summary(conn, cad_number)
    lines: list[str] = []
    lines += _header(cad_number, facts, summary)
    lines += _characteristics(facts, summary)
    lines += _borders(conn, cad_number, summary)
    lines += _parts(conn, cad_number)
    lines += _restrictions(conn, cad_number)
    lines += _rights(conn, cad_number)
    lines += _sources(summary, cad_number)
    return "\n".join(lines)


def essay_filename(cad_number: str, day: Optional[str] = None) -> str:
    return (f"Эссе_{cad_number.replace(':', '-')}_"
            f"{day or date.today().isoformat()}.md")


def export_essay(conn: sqlite3.Connection, cad_number: str,
                 out_path: Path | str) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_essay(conn, cad_number), encoding="utf-8")
    return path
