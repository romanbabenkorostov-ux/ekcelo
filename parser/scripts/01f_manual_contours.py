"""
01f_manual_contours.py — ручные примерные контуры и разрешение конфликтов.

Продолжение линейки 01b–01e. Закрывает случай, которого в них нет: у объекта
контура ещё не существует — кадастровые инженеры до него не дошли, — а работать
надо уже сейчас. Экономист обводит участок примерно в Google Earth или
Яндекс.Конструкторе (кадастровый номер пишет в подпись метки) и подаёт файл
сюда.

Когда позже придёт выписка ЕГРН с настоящим контуром, скрипт (и любой прогон
01e) СКАЖЕТ об этом и предложит решение: оставить исходный или заменить на
уточнённый. Сам он не решает — ручная обводка могла уйти в подписанный акт, и
молча подменить её нельзя (ADR-008).

Usage:
  # загрузить обводки
  python 01f_manual_contours.py --db egrn.db --load ручные.kml --author Бабенко

  # посмотреть, что ждёт решения
  python 01f_manual_contours.py --db egrn.db --list-conflicts

  # решить
  python 01f_manual_contours.py --db egrn.db --resolve 26:29:130106:382 --keep-manual
  python 01f_manual_contours.py --db egrn.db --resolve 26:29:130106:382 --use-egrn

  # какой контур сейчас считается текущим
  python 01f_manual_contours.py --db egrn.db --current
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egrn_parser.parsers import manual_contours as M   # noqa: E402


def _print_conflicts(conflicts: list[dict]) -> None:
    for item in conflicts:
        print(f"  ⚠ {item['message']}")
        details = []
        if item.get("author"):
            details.append(f"обвёл: {item['author']}")
        if item.get("note"):
            details.append(f"пометка: {item['note']}")
        if item.get("confidence") is not None:
            details.append(f"уверенность обводки: {item['confidence']}")
        if details:
            print("      " + "; ".join(details))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="Путь к SQLite БД")
    ap.add_argument("--load", help="KML или GeoJSON с ручными контурами")
    ap.add_argument("--author", help="Кто обвёл — пригодится при споре через год")
    ap.add_argument("--note", help="Пометка: «по забору», «со слов арендатора»")
    ap.add_argument("--confidence", type=float, default=0.5,
                    help="Уверенность обводки 0..1 (0.3 — пальцем по карте)")
    ap.add_argument("--list-conflicts", action="store_true",
                    help="Показать, что ждёт решения человека")
    ap.add_argument("--current", action="store_true",
                    help="Какой контур сейчас считается текущим по объектам")
    ap.add_argument("--resolve", metavar="КН", help="Решить конфликт по объекту")
    ap.add_argument("--keep-manual", action="store_true",
                    help="Оставить исходную ручную обводку")
    ap.add_argument("--use-egrn", action="store_true",
                    help="Заменить на уточнённый контур из выписки")
    ap.add_argument("--resolved-by", help="Кто принял решение")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        if args.load:
            path = Path(args.load)
            if not path.exists():
                print(f"[!] не найдено: {path}")
                return 1
            contours = M.load_contours(
                path, author=args.author, note=args.note,
                confidence=args.confidence)
            if not contours:
                print(f"[!] в {path.name} нет полигонов с кадастровым номером "
                      "в подписи метки")
                return 1
            report = M.import_manual_contours(conn, contours)
            print(f"Ручные контуры: {report.summary()}")
            for cad, reason in report.skipped:
                print(f"  · {cad}: {reason}")
            if report.conflicts:
                print("\nПоявились контуры в выписках:")
                _print_conflicts(report.conflicts)

        if args.resolve:
            if args.keep_manual == args.use_egrn:
                print("[!] укажите ровно одно: --keep-manual или --use-egrn")
                return 1
            choice = "keep_manual" if args.keep_manual else "use_egrn"
            result = M.resolve_conflict(conn, args.resolve, choice,
                                        resolved_by=args.resolved_by)
            if result["resolved"]:
                what = ("оставлен исходный ручной контур" if choice == "keep_manual"
                        else "принят уточнённый контур из выписки")
                print(f"{args.resolve}: {what}")
            else:
                print(f"{args.resolve}: {result['reason']}")

        if args.list_conflicts:
            pending = M.open_conflicts(conn)
            if pending:
                print(f"Ждут решения: {len(pending)}")
                _print_conflicts(pending)
            else:
                print("Открытых конфликтов нет")

        if args.current:
            rows = M.current_contours(conn)
            if not rows:
                print("Контуров в базе нет")
            for row in rows:
                mark = ("выписка ЕГРН" if row["contour_source"] == "egrn"
                        else "ручная обводка")
                extra = (f", {row['land_layout']}" if row["land_layout"] else "")
                print(f"  {row['cad_number']}: {mark}, "
                      f"{row['area_computed_sqm']:.0f} кв.м{extra}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
