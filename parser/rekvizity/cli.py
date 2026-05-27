# -*- coding: utf-8 -*-
"""ekcelo · CLI для парсера реквизитов.

Подкоманды:
  ingest <file>... [--project <path>] [--force]
      Распарсить и сохранить реквизиты из одного или нескольких файлов.
  show <ИНН> [--source-history]
      Показать текущий canonical (или историю источников).
  list [--project <path>]
      Список ИНН в глобальном store / локальном проекте.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.rekvizity import store
from parser.rekvizity.parsers import detect_parser


def _cmd_ingest(args: argparse.Namespace) -> int:
    rc = 0
    for raw in args.files:
        path = Path(raw).expanduser()
        if not path.is_file():
            print(f"✗ Файл не найден: {path}", file=sys.stderr)
            rc = 1
            continue
        try:
            parser_fn = detect_parser(path)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            rc = 1
            continue
        try:
            fragment = parser_fn(path)
        except Exception as e:
            print(f"✗ Ошибка парсинга {path.name}: {e}", file=sys.stderr)
            rc = 1
            continue

        result = store.save(
            fragment,
            project=args.project.expanduser() if args.project else None,
            force=args.force,
        )
        if result["errors"]:
            print(f"⚠ {path.name}: предупреждения валидации:", file=sys.stderr)
            for err in result["errors"]:
                print(f"    • {err}", file=sys.stderr)

        if result["noop"]:
            print(f"  = {path.name}: уже актуально (no-op)")
        else:
            print(f"  ✓ {path.name}: inn={result['inn']}")
            print(f"    глобально: {result['global_path']}")
            if result["local_path"]:
                print(f"    локально:  {result['local_path']}")
    return rc


def _cmd_show(args: argparse.Namespace) -> int:
    rek = store.load_latest(args.inn)
    if rek is None:
        print(f"✗ Реквизитов для inn={args.inn} нет в store", file=sys.stderr)
        return 1
    if args.source_history:
        for src in rek.get("_sources") or []:
            print(f"  {src.get('ts'):<19}  {src.get('type'):<20}  {src.get('file')}")
        return 0
    print(json.dumps(rek, ensure_ascii=False, indent=2))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    inns = store.list_known(
        project=args.project.expanduser() if args.project else None
    )
    if not inns:
        print("(пусто)")
        return 0
    for inn in inns:
        print(inn)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="parser.rekvizity",
        description="ekcelo · парсер и хранилище реквизитов сторон договора",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="распарсить файл и сохранить")
    p_ing.add_argument("files", nargs="+", help="пути к .doc / .docx / .pdf")
    p_ing.add_argument("--project", type=Path, default=None,
                       help="папка проекта (для локального snapshot'а)")
    p_ing.add_argument("--force", action="store_true",
                       help="игнорировать idempotent-check (создать snapshot всегда)")
    p_ing.set_defaults(func=_cmd_ingest)

    p_show = sub.add_parser("show", help="показать canonical по ИНН")
    p_show.add_argument("inn")
    p_show.add_argument("--source-history", action="store_true",
                        help="вывести только историю источников")
    p_show.set_defaults(func=_cmd_show)

    p_list = sub.add_parser("list", help="список ИНН в store")
    p_list.add_argument("--project", type=Path, default=None)
    p_list.set_defaults(func=_cmd_list)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
