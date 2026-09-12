"""tests/test_html_report.py — отчёт из БД: граф, хронология, эссе.

Данные проверяются словарём (`build_report_data`), вёрстка — отдельно, наличием
опорных элементов в HTML. Разделение намеренное: сборка данных — это логика,
которую надо сторожить построчно, а разметка ломается иначе и заметна глазом.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.exporters import html_report as R                # noqa: E402
from egrn_parser.parsers import manual_contours as M              # noqa: E402
from egrn_parser.parsers import xml_geometry_db as W              # noqa: E402
from egrn_parser.parsers.xml_geometry import extract_geometry     # noqa: E402
from tests.test_xml_geometry import land_xml                      # noqa: E402

CAD = "26:29:130106:382"


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    """База как после полного прохода: геометрия, карточка, права, ЗОУИТ."""
    connection = sqlite3.connect(":memory:")
    path = tmp_path / "extract.xml"
    path.write_text(land_xml(), encoding="utf-8")
    W.write_geometry(connection, extract_geometry(path),
                     extract_number="КУВИ-001/2026-1", extract_date="2026-09-07")
    connection.executescript("""
        CREATE TABLE land_objects (cad_number TEXT PRIMARY KEY, address TEXT,
            area REAL, land_category TEXT, permitted_uses TEXT,
            cadastral_value REAL, lifecycle_status_text TEXT,
            registration_date TEXT, object_restrictions TEXT);
        CREATE TABLE rights (right_id INTEGER PRIMARY KEY, object_key_value TEXT,
            right_type TEXT, right_number TEXT, right_date TEXT,
            right_category TEXT, beneficiary_name TEXT, beneficiary_inn TEXT,
            basis TEXT, is_active INTEGER);
        CREATE TABLE right_holders (right_id INTEGER, name TEXT, inn TEXT,
            holder_type TEXT);
        CREATE TABLE extracts (cad_number TEXT, extract_number TEXT,
            extract_date TEXT, extract_template TEXT);
    """)
    connection.execute(
        "INSERT INTO land_objects VALUES (?, 'Ставрополье, Предгорный МО', 1986.0, "
        "'Земли населенных пунктов', 'Для сельхозпроизводства', 15550.38, "
        "'актуальные', '2023-03-10 08:59:03', ?)",
        (CAD, json.dumps([{"registry_number": "26:29-6.395",
                           "description": "Охранная зона ЛЭП"}], ensure_ascii=False)))
    connection.execute(
        "INSERT INTO rights VALUES (1, ?, 'Собственность', '26:29-26/109/2024-3', "
        "'2024-03-16', 'right', NULL, NULL, NULL, 1)", (CAD,))
    connection.execute(
        "INSERT INTO rights VALUES (2, ?, 'Ипотека', '26:29-26/109/2024-4', "
        "'2024-05-20', 'encumbrance', 'ПАО Банк, ОГРН: 1027700000000, адрес', "
        "'7707083893', 'Договор залога № 5', 1)", (CAD,))
    connection.execute("INSERT INTO right_holders VALUES (1, NULL, NULL, 'individual')")
    connection.execute(
        "INSERT INTO extracts VALUES (?, 'КУВИ-001/2026-1', '2026-09-07', 'full')", (CAD,))
    connection.commit()
    yield connection
    connection.close()


# --- граф -----------------------------------------------------------------

def test_graph_has_object_right_encumbrance_and_zone(conn):
    data = R.build_report_data(conn, generated_on="2026-09-12")
    types = {node["type"] for node in data["graph"]["nodes"]}
    assert "Земельный участок" in types
    assert "Право" in types
    assert "Обременение" in types
    assert "Ограничение (ЗОУИТ)" in types
    assert "Часть ЗУ" in types


def test_right_and_encumbrance_are_not_merged(conn):
    """Разные типы узлов и разные рёбра: одно говорит чей объект, другое — что нельзя."""
    data = R.build_report_data(conn)
    kinds = {edge["kind"] for edge in data["graph"]["edges"]}
    assert "right" in kinds and "encumbrance" in kinds
    right_node = next(n for n in data["graph"]["nodes"] if n["type"] == "Право")
    encumbrance = next(n for n in data["graph"]["nodes"] if n["type"] == "Обременение")
    assert right_node["color"] != encumbrance["color"]


def test_individual_holder_is_anonymous(conn):
    """Физлицо в графе — «Физическое лицо», без ФИО и без СНИЛС."""
    data = R.build_report_data(conn)
    holders = [n for n in data["graph"]["nodes"] if n["kind"] == "holder"]
    assert any(h["label"] == "Физическое лицо" for h in holders)


def test_legal_beneficiary_is_named_without_contacts(conn):
    """ЮЛ называется (публично по ЕГРЮЛ), но без адреса и ОГРН из слипшейся строки."""
    data = R.build_report_data(conn)
    labels = [n["label"] for n in data["graph"]["nodes"] if n["kind"] == "holder"]
    assert "ПАО Банк" in labels
    assert not any("адрес" in label for label in labels)


def test_categories_are_added_as_hexagons(conn):
    data = R.build_report_data(conn)
    categories = [n for n in data["graph"]["nodes"] if n["kind"] == "category"]
    assert categories
    assert all(n["shape"] == "hexagon" for n in categories)
    assert {"Объекты", "Права", "Обременения"} <= {n["label"] for n in categories}


def test_every_edge_points_to_existing_node(conn):
    data = R.build_report_data(conn)
    ids = {n["id"] for n in data["graph"]["nodes"]}
    for edge in data["graph"]["edges"]:
        assert edge["from"] in ids and edge["to"] in ids


def test_colors_match_the_other_graph_of_the_system(conn):
    """Один тип объекта обязан выглядеть одинаково в обоих графах системы."""
    assert R.TYPE_COLORS["Земельный участок"]["bg"] == "#7fc97f"
    assert R.TYPE_COLORS["Право"]["bg"] == "#6baed6"
    assert R.TYPE_COLORS["Обременение"]["bg"] == "#3182bd"


# --- хронология -----------------------------------------------------------

def test_timeline_is_sorted_and_typed(conn):
    events = R.build_report_data(conn)["timeline"]
    assert events == sorted(events, key=lambda e: (e["date"], e["cad_number"], e["title"]))
    labels = {e["label"] for e in events}
    assert {"Объект", "Право", "Обременение", "Выписка", "Контур"} <= labels


def test_timeline_covers_registration_rights_and_contour(conn):
    events = R.build_report_data(conn)["timeline"]
    dates = {e["date"]: e["title"] for e in events}
    assert dates["2023-03-10"] == "Поставлен на кадастровый учёт"
    assert dates["2024-03-16"] == "Собственность"
    assert dates["2024-05-20"] == "Ипотека"
    assert "2026-09-07" in dates


def test_events_without_date_are_dropped(conn):
    """«Неизвестно когда» на шкале времени изображается только враньём."""
    conn.execute("INSERT INTO rights VALUES (3, ?, 'Аренда', NULL, NULL, 'right', "
                 "NULL, NULL, NULL, 1)", (CAD,))
    events = R.build_report_data(conn)["timeline"]
    assert all(e["date"] for e in events)
    assert not any(e["title"] == "Аренда" for e in events)


def test_contour_conflict_appears_in_timeline(conn, tmp_path):
    kml = tmp_path / "ручные.kml"
    ring = [(42.8098, 43.9713), (42.8115, 43.9713), (42.8115, 43.9719)]
    coords = " ".join(f"{lon},{lat}" for lon, lat in ring)
    kml.write_text('<?xml version="1.0" encoding="UTF-8"?>'
                   '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
                   f"<name>{CAD}</name><Polygon><outerBoundaryIs><LinearRing>"
                   f"<coordinates>{coords}</coordinates></LinearRing>"
                   "</outerBoundaryIs></Polygon></Placemark></Document></kml>",
                   encoding="utf-8")
    M.import_manual_contours(conn, M.load_contours(kml))
    M.detect_conflicts(conn)
    titles = {e["title"] for e in R.build_report_data(conn)["timeline"]}
    assert "В выписке появился уточнённый контур" in titles
    assert "Ручная обводка" in titles


# --- эссе -----------------------------------------------------------------

def test_essays_carry_markdown_and_html(conn):
    essays = R.build_report_data(conn)["essays"]
    assert len(essays) == 1
    assert essays[0]["markdown"].startswith("# Земельный участок")
    assert "<h2>" in essays[0]["html"] and "<table>" in essays[0]["html"]


def test_markdown_conversion_covers_what_essay_emits():
    html = R._markdown_to_html(
        "# Заголовок\n\n## Раздел\n\n**жирный** и *курсив*\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n- пункт\n\n> цитата\n")
    assert "<h2>Заголовок</h2>" in html
    assert "<h3>Раздел</h3>" in html
    assert "<strong>жирный</strong>" in html and "<em>курсив</em>" in html
    assert "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>" \
        in html.replace("\n", "")
    assert "<ul><li>пункт</li></ul>" in html
    assert "<blockquote>цитата</blockquote>" in html


def test_markdown_escapes_html_from_data():
    """В адресе или названии может оказаться «<», и это не разметка."""
    html = R._markdown_to_html("Объект <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --- документ -------------------------------------------------------------

def test_html_has_three_tabs_and_no_cdn_when_inlined(conn):
    html = R.build_html(conn, generated_on="2026-09-12")
    assert html.lstrip().startswith("<!doctype html>")
    for tab in ("Права и ограничения", "Хронология", "Эссе"):
        assert tab in html
    assert 'id="panel-graph"' in html and 'id="panel-time"' in html \
        and 'id="panel-essay"' in html
    # Отчёт открывают на объекте, где сети может не быть.
    assert R.VIS_CDN not in html
    assert "vis-network" in html


def test_html_falls_back_to_cdn_when_asked(conn):
    html = R.build_html(conn, inline_vis=False, generated_on="2026-09-12")
    assert R.VIS_CDN in html


def test_html_embeds_markdown_for_download(conn):
    """Кнопка отдаёт исходный .md, значит он обязан быть в файле."""
    html = R.build_html(conn, generated_on="2026-09-12")
    assert "essay-download" in html
    assert "Земельный участок" in html
    assert '"markdown"' in html


def test_report_is_deterministic(conn):
    first = R.build_html(conn, generated_on="2026-09-12")
    second = R.build_html(conn, generated_on="2026-09-12")
    assert first == second


def test_filter_by_cad_number(conn):
    data = R.build_report_data(conn, cad_number=CAD)
    assert [o["cad_number"] for o in data["objects"]] == [CAD]
    assert R.build_report_data(conn, cad_number="26:29:000000:1")["objects"] == []


def test_export_writes_file(conn, tmp_path):
    path = R.export_html_report(
        conn, tmp_path / "out" / R.report_filename(None, "2026-09-12"),
        generated_on="2026-09-12")
    assert path.exists() and path.name == "Отчёт_ЕГРН_2026-09-12.html"


def test_empty_db_gives_valid_page():
    connection = sqlite3.connect(":memory:")
    W.ensure_schema(connection)
    html = R.build_html(connection, generated_on="2026-09-12")
    assert "<!doctype html>" in html
    assert "нет объектов" in html
    connection.close()
