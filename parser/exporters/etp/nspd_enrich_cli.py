"""CLI: NSPD-enrichment object_etp_profile из директории JSON-файлов.

Usage:
    python -m parser.exporters.etp.nspd_enrich_cli \\
        --db   path/to/ekcelo.sqlite \\
        --nspd path/to/_data/nspd_cache/ \\
        [--source nspd] [--confidence 0.8] [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from parser.exporters.etp.nspd_enricher import (
    DEFAULT_CONFIDENCE,
    DEFAULT_SOURCE,
    enrich_from_directory,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2
    nspd_dir = Path(args.nspd)
    if not nspd_dir.is_dir():
        print(f"error: nspd dir not found: {nspd_dir}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    if args.dry_run:
        conn.execute("BEGIN")
    reports = enrich_from_directory(
        conn, nspd_dir, source=args.source, confidence=args.confidence
    )
    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()

    changed = sum(1 for r in reports if r.changed)
    skipped = sum(1 for r in reports if r.skipped_reason)
    fields_total = sum(len(r.building_extra_filled) + len(r.legal_extra_filled)
                       for r in reports)
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[{mode}] processed: {len(reports)}  changed: {changed}  "
        f"skipped: {skipped}  fields_filled: {fields_total}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.nspd_enrich_cli",
        description="NSPD-обогащение object_etp_profile (gap-fill).",
    )
    p.add_argument("--db", required=True)
    p.add_argument("--nspd", required=True,
                   help="Директория с NSPD JSON (по одному файлу на КН).")
    p.add_argument("--source", default=DEFAULT_SOURCE,
                   help=f"Source для новых записей (default: {DEFAULT_SOURCE}).")
    p.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE,
                   help=f"Confidence для новых записей (default: {DEFAULT_CONFIDENCE}).")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
