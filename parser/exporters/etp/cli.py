"""CLI: экспорт лота в файлы для ЭТП.

Usage:
    python -m parser.exporters.etp.cli \\
        --lot lot:pirushin:001 \\
        --db path/to/ekcelo.sqlite \\
        --platforms torgi.gov.ru,sberbank-ast.ru \\
        --modes short,full \\
        --out out/etp/

Output:
    out/etp/<lot_id>/
        lot_appendix.md
        <platform>/
            long_description.json
            description.short.txt
            description.full.txt
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from parser.exporters.etp.appendix import build_lot_appendix
from parser.exporters.etp.build_lot_context import build_lot_context
from parser.exporters.etp.md_convert import convert_appendix
from parser.exporters.etp.text_render import (
    available_modes,
    available_platforms,
    render_lot_description,
)


DEFAULT_PLATFORMS = ",".join(available_platforms())
DEFAULT_MODES = "short,full"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    platforms = _csv(args.platforms)
    modes = _csv(args.modes)
    _validate(platforms, modes)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2

    out_root = Path(args.out) / _safe_dirname(args.lot)
    out_root.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    appendix_md = build_lot_appendix(conn, args.lot)
    appendix_path = out_root / "lot_appendix.md"
    appendix_path.write_text(appendix_md, encoding="utf-8")
    written = [appendix_path]

    # Опциональная конвертация приложения в PDF/DOCX (best-effort).
    if args.appendix_format != "md":
        converted = convert_appendix(appendix_path, target=args.appendix_format)
        if converted is not None:
            written.append(converted)

    for platform in platforms:
        platform_dir = out_root / _safe_dirname(platform)
        platform_dir.mkdir(exist_ok=True)
        ctx_cache: dict | None = None
        for mode in modes:
            ctx = build_lot_context(conn, args.lot,
                                    platform=platform, platform_mode=mode,
                                    target_cad_number=args.target_cad)
            if ctx_cache is None:
                ctx_cache = ctx
            text = render_lot_description(ctx)
            txt_path = platform_dir / f"description.{mode}.txt"
            txt_path.write_text(text, encoding="utf-8")
            written.append(txt_path)
        # One canonical ctx JSON per platform (mode-independent except meta.platform_mode).
        if ctx_cache is not None:
            json_path = platform_dir / "long_description.json"
            json_path.write_text(
                json.dumps(ctx_cache, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            written.append(json_path)

    if not args.quiet:
        for p in written:
            print(p)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.cli",
        description="Экспорт лота в текстовые описания + JSON ctx + MD-приложение.",
    )
    p.add_argument("--lot", required=True, help="lot_id (например, lot:pirushin:001).")
    p.add_argument("--db", required=True, help="Путь к SQLite БД с миграцией 0001.")
    p.add_argument("--out", required=True, help="Выходная директория. Создаётся, если нет.")
    p.add_argument("--platforms", default=DEFAULT_PLATFORMS,
                   help=f"Через запятую (по умолчанию: {DEFAULT_PLATFORMS}).")
    p.add_argument("--modes", default=DEFAULT_MODES,
                   help="short, full или оба через запятую (по умолчанию: short,full).")
    p.add_argument("--target-cad", dest="target_cad",
                   help="Опционально: КН-анкер для identity (по умолчанию — lots.primary_cad_number).")
    p.add_argument("--appendix-format", default="md", choices=["md", "pdf", "docx"],
                   help="Формат приложения к лоту: md (default) | pdf | docx. "
                        "PDF/DOCX требуют LibreOffice или pandoc; при отсутствии — "
                        "только .md (best-effort).")
    p.add_argument("--quiet", action="store_true", help="Не печатать пути созданных файлов.")
    return p.parse_args(argv)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate(platforms: list[str], modes: list[str]) -> None:
    valid_p = set(available_platforms())
    valid_m = set(available_modes())
    unknown_p = [p for p in platforms if p not in valid_p]
    unknown_m = [m for m in modes if m not in valid_m]
    if unknown_p:
        raise SystemExit(f"unknown platforms: {unknown_p}. Available: {sorted(valid_p)}")
    if unknown_m:
        raise SystemExit(f"unknown modes: {unknown_m}. Available: {sorted(valid_m)}")


def _safe_dirname(value: str) -> str:
    """`:`/`.`/`/` → `_` для безопасных имён директорий."""
    return value.replace(":", "_").replace("/", "_")


if __name__ == "__main__":
    sys.exit(main())
