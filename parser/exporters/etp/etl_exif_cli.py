"""CLI: EXIF-обогащение object_etp_profile из директории JPG.

Usage:
    python -m parser.exporters.etp.etl_exif_cli \\
        --db    path/to/ekcelo.sqlite \\
        --photos path/to/Фотографии/ \\
        [--source exif] [--confidence 0.7] [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from parser.exporters.etp.etl_exif import (
    DEFAULT_CONFIDENCE,
    DEFAULT_SOURCE,
    enrich_from_exif,
    scan_directory,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2
    photos_dir = Path(args.photos)
    if not photos_dir.is_dir():
        print(f"error: photos dir not found: {photos_dir}", file=sys.stderr)
        return 2

    photos = scan_directory(photos_dir)
    if not photos:
        print(f"[NO-PHOTOS] {photos_dir}: ни одного JPG с ekcelo UserComment не найдено.",
              file=sys.stderr)
        return 0

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    if args.dry_run:
        conn.execute("BEGIN")
    reports = enrich_from_exif(conn, photos,
                               source=args.source, confidence=args.confidence)
    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()

    changed = sum(1 for r in reports if r.changed)
    skipped = sum(1 for r in reports if r.skipped_reason)
    total_photos = sum(r.photos_count for r in reports)
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[{mode}] cads: {len(reports)}  photos_total: {total_photos}  "
        f"changed: {changed}  skipped: {skipped}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.etl_exif_cli",
        description="EXIF-обогащение object_etp_profile из JPG фото проекта.",
    )
    p.add_argument("--db", required=True)
    p.add_argument("--photos", required=True,
                   help="Корневая директория с JPG (искаем рекурсивно).")
    p.add_argument("--source", default=DEFAULT_SOURCE)
    p.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
