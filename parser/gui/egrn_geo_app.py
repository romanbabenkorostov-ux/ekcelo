"""
gui/egrn_geo_app.py — окно разбора выписок ЕГРН: XML → SQLite → KML + эссе.

ЗАЧЕМ ОКНО, ЕСЛИ ЕСТЬ CLI. Выписки приходят к экономисту, а не к разработчику:
папка на 40 файлов, из них половина — подписи ЭП, и нужно получить базу, KML на
телефон и текст для отчёта. Консольная строка с четырьмя флагами для этого не
годится, а ошибиться в ней — легко.

ОТКУДА ВЗЯТ ВНЕШНИЙ ВИД. Дизайн-код EkceloFotoMakeInvent (PySide6, та же
экосистема): тёплая бежево-коричневая тема, `BTN_CSS` для нейтральных действий
и `GREEN_CSS` для главного, скругление 6px, вкладки с номером в заголовке
(«1. Разбор выписок»), тяжёлая работа — в `QRunnable` с сигналами, а не в
UI-потоке. Новых цветов здесь не изобретается: каждый взят из той палитры по
смыслу.

ЧЕГО ОКНО НЕ ДЕЛАЕТ САМО. Ни строчки разбора здесь нет — всё уходит в
`egrn_parser.geo_pipeline.run_pipeline`. Причина простая: логика, написанная
внутри обработчика кнопки, не тестируется и не переиспользуется, а этот проход
уже вызывается из CLI (`scripts/01e_egrn_pipeline.py`) и из тестов. Окно —
только выбор путей, прогресс и показ результата.

ПОЧЕМУ СВЕТОФОР В ТАБЛИЦЕ ИМЕННО ТАКОЙ. Красным (`#c0392b`) помечается
несошедшаяся площадь, охрой (`#c9a227`) — записанный принудительно контур и
низкая точность, зелёным (`#2e8b57`) — норма. Это те же STATUS_COLORS, что в
EkceloFotoMakeInvent и в веб-дашборде: человек, работающий с обоими, читает
цвет не задумываясь.

Запуск:
    python -m gui.egrn_geo_app          (из каталога parser/)
    python parser/gui/egrn_geo_app.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_PARSER_ROOT = Path(__file__).resolve().parents[1]
if str(_PARSER_ROOT) not in sys.path:
    sys.path.insert(0, str(_PARSER_ROOT))

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from egrn_parser.geo_pipeline import PipelineResult, collect_xml, run_pipeline

APP_TITLE = "Ekcelo — выписки ЕГРН: контуры, KML, эссе"

# Палитра — дизайн-код EkceloFotoMakeInvent. Новых цветов не добавляем.
BTN_CSS = ("QPushButton{background:#6b5b3e;color:#fff;border:none;border-radius:6px;"
           "padding:7px 12px;}QPushButton:hover{background:#7d6b48;}"
           "QPushButton:disabled{background:#9a948a;color:#eee;}")
GREEN_CSS = ("QPushButton{background:#2e8b57;color:#fff;border:none;border-radius:6px;"
             "padding:7px 12px;}QPushButton:hover{background:#37a164;}"
             "QPushButton:disabled{background:#9a948a;color:#eee;}")

COLOR_OK = "#2e8b57"        # норма
COLOR_WARN = "#c9a227"      # требует внимания
COLOR_BAD = "#c0392b"       # площадь не сошлась
COLOR_MUTED = "#777"


class PipelineSignals(QObject):
    """Сигналы фоновой задачи (паттерн XxxSignals/XxxWorker из дизайн-кода)."""

    step = Signal(str)
    done = Signal(object)
    failed = Signal(str)


class PipelineWorker(QRunnable):
    """Проход в пуле потоков: UI не должен замирать на сорока выписках."""

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.signals = PipelineSignals()
        self._kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            result = run_pipeline(on_step=self.signals.step.emit, **self._kwargs)
        except Exception as exc:                               # noqa: BLE001
            self.signals.failed.emit(str(exc))
            return
        self.signals.done.emit(result)


def _button(text: str, css: str = BTN_CSS) -> QPushButton:
    button = QPushButton(text)
    button.setStyleSheet(css)
    return button


def _title(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont()
    font.setPointSize(15)
    font.setBold(True)
    label.setFont(font)
    return label


class RunTab(QWidget):
    """Вкладка «1. Разбор выписок» — выбор путей, запуск, журнал."""

    finished = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._pool = QThreadPool.globalInstance()
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(_title("Разбор выписок ЕГРН"))
        layout.addWidget(QLabel(
            "Папка с XML-выписками Росреестра. Файлы подписи (.sig) и PDF "
            "пропускаются сами."))

        paths = QGroupBox("Пути")
        paths_layout = QVBoxLayout(paths)
        self.ed_source = QLineEdit()
        self.ed_source.setPlaceholderText("Папка с выписками или один .xml")
        self.ed_db = QLineEdit()
        self.ed_db.setPlaceholderText("Файл базы, например egrn.db")
        self.ed_out = QLineEdit()
        self.ed_out.setPlaceholderText("Куда складывать KML и эссе "
                                       "(по умолчанию — рядом с базой)")
        for label, edit, handler in (
                ("Выписки", self.ed_source, self._pick_source),
                ("База", self.ed_db, self._pick_db),
                ("Выгрузки", self.ed_out, self._pick_out)):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            caption = QLabel(label)
            caption.setMinimumWidth(80)
            row_layout.addWidget(caption)
            row_layout.addWidget(edit, 1)
            browse = _button("Выбрать…")
            browse.clicked.connect(handler)
            row_layout.addWidget(browse)
            paths_layout.addWidget(row)
        layout.addWidget(paths)

        options = QGroupBox("Что делать")
        options_layout = QVBoxLayout(options)
        self.cb_kml = QCheckBox("Создать KML с контурами")
        self.cb_essays = QCheckBox("Написать эссе по каждому объекту (.md)")
        self.cb_schema = QCheckBox("Обновить описание схемы БД (.md)")
        self.cb_parts = QCheckBox("Показывать в KML части участка (ЧЗУ)")
        for box in (self.cb_kml, self.cb_essays, self.cb_schema, self.cb_parts):
            box.setChecked(True)
            options_layout.addWidget(box)
        self.cb_force = QCheckBox(
            "Записывать контур, даже если площадь не сошлась с выпиской")
        # Снятая по умолчанию галка — это и есть гейт ADR-007 §3. Подпись
        # объясняет цену: расхождение почти всегда означает неверную зону МСК,
        # и контур ляжет не туда, оставаясь правдоподобным.
        self.cb_force.setStyleSheet(f"color:{COLOR_WARN};")
        self.cb_force.setToolTip(
            "Расхождение площади обычно означает, что параметры местной системы "
            "координат определены неверно. Контур при этом выглядит нормально, "
            "но лежит не на месте. Включайте, только если разобрались в причине.")
        options_layout.addWidget(self.cb_force)
        layout.addWidget(options)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_run = _button("Разобрать", GREEN_CSS)
        self.btn_run.clicked.connect(self._run)
        self.btn_open = _button("Открыть папку с выгрузками")
        self.btn_open.clicked.connect(self._open_out)
        self.btn_open.setEnabled(False)
        buttons_layout.addWidget(self.btn_run)
        buttons_layout.addWidget(self.btn_open)
        buttons_layout.addStretch(1)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-weight:bold;")
        buttons_layout.addWidget(self.lbl_status)
        layout.addWidget(buttons)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-size:11px;color:#333;")
        layout.addWidget(self.log, 1)

    # --- выбор путей ------------------------------------------------------

    def _pick_source(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Папка с выписками")
        if chosen:
            self.ed_source.setText(chosen)
            if not self.ed_db.text():
                self.ed_db.setText(str(Path(chosen) / "egrn.db"))

    def _pick_db(self) -> None:
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Файл базы", self.ed_db.text() or "egrn.db", "SQLite (*.db)")
        if chosen:
            self.ed_db.setText(chosen)

    def _pick_out(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Папка для выгрузок")
        if chosen:
            self.ed_out.setText(chosen)

    # --- запуск -----------------------------------------------------------

    def _run(self) -> None:
        source = self.ed_source.text().strip()
        db_path = self.ed_db.text().strip()
        if not source or not Path(source).exists():
            QMessageBox.warning(self, "Не указаны выписки",
                                "Выберите папку с XML-выписками или один файл.")
            return
        if not db_path:
            QMessageBox.warning(self, "Не указана база",
                                "Укажите, в какой файл писать базу.")
            return
        files = collect_xml(Path(source))
        if not files:
            QMessageBox.warning(self, "Выписок не найдено",
                                f"В {source} нет файлов .xml.")
            return

        self.log.clear()
        self.btn_run.setEnabled(False)
        self.lbl_status.setText("Идёт разбор…")
        self.lbl_status.setStyleSheet(f"font-weight:bold;color:{COLOR_WARN};")

        worker = PipelineWorker(
            source=Path(source), db_path=Path(db_path),
            out_dir=self.ed_out.text().strip() or None,
            make_kml=self.cb_kml.isChecked(),
            make_essays=self.cb_essays.isChecked(),
            make_schema_doc=self.cb_schema.isChecked(),
            with_parts=self.cb_parts.isChecked(),
            force=self.cb_force.isChecked())
        worker.signals.step.connect(self._on_step)
        worker.signals.done.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._pool.start(worker)

    @Slot(str)
    def _on_step(self, message: str) -> None:
        self.log.appendPlainText(message)

    @Slot(object)
    def _on_done(self, result: PipelineResult) -> None:
        self.btn_run.setEnabled(True)
        self.btn_open.setEnabled(True)
        colour = COLOR_BAD if result.failed else COLOR_OK
        self.lbl_status.setText(result.summary())
        self.lbl_status.setStyleSheet(f"font-weight:bold;color:{colour};")
        self._last_out = (result.kml_path or result.schema_doc
                          or result.db_path).parent
        self.finished.emit(result)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.btn_run.setEnabled(True)
        self.lbl_status.setText("Ошибка")
        self.lbl_status.setStyleSheet(f"font-weight:bold;color:{COLOR_BAD};")
        QMessageBox.critical(self, "Разбор не удался", message)

    def _open_out(self) -> None:
        target = getattr(self, "_last_out", None)
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


class ResultTab(QWidget):
    """Вкладка «2. Объекты» — что получилось, с проверкой площади в цвете."""

    def __init__(self) -> None:
        super().__init__()
        self._db_path: Path | None = None
        self._result: PipelineResult | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(_title("Объекты в базе"))
        self.lbl_hint = QLabel("Разберите выписки на первой вкладке.")
        self.lbl_hint.setStyleSheet(f"color:{COLOR_MUTED};")
        layout.addWidget(self.lbl_hint)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Кадастровый номер", "Контуров", "ЧЗУ", "Площадь по контуру, кв.м",
            "По выписке, кв.м", "Точность, м", "Сверка"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_kml = _button("Открыть KML")
        self.btn_kml.clicked.connect(lambda: self._open(self._result.kml_path
                                                        if self._result else None))
        self.btn_essay = _button("Открыть эссе выбранного объекта", GREEN_CSS)
        self.btn_essay.clicked.connect(self._open_essay)
        self.btn_schema = _button("Открыть описание схемы БД")
        self.btn_schema.clicked.connect(lambda: self._open(self._result.schema_doc
                                                           if self._result else None))
        for button in (self.btn_essay, self.btn_kml, self.btn_schema):
            button.setEnabled(False)
            buttons_layout.addWidget(button)
        buttons_layout.addStretch(1)
        layout.addWidget(buttons)

    @Slot(object)
    def on_result(self, result: PipelineResult) -> None:
        self._result = result
        self._db_path = result.db_path
        self.reload()
        self.btn_kml.setEnabled(bool(result.kml_path))
        self.btn_schema.setEnabled(bool(result.schema_doc))
        self.btn_essay.setEnabled(bool(result.essays))

    def reload(self) -> None:
        if not self._db_path or not Path(self._db_path).exists():
            return
        rows: list[tuple] = []
        with sqlite3.connect(self._db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT s.cad_number, s.contours, "
                    "       (SELECT COUNT(*) FROM egrn_contour p "
                    "         WHERE p.cad_number = s.cad_number AND p.kind='part'), "
                    "       s.area_computed_sqm, s.area_declared_sqm, s.accuracy_m, "
                    "       s.area_check_ok "
                    "  FROM v_egrn_geometry_summary s ORDER BY s.cad_number"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []

        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cad, contours, parts, computed, declared, accuracy, ok = row
            values = [
                cad, str(contours), str(parts),
                f"{computed:.1f}" if computed is not None else "—",
                f"{declared:.0f}" if declared is not None else "—",
                f"{accuracy:g}" if accuracy is not None else "—",
                "сходится" if ok else ("не сходится" if ok == 0 else "нет данных"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(index, column, item)
            # Светофор: тот же смысл цветов, что в STATUS_COLORS.
            if ok == 0:
                colour = COLOR_BAD
            elif accuracy is not None and accuracy >= 2.0:
                colour = COLOR_WARN
            else:
                colour = COLOR_OK
            self.table.item(index, 6).setForeground(QColor(colour))

        self.lbl_hint.setText(
            f"Объектов с геометрией: {len(rows)}. Красным — площадь не сошлась "
            "(проверьте зону МСК), охрой — низкая точность съёмки по выписке."
            if rows else "В базе пока нет объектов с геометрией.")

    def _selected_cad(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _open_essay(self) -> None:
        cad = self._selected_cad()
        if not cad or not self._result:
            QMessageBox.information(self, "Объект не выбран",
                                    "Выберите строку в таблице.")
            return
        needle = cad.replace(":", "-")
        for path in self._result.essays:
            if needle in path.name:
                self._open(path)
                return
        QMessageBox.information(self, "Эссе не найдено",
                                f"Для {cad} эссе не создавалось.")

    def _open(self, path: Path | None) -> None:
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class MainWindow(QWidget):
    """Сборка вкладок и связь между ними — только сигналами, как в дизайн-коде."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1060, 720)

        self.run_tab = RunTab()
        self.result_tab = ResultTab()
        self.run_tab.finished.connect(self.result_tab.on_result)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.run_tab, "1. Разбор выписок")
        self.tabs.addTab(self.result_tab, "2. Объекты")
        self.run_tab.finished.connect(lambda _r: self.tabs.setCurrentIndex(1))

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
