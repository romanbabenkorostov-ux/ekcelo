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
    """КН, по которым есть о чём писать: геометрия либо карточка объекта.

    Геометрии одной недостаточно: выписка на здание её не содержит вовсе
    (свойство формата, см. ADR-007), а эссе по зданию нужно не меньше, чем по
    участку. Поэтому список собирается из трёх источников, с дедупликацией.
    """
    found: list[str] = []
    for sql in ("SELECT DISTINCT cad_number FROM egrn_contour",
                "SELECT cad_number FROM land_objects",
                "SELECT cad_number FROM building_objects"):
        found.extend(r[0] for r in _rows(conn, sql) if r[0])
    return sorted(set(found))


# Карточка объекта лежит в одной из двух таблиц: земля в `land_objects`, всё
# остальное (здание, помещение, сооружение, ОНС) — в `building_objects`. Набор
# колонок у них разный, поэтому запрос свой на каждую, а не один «универсальный»
# с COALESCE по несуществующим полям.
_LAND_SQL = ("SELECT address, area, land_category, permitted_uses, "
             "       cadastral_value, lifecycle_status_text, registration_date, "
             "       NULL, NULL, NULL, NULL "
             "  FROM land_objects WHERE cad_number = ?")
_BUILD_SQL = ("SELECT address, area, NULL, NULL, "
              "       cadastral_value, lifecycle_status_text, registration_date, "
              "       name, purpose, object_type, old_numbers "
              "  FROM building_objects WHERE cad_number = ?")
_FACT_KEYS = ("address", "area", "land_category", "permitted_uses",
              "cadastral_value", "status", "registration_date",
              "name", "purpose", "object_type", "old_numbers")

# Как называть объект в заголовке эссе.
OBJECT_TITLES = {
    "land": "Земельный участок",
    "building": "Здание",
    "room": "Помещение",
    "construction": "Сооружение",
    "ons": "Объект незавершённого строительства",
    "parking": "Машино-место",
}


def _object_facts(conn: sqlite3.Connection, cad: str) -> dict[str, Any]:
    for sql, kind in ((_LAND_SQL, "land"), (_BUILD_SQL, None)):
        row = _row(conn, sql, cad)
        if row:
            facts = dict(zip(_FACT_KEYS, row))
            facts["object_type"] = facts.get("object_type") or kind or "building"
            return facts
    return {}


def _summary(conn: sqlite3.Connection, cad: str) -> dict[str, Any]:
    row = _row(conn,
               "SELECT contours, area_computed_sqm, area_declared_sqm, accuracy_m, "
               "       msk_zone, source_extract_number, extract_date, area_check_ok "
               "  FROM v_egrn_geometry_summary WHERE cad_number = ?", cad)
    keys = ("contours", "area_computed", "area_declared", "accuracy", "zone",
            "extract_number", "extract_date", "area_ok")
    return dict(zip(keys, row)) if row else {}


def _extract_requisites(conn: sqlite3.Connection, cad: str,
                        summary: dict) -> tuple[Optional[str], Optional[str]]:
    """Номер и дата выписки.

    У объекта с геометрией они уже лежат в §8. У здания геометрии нет вовсе, но
    выписка была — её реквизиты хранит таблица `extracts`. Без этого шага эссе
    по зданию печатало «Выписка: — от —», хотя документ в базе есть.
    """
    if summary.get("extract_number") or summary.get("extract_date"):
        return summary.get("extract_number"), summary.get("extract_date")
    row = _row(conn, "SELECT extract_number, extract_date FROM extracts "
                     " WHERE cad_number = ? ORDER BY extract_date DESC LIMIT 1", cad)
    return (row[0], row[1]) if row else (None, None)


