"""tests/test_essay_and_schema_doc.py — эссе по объекту и описание схемы БД.

Главное, что здесь сторожится, — не форматирование, а два обещания модулей:
эссе не выдумывает цифр и не раскрывает персональных данных, а описание схемы
не врёт про фактический состав базы.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.exporters import essay_md as E                  # noqa: E402
from egrn_parser.exporters import schema_doc as S                # noqa: E402
from egrn_parser.parsers import xml_geometry_db as W             # noqa: E402
from egrn_parser.parsers.xml_geometry import extract_geometry    # noqa: E402
from tests.test_xml_geometry import land_xml                     # noqa: E402

CAD = "26:29:130106:382"


def _with_geometry(tmp_path, xml: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    path = tmp_path / "extract.xml"
    path.write_text(xml or land_xml(), encoding="utf-8")
    W.write_geometry(conn, extract_geometry(path))
    return conn


def _with_card(tmp_path, **overrides) -> sqlite3.Connection:
    """Геометрия плюс карточка объекта — как после полного прохода."""
    conn = _with_geometry(tmp_path)
    conn.executescript(
        "CREATE TABLE land_objects (cad_number TEXT PRIMARY KEY, address TEXT, "
        "  area REAL, land_category TEXT, permitted_uses TEXT, "
        "  cadastral_value REAL, lifecycle_status_text TEXT, "
        "  registration_date TEXT, object_restrictions TEXT);")
    row = {
        "cad_number": CAD,
        "address": "Ставропольский край, Предгорный МО",
        "area": 1986.0,
        "land_category": "Земли населенных пунктов",
        "permitted_uses": "Для сельскохозяйственного производства",
        "cadastral_value": 15550.38,
        "lifecycle_status_text": "актуальные",
        "registration_date": "2023-03-10 08:59:03",
        "object_restrictions": None,
    }
    row.update(overrides)
    conn.execute(
        "INSERT INTO land_objects VALUES (:cad_number, :address, :area, "
        ":land_category, :permitted_uses, :cadastral_value, "
        ":lifecycle_status_text, :registration_date, :object_restrictions)", row)
    return conn


# --- эссе -----------------------------------------------------------------

def test_lists_objects_with_geometry(tmp_path):
    conn = _with_geometry(tmp_path)
    assert E.list_objects(conn) == [CAD]


def test_essay_states_area_check_explicitly(tmp_path):
    """Сверка площади обязана быть в тексте, а не только в базе."""
    text = E.build_essay(_with_geometry(tmp_path), CAD)
    assert "## Границы" in text
    assert "сходится с заявленной" in text
    assert "1985.6" in text and "1986" in text


def test_essay_warns_when_area_does_not_match(tmp_path):
    conn = _with_geometry(tmp_path)
    path = tmp_path / "bad.xml"
    path.write_text(land_xml(area="9000"), encoding="utf-8")
    W.write_geometry(conn, extract_geometry(path), strict=False)
    text = E.build_essay(conn, CAD)
    assert "**НЕ СХОДИТСЯ**" in text
    assert "требует проверки человеком" in text


def test_essay_reports_accuracy_class(tmp_path):
    text = E.build_essay(_with_geometry(tmp_path), CAD)
    assert "2.5 м" in text
    assert "пересчёт из ранее учтённых материалов" in text


def test_essay_separates_parts_from_parcel_area(tmp_path):
    text = E.build_essay(_with_geometry(tmp_path), CAD)
    assert "## Части участка (ЧЗУ)" in text
    assert "их площадь не прибавляется к его площади" in text


def test_essay_uses_card_when_present(tmp_path):
    text = E.build_essay(_with_card(tmp_path), CAD)
    assert "Земли населенных пунктов" in text
    assert "Для сельскохозяйственного производства" in text
    assert "₽" in text


def test_essay_survives_without_card(tmp_path):
    """База из одной геометрии — валидный случай, эссе не должно падать."""
    text = E.build_essay(_with_geometry(tmp_path), CAD)
    assert text.startswith(f"# Земельный участок {CAD}")
    assert "Категория земель | —" in text


def test_essay_area_is_not_mangled_by_trailing_zero_strip(tmp_path):
    """Регресс той же ошибки, что в KML: 15120 не должно стать 1512."""
    conn = _with_card(tmp_path, area=15120.0)
    assert "| Площадь | 15120 кв.м |" in E.build_essay(conn, CAD)


def test_essay_never_prints_personal_data(tmp_path):
    """Физлица не называются — ни ФИО, ни СНИЛС, ни паспорт."""
    conn = _with_card(tmp_path)
    conn.executescript(
        "CREATE TABLE rights (object_key_value TEXT, right_type TEXT, "
        "  right_number TEXT, right_date TEXT, right_category TEXT, is_active INT);"
        "CREATE TABLE right_holders (right_id INT, surname TEXT, snils TEXT);")
    conn.execute("INSERT INTO rights VALUES (?, 'Собственность', "
                 "'26:29:130106:382-26/109/2024-3', '2024-03-16', 'right', 1)", (CAD,))
    conn.execute("INSERT INTO right_holders VALUES (1, 'Иванов', '123-456-789 00')")
    text = E.build_essay(conn, CAD)
    assert "## Права" in text
    assert "Собственность" in text
    assert "Иванов" not in text
    assert "123-456-789" not in text


def test_essay_reads_restrictions_from_json_column(tmp_path):
    """Во внутренней схеме парсера ограничения — JSON, а не таблица."""
    payload = json.dumps([{"registry_number": "26:29-6.395",
                           "description": "Охранная зона ЛЭП"}], ensure_ascii=False)
    conn = _with_card(tmp_path, object_restrictions=payload)
    text = E.build_essay(conn, CAD)
    assert "26:29-6.395" in text
    assert "Охранная зона ЛЭП" in text


def test_essay_reads_restrictions_from_table(tmp_path):
    """В каноне (§5) те же сведения лежат отдельной таблицей."""
    conn = _with_card(tmp_path)
    conn.executescript(
        "CREATE TABLE object_restrictions (cad_number TEXT, registry_number TEXT, "
        "  description TEXT);")
    conn.execute("INSERT INTO object_restrictions VALUES (?, '26:33-6.94', "
                 "'Водоохранная зона')", (CAD,))
    assert "Водоохранная зона" in E.build_essay(conn, CAD)


def test_essay_is_deterministic(tmp_path):
    conn = _with_card(tmp_path)
    assert E.build_essay(conn, CAD) == E.build_essay(conn, CAD)


def test_export_essay_writes_file(tmp_path):
    conn = _with_geometry(tmp_path)
    path = E.export_essay(conn, CAD, tmp_path / "out" / E.essay_filename(CAD, "2026-09-12"))
    assert path.exists()
    assert path.name == "Эссе_26-29-130106-382_2026-09-12.md"
    assert path.read_text(encoding="utf-8").startswith("# Земельный участок")


# --- описание схемы -------------------------------------------------------

def test_schema_doc_reflects_actual_tables(tmp_path):
    conn = _with_card(tmp_path)
    text = S.build_schema_doc(conn, db_name="test.db", generated_on="2026-09-12")
    assert "`egrn_contour`" in text
    assert "`land_objects`" in text
    assert "`v_egrn_parcel_contour`" in text


def test_schema_doc_counts_rows(tmp_path):
    conn = _with_geometry(tmp_path)
    text = S.build_schema_doc(conn, generated_on="2026-09-12")
    assert "Строк на момент снятия: **2**." in text


def test_schema_doc_carries_human_notes(tmp_path):
    """Отпечаток без пояснений бесполезен — ключевые заметки должны быть."""
    text = S.build_schema_doc(_with_geometry(tmp_path), generated_on="2026-09-12")
    assert "складывать нельзя" in text
    assert "ADR-007" in text


def test_schema_doc_does_not_invent_notes_for_unknown_tables(tmp_path):
    conn = _with_geometry(tmp_path)
    conn.executescript("CREATE TABLE самописная_таблица (id INTEGER);")
    text = S.build_schema_doc(conn, generated_on="2026-09-12")
    assert "## Прочие таблицы и представления" in text
    assert "`самописная_таблица`" in text


def test_schema_doc_is_deterministic(tmp_path):
    conn = _with_geometry(tmp_path)
    first = S.build_schema_doc(conn, generated_on="2026-09-12")
    second = S.build_schema_doc(conn, generated_on="2026-09-12")
    assert first == second


def test_schema_doc_lists_sources_of_truth(tmp_path):
    text = S.build_schema_doc(_with_geometry(tmp_path), generated_on="2026-09-12")
    assert "schema/egrn_current_schema.sql" in text
    assert "obsidian/Database/*.md" in text


def test_export_schema_doc_writes_file(tmp_path):
    conn = _with_geometry(tmp_path)
    path = S.export_schema_doc(conn, tmp_path / "out" / "Схема_БД.md",
                               generated_on="2026-09-12")
    assert path.exists() and path.read_text(encoding="utf-8").startswith("# Схема БД")
