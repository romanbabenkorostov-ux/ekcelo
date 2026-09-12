"""
egrn_parser/geo_pipeline.py — выписки → SQLite → KML + эссе + описание схемы.

ОДНА ФУНКЦИЯ НА ВЕСЬ ПРОХОД. Шаги по отдельности уже есть: `xml_parser` даёт
карточку, права и ограничения; `xml_geometry` — контуры; `xml_geometry_db` —
запись; экспортёры — вывод. Склеивать их каждый раз заново пришлось бы и в CLI,
и в графической оболочке, и в тестах — три места, где порядок шагов разъедется.
Поэтому порядок зафиксирован здесь, а CLI и окно только показывают результат.

ПОРЯДОК ШАГОВ НЕ ПРОИЗВОЛЕН. Сначала карточка (`save_parsed_result`), потом
геометрия. Наоборот нельзя: эссе и подписи KML берут категорию земель, адрес и
кадастровую стоимость из `land_objects`, и при обратном порядке первый прогон
выдал бы контуры без единой характеристики — формально верный результат,
который человек прочтёт как «в выписке ничего нет».

ПРОГРЕСС ОТДАЁТСЯ CALLBACK'ОМ, А НЕ ПЕЧАТЬЮ. В окне нужен прогресс-бар, в
консоли — строки, в тесте — ничего. `on_step` решает это одним аргументом,
не заводя в модуле ни print, ни зависимости от Qt.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from egrn_parser.parsers import manual_contours as _manual
from egrn_parser.parsers import xml_geometry_db as _geo_db
from egrn_parser.parsers.xml_geometry import extract_geometry

log = logging.getLogger(__name__)

__all__ = ["FileResult", "PipelineResult", "run_pipeline", "collect_xml"]

ProgressFn = Callable[[str], None]


@dataclass
class FileResult:
    """Итог по одному файлу — и для строки в консоли, и для строки в таблице окна."""

    path: Path
    cad_number: Optional[str] = None
    object_type: Optional[str] = None
    card_saved: bool = False
    geometry_written: bool = False
    contours: int = 0
    parts: int = 0
    area_check: Optional[str] = None
    note: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def describe(self) -> str:
        if self.error:
            return f"✗ {self.path.name}: {self.error}"
        head = self.cad_number or self.path.name
        if self.geometry_written:
            return (f"✓ {head}: контуров {self.contours}, ЧЗУ {self.parts}"
                    + (f"; {self.area_check}" if self.area_check else ""))
        return f"· {head}: {self.note or 'геометрия не записана'}"


@dataclass
class PipelineResult:
    db_path: Path
    files: list[FileResult] = field(default_factory=list)
    kml_path: Optional[Path] = None
    essays: list[Path] = field(default_factory=list)
    schema_doc: Optional[Path] = None
    html_report: Optional[Path] = None
    # Объекты, у которых ручная обводка встретилась с контуром из выписки.
    # Проход их НЕ решает: он обязан их показать (ADR-008).
    conflicts: list[dict] = field(default_factory=list)

    @property
    def written(self) -> int:
        return sum(1 for f in self.files if f.geometry_written)

    @property
    def failed(self) -> int:
        return sum(1 for f in self.files if f.error)

    def summary(self) -> str:
        text = (f"файлов: {len(self.files)}; с геометрией: {self.written}; "
                f"ошибок: {self.failed}; контуров: "
                f"{sum(f.contours for f in self.files)}; ЧЗУ: "
                f"{sum(f.parts for f in self.files)}")
        if self.conflicts:
            text += f"; КОНФЛИКТОВ КОНТУРА: {len(self.conflicts)}"
        return text


def collect_xml(target: Path | str) -> list[Path]:
    """Файл или папка → список XML-выписок.

    Подписи (`*.xml.sig`) отсеиваются: рядом с каждой выпиской Роскадастр
    кладёт файл ЭП, и попытка разобрать его как выписку даёт бессмысленную
    ошибку в отчёте на ровном месте.
    """
    path = Path(target)
    if path.is_file():
        return [path] if path.suffix.lower() == ".xml" else []
    return sorted(p for p in path.rglob("*.xml")
                  if p.is_file() and not p.name.lower().endswith(".sig"))


def _ensure_parser_schema(db_path: Path, say: ProgressFn) -> None:
    """Создать схему парсера, если её в базе нет.

    `save_parsed_result` пишет в `extracts`, `land_objects`, `rights` — таблицы
    из `db/schema.sql`. База, созданная одной только миграцией 0006 (так делает
    `01d`), их не содержит, и карточка падала бы на каждом файле с «no such
    table: extracts». Инициализация идемпотентна: схема вся на
    `CREATE TABLE IF NOT EXISTS`.
    """
    try:
        from egrn_parser.db.connection import check_db, init_db
    except Exception as exc:                                   # noqa: BLE001
        say(f"Схема парсера не создана ({exc}) — карточки будут пропущены")
        return
    if check_db(db_path):
        return
    try:
        init_db(db_path)
        say(f"Создана БД {db_path.name} по схеме парсера")
    except Exception as exc:                                   # noqa: BLE001
        say(f"Не удалось создать схему парсера: {exc}")


def _save_card(db_path: Path, xml_path: Path, result: FileResult) -> None:
    """Карточка, права и ограничения через существующий путь парсера.

    Импорт локальный: `xml_parser` тянет `pdf_parser`, а тот — `pdfplumber`.
    Геометрия от него не зависит, и падение тяжёлой зависимости не должно
    уносить с собой весь проход — поэтому карточка пропускается с пометкой,
    а контуры пишутся всё равно.
    """
    try:
        from egrn_parser.merge.upsert import save_parsed_result
        from egrn_parser.parsers.xml_parser import parse_egrn_xml
    except Exception as exc:                                   # noqa: BLE001
        result.note = f"карточка пропущена: {exc}"
        return

    try:
        parsed = parse_egrn_xml(xml_path)
        if not parsed:
            result.note = "карточка: файл не распознан как выписка ЕГРН"
            return
        save_parsed_result(db_path, parsed, policy="replace")
        result.card_saved = True
        result.object_type = parsed.get("object_type")
    except Exception as exc:                                   # noqa: BLE001
        log.warning("%s: карточка не сохранена — %s", xml_path.name, exc)
        result.note = f"карточка не сохранена: {exc}"


def run_pipeline(source: Path | str, db_path: Path | str, *,
                 out_dir: Path | str | None = None,
                 make_kml: bool = True,
                 make_essays: bool = True,
                 make_schema_doc: bool = True,
                 make_html: bool = True,
                 with_parts: bool = True,
                 force: bool = False,
                 skip_card: bool = False,
                 generated_on: Optional[str] = None,
                 on_step: Optional[ProgressFn] = None) -> PipelineResult:
    """Прогнать выписки от файлов до готовых выгрузок."""
    from egrn_parser.exporters import (essay_md, html_report,
                                       kml_exporter, schema_doc)

    say: ProgressFn = on_step or (lambda _msg: None)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir) if out_dir else db_path.parent
    day = generated_on or date.today().isoformat()

    if not skip_card:
        _ensure_parser_schema(db_path, say)

    files = collect_xml(source)
    result = PipelineResult(db_path=db_path)
    say(f"Найдено XML: {len(files)}")

    for xml_path in files:
        item = FileResult(path=xml_path)
        result.files.append(item)
        try:
            if not skip_card:
                _save_card(db_path, xml_path, item)

            geometry = extract_geometry(xml_path)
            item.cad_number = geometry.cad_number
            item.object_type = item.object_type or geometry.object_type

            with sqlite3.connect(db_path) as conn:
                report = _geo_db.write_geometry(conn, geometry, strict=not force)
            item.geometry_written = report["written"]
            item.contours = report["contours"]
            item.parts = report["parts"]
            item.area_check = report["area_check"]
            if not report["written"]:
                item.note = report["skipped"]
        except Exception as exc:                               # noqa: BLE001
            item.error = str(exc)
            log.exception("%s: не обработан", xml_path)
        say(item.describe())

    with sqlite3.connect(db_path) as conn:
        # Встреча ручной обводки с контуром из выписки — событие, о котором
        # человек обязан узнать до того, как посмотрит на выгрузку: в KML и
        # эссе пойдёт ТЕКУЩИЙ контур, а какой он — решает не проход.
        result.conflicts = _manual.detect_conflicts(conn)
        for conflict in result.conflicts:
            say(f"⚠ {conflict['message']}")
        pending = _manual.open_conflicts(conn)
        if pending:
            say(f"Ждут решения человека: {len(pending)} "
                "(оставить исходный / заменить на уточнённый)")

        # Схема §8 создаётся до выгрузок, а не только при первой записи
        # контура. Иначе папка из одних выписок на ОКС (геометрии в них нет
        # вовсе) роняет экспорт на «no such table: egrn_contour» — при том что
        # проход отработал верно и показывать просто нечего.
        _geo_db.ensure_schema(conn)

        if make_kml:
            kml = kml_exporter.build_kml(conn, with_parts=with_parts,
                                         generated_on=day)
            # Пустой KML не пишется: файл с нулём Placemark выглядит как
            # «выгрузка прошла», а на деле показывать нечего.
            if "<Placemark>" in kml:
                path = Path(out_dir) / kml_exporter.kml_filename(None, day)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(kml, encoding="utf-8")
                result.kml_path = path
                say(f"KML: {path.name}")
            else:
                say("KML не создан — в базе нет контуров")

        if make_essays:
            for cad in essay_md.list_objects(conn):
                path = essay_md.export_essay(
                    conn, cad, Path(out_dir) / essay_md.essay_filename(cad, day))
                result.essays.append(path)
            say(f"Эссе: {len(result.essays)}")

        if make_html:
            # Отчёт собирается ПОСЛЕ эссе: третья вкладка показывает их текст,
            # и собранный раньше отчёт показал бы вчерашние.
            path = html_report.export_html_report(
                conn, Path(out_dir) / html_report.report_filename(None, day),
                generated_on=day)
            result.html_report = path
            say(f"Отчёт HTML: {path.name}")

        if make_schema_doc:
            path = schema_doc.export_schema_doc(
                conn, Path(out_dir) / "Схема_БД.md",
                db_name=db_path.name, generated_on=day)
            result.schema_doc = path
            say(f"Описание схемы: {path.name}")

    say(result.summary())
    return result