def _header(cad: str, facts: dict, summary: dict) -> list[str]:
    title = OBJECT_TITLES.get(facts.get("object_type") or "land", "Объект недвижимости")
    lines = [f"# {title} {cad}", ""]
    if facts.get("name"):
        lines += [f"*{facts['name']}*", ""]
    if facts.get("address"):
        lines += [f"**Адрес:** {facts['address']}", ""]
    number, day = summary.get("_extract_number"), summary.get("_extract_date")
    if number or day:
        lines += [f"**Выписка:** {number or '—'} от {day or '—'}", ""]
    return lines


def _characteristics(facts: dict, summary: dict) -> list[str]:
    """Таблица характеристик. Строки без значения не выводятся вовсе.

    У здания нет категории земель, у участка — назначения; печатать их с
    прочерком значит заставлять читателя проверять, не потерялись ли данные.
    """
    declared = facts.get("area") or summary.get("area_declared")
    rows = [
        ("Площадь", f"{_num(declared, 0)} кв.м" if declared else None),
        ("Назначение", facts.get("purpose")),
        ("Категория земель", facts.get("land_category")),
        ("Разрешённое использование", facts.get("permitted_uses")),
        ("Кадастровая стоимость", _money(facts.get("cadastral_value"))
         if facts.get("cadastral_value") else None),
        ("Статус сведений", facts.get("status")),
        ("Дата постановки на учёт", (facts.get("registration_date") or "")[:10] or None),
        ("Прежние номера", facts.get("old_numbers")),
    ]
    visible = [(name, value) for name, value in rows if value]
    if not visible:
        return []
    return (["## Характеристики по выписке", "", "| Показатель | Значение |", "|---|---|"]
            + [f"| {name} | {value} |" for name, value in visible] + [""])


def _borders(conn: sqlite3.Connection, cad: str, summary: dict) -> list[str]:
    """Раздел о границах. Стоит раньше прав — см. преамбулу модуля."""
    # Признак «геометрии нет» — отсутствие КОНТУРОВ, а не пустота `summary`:
    # в него перед вызовом кладутся реквизиты выписки, и проверка на пустой
    # словарь молча уводила раздел в ветку «геометрия есть», где все значения
    # None — заголовок печатался, текст исчезал.
    if not summary.get("contours"):
        return ["## Границы", "",
                "Контура по этому объекту в базе нет. Для зданий и помещений это "
                "штатно: выписка на объект капитального строительства координат "
                "не содержит — они берутся у земельного участка под ним.", ""]

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


# Обязательные колонки `rights` и те, которых в старой базе может не быть.
# Запрос собирается по факту: одна отсутствующая колонка не должна уносить с
# собой весь раздел «Права» — раздел молча исчезал бы, и заметить это можно
# было бы только сверив эссе с выпиской.
_RIGHT_REQUIRED = ("right_type", "right_number", "right_date", "right_category")
_RIGHT_OPTIONAL = ("beneficiary_name", "beneficiary_inn", "basis")


def _right_rows(conn: sqlite3.Connection, cad: str) -> list[dict]:
    try:
        present = {r[1] for r in conn.execute("PRAGMA table_info(rights)")}
    except sqlite3.OperationalError:
        return []
    if not present:
        return []
    columns = [c for c in _RIGHT_REQUIRED + _RIGHT_OPTIONAL if c in present]
    if "right_type" not in columns:
        return []
    order = "right_category, right_date" if "right_category" in present else "right_date"
    rows = _rows(conn, f"SELECT {', '.join(columns)} FROM rights "
                       f" WHERE object_key_value = ? AND is_active = 1 "
                       f" ORDER BY {order}", cad)
    return [dict(zip(columns, row)) for row in rows]


def _beneficiary(name: Optional[str], inn: Optional[str]) -> Optional[str]:
    """Кто выгодоприобретатель обременения.

    Юридические лица называются: они публичны по ЕГРЮЛ, и без них обременение
    нечитаемо («в пользу кого залог?»). Поле в базе часто хранит слипшуюся
    строку с ИНН, ОГРН, почтой и адресом — в эссе идёт только имя и ИНН,
    остальное это контактные данные, которым в отчёте не место.
    """
    if not name:
        return f"ИНН {inn}" if inn else None
    head = name.split(",")[0].strip()
    if inn and inn in head:
        head = f"ИНН {inn}"
    elif inn:
        head = f"{head} (ИНН {inn})"
    return head or None


