"""CLI: импорт Bundle (C3) в ekcelo SQLite.

Реализует SPEC_backend.md §P0.2 п.2 «локальный CLI ekcelo-import-bundle».
Тонкая обёртка над `backend.app.services.bundle.import_bundle` — без своей
логики; вся валидация и idempotent upsert — в сервис-слое.

Usage:
    ekcelo-import-bundle --bundle <dir> --db <ekcelo.sqlite>
    ekcelo-import-bundle --bundle <dir> --db <ekcelo.sqlite> --dry-run
    ekcelo-import-bundle --bundle <dir> --db <ekcelo.sqlite> --no-verify

Exit codes:
    0 — успех (даже если no-op повтор того же Bundle).
    2 — ошибка input'а (нет каталога, невалидный манифест).
    3 — ошибка целостности (sha256/size mismatch).
    4 — ошибка импорта (sqlite/FK).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.app.services.bundle import ImportReport, import_bundle


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    bundle = Path(args.bundle)
    target_db = Path(args.db)

    if not bundle.is_dir():
        print(f"error: --bundle не каталог: {bundle}", file=sys.stderr)
        return 2

    try:
        report = import_bundle(
            bundle, target_db,
            verify_hashes=not args.no_verify,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover (внутренняя ошибка sqlite)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    rc = _print_report(report, args.json_output)
    return rc


def _print_report(report: ImportReport, as_json: bool) -> int:
    """Печатает отчёт человеку или JSON; возвращает exit code."""
    if as_json:
        payload = {
            "bundle_path": str(report.bundle_path),
            "is_noop": report.is_noop,
            "objects_inserted": report.objects_inserted,
            "objects_updated": report.objects_updated,
            "objects_skipped_identical": report.objects_skipped_identical,
            "entities_inserted": report.entities_inserted,
            "rights_inserted": report.rights_inserted,
            "etp_profiles_inserted": report.etp_profiles_inserted,
            "etp_profiles_skipped_authoritative": report.etp_profiles_skipped_authoritative,
            "files_verified": report.files_verified,
            "files_failed": report.files_failed,
            "warnings": report.warnings,
            "errors": report.errors,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        # Человеко-читаемый отчёт в stdout.
        status = "NOOP" if report.is_noop else "OK" if not report.errors else "ERROR"
        print(f"[{status}] bundle: {report.bundle_path}")
        if report.files_failed:
            print(f"  ! файлов с ошибками целостности: {len(report.files_failed)}")
            for f in report.files_failed:
                print(f"    - {f}", file=sys.stderr)
        print(f"  objects: +{report.objects_inserted} ins / "
              f"~{report.objects_updated} upd / "
              f"={report.objects_skipped_identical} skip")
        print(f"  entity_registry: +{report.entities_inserted}")
        print(f"  rights: +{report.rights_inserted}")
        if report.etp_profiles_inserted or report.etp_profiles_skipped_authoritative:
            print(f"  etp_profile: +{report.etp_profiles_inserted} ins / "
                  f"={report.etp_profiles_skipped_authoritative} skip-authoritative")
        if report.warnings:
            print(f"  warnings: {len(report.warnings)}", file=sys.stderr)
            for w in report.warnings:
                print(f"    - {w}", file=sys.stderr)
        if report.errors:
            print(f"  errors: {len(report.errors)}", file=sys.stderr)
            for e in report.errors:
                print(f"    - {e}", file=sys.stderr)

    if report.files_failed:
        return 3
    if report.errors:
        return 4
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ekcelo-import-bundle",
        description="Идемпотентный импорт Bundle (C3) в ekcelo SQLite.",
        epilog=(
            "Bundle — каталог с manifest.json + db.sqlite + project.kmz "
            "(контракт contracts/bundle/BUNDLE_SPEC.md). "
            "Повторный импорт того же Bundle — no-op."
        ),
    )
    p.add_argument("--bundle", required=True, help="Каталог Bundle.")
    p.add_argument("--db", required=True,
                   help="Целевая SQLite БД (создаётся если её нет).")
    p.add_argument("--dry-run", action="store_true",
                   help="Открыть транзакцию и откатить; отчёт остаётся.")
    p.add_argument("--no-verify", action="store_true",
                   help="Пропустить sha256/size проверку файлов из manifest.")
    p.add_argument("--json", dest="json_output", action="store_true",
                   help="Машиночитаемый JSON в stdout вместо текста.")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
