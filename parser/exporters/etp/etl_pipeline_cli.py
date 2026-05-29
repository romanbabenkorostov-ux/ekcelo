"""CLI: bulk-обработка всех YAML из parser/inbox/etp/.

Прогоняет etl_osv по каждому файлу в inbox (alphabetical order), копит
суммарный report. Опционально:
- `--move-applied` — перенести успешно применённые файлы в `_applied/`
  с date-prefix'ом.
- `--export` / `--commit` — после применения всех файлов один раз
  обновить JSON-экспорт + закоммитить.

Usage:
    # Прогнать все YAML из default inbox в БД, без побочных действий.
    python -m parser.exporters.etp.etl_pipeline_cli --db ekcelo.sqlite

    # Прогнать + переместить в _applied/ + обновить JSON + закоммитить.
    python -m parser.exporters.etp.etl_pipeline_cli \\
        --db ekcelo.sqlite --move-applied --export --commit

    # Кастомный inbox, dry-run (валидация только).
    python -m parser.exporters.etp.etl_pipeline_cli \\
        --db ekcelo.sqlite --inbox path/to/yaml-dir --dry-run

Exit codes:
    0 — все файлы успешно (или нет файлов; не ошибка).
    2 — отсутствует БД / inbox.
    3 — хотя бы один файл провалил валидацию; остальные применены
        (если не --dry-run и не --atomic-batch).
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

from parser.exporters.etp.auto_export import add_export_args, run_export_if_requested
from parser.exporters.etp.etl_osv import apply_osv, load_osv


DEFAULT_INBOX = Path("parser/inbox/etp")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2

    inbox = Path(args.inbox)
    if not inbox.is_dir():
        print(f"error: inbox not found: {inbox}", file=sys.stderr)
        return 2

    yaml_files = _find_yaml(inbox)
    if not yaml_files:
        print(f"[no-yaml] {inbox}: нет YAML-файлов на applied")
        return 0

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    totals = {
        "profiles_inserted": 0, "profiles_updated": 0,
        "lots_inserted": 0,     "lots_updated": 0,
        "lot_items_inserted": 0, "lot_items_deleted": 0,
    }
    applied: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for yaml_path in yaml_files:
        try:
            doc = load_osv(yaml_path)
            report = apply_osv(conn, doc, dry_run=args.dry_run)
        except (ValueError, sqlite3.IntegrityError) as e:
            failed.append((yaml_path, str(e)))
            print(f"[FAIL ] {yaml_path.name}: {e}", file=sys.stderr)
            continue

        totals["profiles_inserted"] += report.profiles_inserted
        totals["profiles_updated"]  += report.profiles_updated
        totals["lots_inserted"]     += report.lots_inserted
        totals["lots_updated"]      += report.lots_updated
        totals["lot_items_inserted"] += report.lot_items_inserted
        totals["lot_items_deleted"]  += report.lot_items_deleted

        mode = "DRY-RUN" if args.dry_run else "APPLIED"
        print(
            f"[{mode}] {yaml_path.name}  "
            f"profiles +{report.profiles_inserted}/~{report.profiles_updated}  "
            f"lots +{report.lots_inserted}/~{report.lots_updated}  "
            f"items +{report.lot_items_inserted}/-{report.lot_items_deleted}"
        )
        applied.append(yaml_path)

    if not args.dry_run and args.move_applied and applied:
        _move_to_applied(applied, inbox)

    print(
        f"[summary] files: {len(applied)}/{len(yaml_files)} ok, "
        f"{len(failed)} failed.  "
        f"profiles +{totals['profiles_inserted']}/~{totals['profiles_updated']}  "
        f"lots +{totals['lots_inserted']}/~{totals['lots_updated']}  "
        f"items +{totals['lot_items_inserted']}/-{totals['lot_items_deleted']}"
    )

    # Export/commit (если запрошено) — один раз после всех файлов.
    run_export_if_requested(conn, args, dry_run=args.dry_run, source_label="osv-bulk")

    return 0 if not failed else 3


def _find_yaml(directory: Path) -> list[Path]:
    """YAML/YML файлы в директории (не рекурсивно, без `_applied/` подпапки)."""
    candidates = sorted(
        [p for p in directory.iterdir()
         if p.is_file() and p.suffix.lower() in (".yml", ".yaml")]
    )
    return candidates


def _move_to_applied(files: list[Path], inbox: Path) -> None:
    """Переместить применённые YAML в `_applied/YYYY-MM-DD/`."""
    archive = inbox / "_applied" / date.today().isoformat()
    archive.mkdir(parents=True, exist_ok=True)
    for src in files:
        dst = archive / src.name
        # Если уже есть такой же файл — добавим суффикс.
        if dst.exists():
            stem = src.stem
            ext = src.suffix
            for i in range(1, 1000):
                candidate = archive / f"{stem}.{i}{ext}"
                if not candidate.exists():
                    dst = candidate
                    break
        shutil.move(str(src), str(dst))
        print(f"[moved] {src.name} → {dst.relative_to(inbox.parent)}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.etl_pipeline_cli",
        description="Bulk-применение всех YAML survey-листов из inbox.",
    )
    p.add_argument("--db", required=True, help="Путь к SQLite БД с миграцией 0001.")
    p.add_argument("--inbox", default=str(DEFAULT_INBOX),
                   help=f"Директория с YAML-файлами (default: {DEFAULT_INBOX}).")
    p.add_argument("--dry-run", action="store_true",
                   help="Только валидация: БД и inbox не меняются.")
    p.add_argument("--move-applied", action="store_true",
                   help="Перенести успешно применённые YAML в "
                        "<inbox>/_applied/<date>/ после прогона.")
    add_export_args(p)
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