def _rights(conn: sqlite3.Connection, cad: str) -> list[str]:
    """Права. Физлица не называются — см. преамбулу модуля.

    Права и обременения разводятся по разным разделам намеренно: «Собственность»
    и «Запрещение регистрации» в одной таблице читаются как однородные записи,
    хотя одна говорит, чей объект, а другая — что с ним нельзя сделать.
    """
    owned = [r for r in _right_rows(conn, cad)
             if (r.get("right_category") or "right") == "right"]
    if not owned:
        return []
    lines = ["## Права", "",
             "| Вид права | Номер регистрации | Дата |", "|---|---|---|"]
    for row in owned:
        lines.append(f"| {row.get('right_type') or '—'} | "
                     f"{row.get('right_number') or '—'} | "
                     f"{(row.get('right_date') or '—')[:10]} |")
    lines += ["", "> Сведения о правообладателях-физических лицах в эссе не "
                  "приводятся: это персональные данные.", ""]
    return lines


def _encumbrances(conn: sqlite3.Connection, cad: str) -> list[str]:
    """Обременения и ограничения прав из реестра прав (не путать с ЗОУИТ)."""
    rows = [r for r in _right_rows(conn, cad)
            if (r.get("right_category") or "right") in ("encumbrance", "restriction")]
    if not rows:
        return []
    lines = ["## Обременения и ограничения прав", "",
             f"Зарегистрировано записей: **{len(rows)}**.", ""]
    for row in rows:
        head = f"**{row.get('right_type') or 'Обременение'}**"
        right_date = row.get("right_date")
        details = [f"№ {row['right_number']}" if row.get("right_number") else None,
                   f"от {right_date[:10]}" if right_date else None]
        who = _beneficiary(row.get("beneficiary_name"), row.get("beneficiary_inn"))
        if who:
            details.append(f"в пользу: {who}")
        if row.get("basis"):
            details.append(f"основание: {row['basis']}")
        tail = "; ".join(d for d in details if d)
        lines.append(f"- {head} — {tail}" if tail else f"- {head}")
    lines.append("")
    return lines


def _sources(summary: dict, cad: str) -> list[str]:
    number = summary.get("_extract_number")
    day = summary.get("_extract_date")
    document = (f"выписки ЕГРН {number}" if number else "выписки ЕГРН")
    if day:
        document += f" от {day}"
    lines = ["## Источник сведений", "",
             f"Все сведения выше взяты из {document} на объект {cad}."]
    # Абзац про пересчёт координат пишется только там, где координаты были.
    # У здания их нет, и обещание «сверено по площади» было бы неправдой.
    if summary.get("contours"):
        lines.append(
            "Геометрия извлечена из XML-раздела выписки, пересчитана из местной "
            "системы координат в WGS-84 и сверена по площади с той же выпиской.")
    return lines + [
        "",
        "Эссе сформировано автоматически из базы; оценочных суждений не содержит.",
        "",
    ]


def build_essay(conn: sqlite3.Connection, cad_number: str) -> str:
    """Собрать эссе по одному объекту. Детерминировано: только данные из БД."""
    facts = _object_facts(conn, cad_number)
    summary = _summary(conn, cad_number)
    number, day = _extract_requisites(conn, cad_number, summary)
    summary["_extract_number"], summary["_extract_date"] = number, day
    lines: list[str] = []
    lines += _header(cad_number, facts, summary)
    lines += _characteristics(facts, summary)
    lines += _borders(conn, cad_number, summary)
    lines += _parts(conn, cad_number)
    lines += _restrictions(conn, cad_number)
    lines += _rights(conn, cad_number)
    lines += _encumbrances(conn, cad_number)
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
