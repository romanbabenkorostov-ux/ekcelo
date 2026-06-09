"""
egrn_parser/parsers/egrul_egrip_pipeline.py — связка источников ЕГРЮЛ/ЕГРИП.

Автораспознаёт входной файл (ФНС-XML / PDF), извлекает нормализованную запись,
по ИНН опционально дотягивает данные из checko/dadata и сливает в одну запись
по приоритету источника (`egrul_egrip_normalized.merge_records`).

Типичный сценарий экономиста: на руках PDF-выписка → отсюда берём ИНН/ОГРН
(offline, без ключа) → если задан ключ checko/dadata, обогащаем
руководителями/учредителями → единая запись.

CLI (JSON — в stdout, сводка/статусы — в stderr):
    python -m egrn_parser.parsers.egrul_egrip_pipeline ВЫПИСКА.pdf
    python -m egrn_parser.parsers.egrul_egrip_pipeline ВЫПИСКА.pdf --enrich checko
    python -m egrn_parser.parsers.egrul_egrip_pipeline ВЫПИСКА.pdf --enrich checko --db ekcelo.sqlite
    # --db без пути → пишет в ekcelo.sqlite в текущей папке
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from egrn_parser.parsers import egrul_egrip_parser as XML
from egrn_parser.parsers import egrul_egrip_pdf as PDF
from egrn_parser.parsers import egrul_egrip_sources as SRC
from egrn_parser.parsers.egrul_egrip_normalized import merge_records

log = logging.getLogger(__name__)


def parse_any(path: Path | str) -> dict[str, Any]:
    """Распарсить выписку, автоопределив тип файла (XML ФНС или PDF).

    Возвращает {format, records}. Бросает ValueError, если не опознано.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xml" or XML.is_fns_reestr_xml(path):
        return XML.parse(path)
    if suffix == ".pdf":
        return PDF.parse_pdf(path)
    # .txt и прочее — пробуем как текст PDF-выписки
    return PDF.parse_text(path.read_text(encoding="utf-8"), file=path.name)


def enrich_record(record: dict[str, Any], *, vendor: str = "checko") -> dict[str, Any]:
    """Обогатить запись по её ИНН из checko/dadata и слить (источник-приоритет).

    Если у записи нет ИНН или нет ключа — возвращает исходную запись
    (с пометкой в `source.enrich_error`), в сеть без ключа не ходит.
    """
    inn = (record.get("subject") or {}).get("inn")
    if not inn:
        record.setdefault("source", {})["enrich_error"] = "нет ИНН для обогащения"
        return record
    try:
        ext = SRC.fetch_by_inn(inn, vendor=vendor)["records"][0]
    except Exception as exc:  # noqa: BLE001 — нет ключа / сети / ИНН не найден
        log.warning("enrich(%s) по ИНН %s не удалось: %s", vendor, inn, exc)
        record.setdefault("source", {})["enrich_error"] = str(exc)
        return record
    return merge_records([record, ext])  # запись (XML/PDF) приоритетнее checko/dadata


def run(path: Path | str, *, enrich: Optional[str] = None) -> dict[str, Any]:
    """Полный проход: parse_any → (опц.) enrich → запись(и)."""
    out = parse_any(path)
    if enrich:
        out["records"] = [enrich_record(r, vendor=enrich) for r in out["records"]]
    return out


# Дефолтная БД, если --db указан без пути.
DEFAULT_DB = "ekcelo.sqlite"


def write_to_db(records: list[dict[str, Any]], db_path: str) -> list[dict[str, Any]]:
    """Записать subject'ы в entity_registry указанной SQLite (создаёт таблицу при нужде)."""
    import sqlite3
    from egrn_parser.parsers import egrul_egrip_db as DB
    with sqlite3.connect(db_path) as conn:
        return DB.upsert_records(conn, records)


def _summary(record: dict[str, Any]) -> str:
    s = record.get("subject") or {}
    ident = s.get("inn") or s.get("ogrnip") or s.get("ogrn") or "—"
    name = s.get("name_full") or "/".join(
        filter(None, (s.get("fio") or {}).values())) or "—"
    return f"{record.get('registry')} · ИНН {ident} · {name}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="egrul_egrip_pipeline",
        description="Парсинг выписки ЕГРЮЛ/ЕГРИП (XML/PDF) + опц. обогащение по ИНН")
    ap.add_argument("file", help="путь к выписке (.xml ФНС или .pdf)")
    ap.add_argument("--enrich", choices=["checko", "dadata"], default=None,
                    help="дотянуть данные по ИНН из источника (нужен ключ в parser/.env)")
    ap.add_argument("--db", nargs="?", const=DEFAULT_DB, default=None,
                    metavar="PATH",
                    help=f"записать subject'ы в entity_registry SQLite-БД "
                         f"(без аргумента — {DEFAULT_DB} в текущей папке)")
    ap.add_argument("-o", "--out", help="записать JSON в файл (по умолчанию — stdout)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
        result = run(args.file, enrich=args.enrich)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    # Краткая сводка по каждому субъекту (в stderr, чтобы не мешать JSON в stdout).
    for rec in result["records"]:
        print(_summary(rec), file=sys.stderr)

    if args.db:
        actions = write_to_db(result["records"], args.db)
        for a in actions:
            print(f"БД {args.db}: {a['action']} {a.get('inn') or a.get('reason') or ''}".rstrip(),
                  file=sys.stderr)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"JSON записан: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
