"""tests/test_gui_smoke.py — окно разбора выписок доходит до результата.

PySide6 в зависимостях парсера нет (оболочка ставится отдельно), поэтому тест
пропускается там, где Qt не установлен. Там, где установлен, он проверяет не
внешний вид, а то единственное, что может сломаться незаметно: что окно
действительно вызывает проход, дожидается фонового потока и показывает
результат — а не молча остаётся пустым.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.test_xml_geometry import BUILD_XML, land_xml          # noqa: E402

pytest.importorskip("PySide6", reason="графическая оболочка ставится отдельно")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def inbox(tmp_path) -> Path:
    folder = tmp_path / "Выписки"
    folder.mkdir()
    (folder / "land.xml").write_text(land_xml(), encoding="utf-8")
    (folder / "build.xml").write_text(BUILD_XML, encoding="utf-8")
    (folder / "land.xml.sig").write_text("подпись", encoding="utf-8")
    return folder


def _run_window(window, timeout_ms: int = 60000):
    """Запустить проход и подождать сигнал `finished`, крутя цикл событий."""
    from PySide6.QtCore import QEventLoop, QTimer

    done: dict = {}
    window.run_tab.finished.connect(lambda result: done.setdefault("result", result))
    window.run_tab._run()
    loop = QEventLoop()
    ticker = QTimer()
    ticker.timeout.connect(lambda: loop.quit() if "result" in done else None)
    ticker.start(50)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return done.get("result")


def test_tabs_are_numbered_as_in_design_code(app):
    from gui.egrn_geo_app import MainWindow
    window = MainWindow()
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["1. Разбор выписок", "2. Объекты", "3. Контуры"]


def test_area_gate_is_off_by_default_in_ui(app):
    """Галка «писать при несошедшейся площади» снята — это и есть гейт ADR-007."""
    from gui.egrn_geo_app import MainWindow
    window = MainWindow()
    assert not window.run_tab.cb_force.isChecked()
    assert window.run_tab.cb_kml.isChecked()
    assert window.run_tab.cb_essays.isChecked()
    assert window.run_tab.cb_schema.isChecked()


def test_window_runs_pipeline_and_fills_table(app, inbox, tmp_path):
    from gui.egrn_geo_app import MainWindow
    window = MainWindow()
    window.run_tab.ed_source.setText(str(inbox))
    window.run_tab.ed_db.setText(str(tmp_path / "egrn.db"))
    window.run_tab.ed_out.setText(str(tmp_path / "выгрузка"))

    result = _run_window(window)
    assert result is not None, "окно не дождалось фонового прохода"
    assert result.written == 1
    assert result.kml_path and result.kml_path.exists()

    log = window.run_tab.log.toPlainText()
    assert "Найдено XML: 2" in log
    assert "нет геометрии" in log, "выписка на ОКС должна попасть в журнал"

    table = window.result_tab.table
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "26:29:130106:382"
    assert table.item(0, 6).text() == "сходится"
    assert window.tabs.currentIndex() == 1, "после прогона показываем результат"


def test_mismatched_area_is_marked_red(app, tmp_path):
    """Цвет — тот же, что в STATUS_COLORS: несошедшаяся площадь красным."""
    from gui.egrn_geo_app import MainWindow
    folder = tmp_path / "плохая_зона"
    folder.mkdir()
    (folder / "land.xml").write_text(land_xml(area="9000"), encoding="utf-8")

    window = MainWindow()
    window.run_tab.ed_source.setText(str(folder))
    window.run_tab.ed_db.setText(str(tmp_path / "egrn.db"))
    window.run_tab.cb_force.setChecked(True)      # иначе писать было бы нечего

    assert _run_window(window) is not None
    table = window.result_tab.table
    assert table.rowCount() == 1
    assert table.item(0, 6).text() == "не сходится"
    assert table.item(0, 6).foreground().color().name() == "#c0392b"


# --- вкладка «3. Контуры» -------------------------------------------------

def _rough_kml(cad: str = "26:29:130106:382") -> str:
    ring = [(42.8098, 43.9713), (42.8115, 43.9713),
            (42.8115, 43.9719), (42.8098, 43.9719)]
    coords = " ".join(f"{lon},{lat}" for lon, lat in ring)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
            f"<name>{cad} примерно</name><Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{coords}</coordinates>"
            "</LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>")


def test_conflict_sends_user_to_contour_tab(app, inbox, tmp_path):
    """Появился уточнённый контур — человека ведём туда, где это решается."""
    import sqlite3

    from egrn_parser.parsers import manual_contours as manual
    from gui.egrn_geo_app import MainWindow

    db = tmp_path / "egrn.db"
    kml = tmp_path / "ручные.kml"
    kml.write_text(_rough_kml(), encoding="utf-8")
    with sqlite3.connect(db) as conn:
        manual.import_manual_contours(conn, manual.load_contours(kml, author="Бабенко"))

    window = MainWindow()
    window.run_tab.ed_source.setText(str(inbox))
    window.run_tab.ed_db.setText(str(db))
    result = _run_window(window)

    assert result is not None and result.conflicts, "конфликт должен быть обнаружен"
    assert window.tabs.currentIndex() == 2
    assert window.contour_tab.table.rowCount() == 1
    assert window.contour_tab.table.item(0, 0).text() == "26:29:130106:382"
    assert window.contour_tab.btn_keep.isEnabled()
    assert window.contour_tab.btn_use.isEnabled()


def test_resolution_from_window_switches_current_contour(app, inbox, tmp_path):
    import sqlite3

    from egrn_parser.parsers import manual_contours as manual
    from gui.egrn_geo_app import MainWindow

    db = tmp_path / "egrn.db"
    kml = tmp_path / "ручные.kml"
    kml.write_text(_rough_kml(), encoding="utf-8")
    with sqlite3.connect(db) as conn:
        manual.import_manual_contours(conn, manual.load_contours(kml))

    window = MainWindow()
    window.run_tab.ed_source.setText(str(inbox))
    window.run_tab.ed_db.setText(str(db))
    _run_window(window)

    window.contour_tab.table.setCurrentCell(0, 0)
    window.contour_tab._resolve("use_egrn")

    assert window.contour_tab.table.rowCount() == 0
    assert not window.contour_tab.btn_use.isEnabled()
    with sqlite3.connect(db) as conn:
        current = manual.current_contours(conn)
    assert [r["contour_source"] for r in current] == ["egrn"]
