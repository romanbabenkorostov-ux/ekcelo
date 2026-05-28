"""auto_export: общий хелпер «после ETL → перегенерация JSON-экспорта для viewer».

Все ETL CLI (`etl_osv_cli`, `nspd_enrich_cli`, `etl_exif_cli`) могут принять
флаг `--export` / `--export-out` / `--export-project` — после успешного
commit в БД автоматически вызывают `write_export()` для обновления
`parser/exports/etp/object_etp_profile.json`.

Это закрывает workflow «UI → YAML → drop → ETL → viewer fetch» в одну
команду на parser-стороне, без отдельного шага re-export.

См. `obsidian/Architecture/etp-exporter.md` § «Полный пайплайн».
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from parser.exporters.etp.export_json import DEFAULT_OUT_DIR, write_export


def add_export_args(parser: argparse.ArgumentParser) -> None:
    """Зарегистрировать общие --export / --export-out / --export-project флаги."""
    group = parser.add_argument_group("auto-export")
    group.add_argument(
        "--export",
        action="store_true",
        help="После применения ETL перегенерировать JSON-экспорт "
             "для viewer (parser/exports/etp/object_etp_profile.json).",
    )
    group.add_argument(
        "--export-out",
        default=str(DEFAULT_OUT_DIR),
        help=f"Корневая директория экспорта (по умолчанию: {DEFAULT_OUT_DIR}).",
    )
    group.add_argument(
        "--export-project",
        default=None,
        help="Project slug для фильтра экспорта (по умолчанию: всё).",
    )


def run_export_if_requested(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    *,
    dry_run: bool = False,
) -> Path | None:
    """Если в args был --export — записать JSON и вернуть путь.

    Args:
        conn: открытое соединение, в котором уже зафиксированы изменения ETL.
        args: namespace argparse с полями export / export_out / export_project.
        dry_run: если True, экспорт пропускается с сообщением.

    Returns:
        Path к сгенерированному JSON либо None (если --export не указан или dry-run).
    """
    if not getattr(args, "export", False):
        return None
    if dry_run:
        print("[skip-export] dry-run: JSON-экспорт пропущен")
        return None
    out_path = write_export(
        conn,
        args.export_out,
        project_slug=args.export_project,
    )
    print(f"[exported] {out_path}")
    return out_path
