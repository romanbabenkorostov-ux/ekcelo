"""CLI `ekcelo-validate-bundle-db` — проверка db.sqlite Bundle против C2-контракта.

Реализует `SPEC_backend.md §P0.1` (sub-stage P0.1.2): standalone-валидатор для
парсер-команды. Позволяет проверить interchange-схему Bundle ДО отправки на
backend, без запуска импорта.

Принимает путь к:
- каталогу Bundle (ищет `db.sqlite` внутри), ИЛИ
- напрямую файлу `*.sqlite`.

Exit codes:
- 0 — соответствует контракту (или пусто нарушений).
- 2 — input-ошибка (путь не найден / нет db.sqlite).
- 3 — нарушения контракта (печатает список).

Использование:
    ekcelo-validate-bundle-db ./my-bundle/
    ekcelo-validate-bundle-db ./my-bundle/db.sqlite
    ekcelo-validate-bundle-db ./my-bundle/ --require-section6
    ekcelo-validate-bundle-db ./my-bundle/ --json

Регистрация: `pyproject.toml::[project.scripts]::ekcelo-validate-bundle-db`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _resolve_db_path(target: Path) -> Path | None:
    """Из каталога Bundle или прямого пути к sqlite вернуть путь к db.sqlite."""
    if target.is_dir():
        candidate = target / "db.sqlite"
        return candidate if candidate.is_file() else None
    if target.is_file():
        return target
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ekcelo-validate-bundle-db",
        description="Проверка db.sqlite Bundle против C2 DB-контракта "
                    "(contracts/db/schema.json).",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Каталог Bundle (ищет db.sqlite) или прямой путь к *.sqlite.",
    )
    parser.add_argument(
        "--require-section6",
        action="store_true",
        help="Требовать наличие §6 (ЭТП-профиль/лоты). По умолчанию §6 опционален.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON ({ok, db_path, violations}).",
    )
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.path)
    if db_path is None:
        msg = f"input: db.sqlite не найден по пути {args.path}"
        if args.json:
            print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
        else:
            print(msg, file=sys.stderr)
        return 2

    from backend.app.services.db_contract import validate_db

    violations = validate_db(db_path, require_section6=args.require_section6)

    if args.json:
        print(json.dumps({
            "ok": not violations,
            "db_path": str(db_path),
            "violations": violations,
        }, ensure_ascii=False, indent=2))
    else:
        if not violations:
            print(f"OK: {db_path} соответствует C2-контракту")
        else:
            print(f"НАРУШЕНИЯ C2-контракта ({len(violations)}) в {db_path}:")
            for v in violations:
                print(f"  - {v}")

    return 3 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
