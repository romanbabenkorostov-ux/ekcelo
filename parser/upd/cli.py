# -*- coding: utf-8 -*-
"""ekcelo · CLI для валидатора УПД-XML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.upd import validator


def _cmd_validate(args: argparse.Namespace) -> int:
    errs = validator.validate(args.xml.expanduser(),
                               args.xsd.expanduser() if args.xsd else None)
    if not errs:
        print(f"✓ Валидация прошла: {args.xml}")
        return 0
    print(f"✗ Ошибки валидации ({len(errs)}):", file=sys.stderr)
    for e in errs:
        print(f"    • {e}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="parser.upd",
        description="ekcelo · валидатор УПД-XML по XSD ФНС",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_v = sub.add_parser("validate", help="валидировать UPD-XML")
    p_v.add_argument("xml", type=Path)
    p_v.add_argument("--xsd", type=Path, default=None,
                     help="путь к ON_NSCHFDOPPR_*.xsd (по умолчанию — bundled)")
    p_v.set_defaults(func=_cmd_validate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
