"""CLI: end-to-end smoke-тест ЭТП-экспортёра.

Usage:
    python -m parser.exporters.etp.smoke_cli

Что делает (в tmp-директории, без побочных эффектов на репо):

1. import-check — пытается импортировать все 20 модулей пакета.
   Ловит инциденты вроде ModuleNotFoundError (см. obsidian/Architecture/
   etp-local-sync.md) до запуска CLI.
2. init-db --with-template — создаёт SQLite + объекты + профиль + лот.
3. verify-db — проверяет наличие строк в objects / object_etp_profile /
   lots / lot_items.
4. cli (Stage 3) — экспортирует lot:pirushin:001 на torgi.gov.ru в
   short+full; ожидает description.{short,full}.txt + lot_appendix.md +
   long_description.json.
5. verify-artifacts — проверяет существование и непустоту артефактов.
6. export-json — экспортирует object_etp_profile.json для viewer.
7. verify-json — проверяет ключи verschema / profiles / lots / lot_items.

Exit code:
    0 — все проверки пройдены.
    1 — хотя бы одна проверка упала; детали — в stderr.

Назначение:
- CI / release validation.
- Локальная проверка после клонирования / обновления.
- Профилактика "missing module" инцидентов.
"""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Все модули пакета, которые должны импортироваться без ошибок.
_REQUIRED_MODULES = [
    "parser.exporters.etp",
    "parser.exporters.etp.address_parser",
    "parser.exporters.etp.appendix",
    "parser.exporters.etp.auto_export",
    "parser.exporters.etp.build_lot_context",
    "parser.exporters.etp.cli",
    "parser.exporters.etp.encumbrance_mapper",
    "parser.exporters.etp.etl_exif",
    "parser.exporters.etp.etl_exif_cli",
    "parser.exporters.etp.etl_osv",
    "parser.exporters.etp.etl_osv_cli",
    "parser.exporters.etp.etl_pipeline_cli",
    "parser.exporters.etp.export_json",
    "parser.exporters.etp.export_json_cli",
    "parser.exporters.etp.init_db_cli",
    "parser.exporters.etp.md_convert",
    "parser.exporters.etp.morphology",
    "parser.exporters.etp.nspd_enrich_cli",
    "parser.exporters.etp.nspd_enricher",
    "parser.exporters.etp.text_render",
]

_SMOKE_LOT = "lot:pirushin:001"
_SMOKE_PLATFORM = "torgi.gov.ru"
_SMOKE_MODES = "short,full"


class _Check:
    __slots__ = ("name", "ok", "detail")

    def __init__(self, name: str, ok: bool, detail: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    checks: list[_Check] = []

    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="ekcelo-smoke-"))
    work.mkdir(parents=True, exist_ok=True)
    cleanup = args.work_dir is None and not args.keep

    try:
        checks.extend(_check_imports())
        if not all(c.ok for c in checks):
            return _report(checks, args.quiet)

        db_path = work / "smoke.sqlite"
        export_root = work / "out" / "etp"
        json_root = work / "exports" / "etp"

        checks.append(_check_init_db(db_path))
        if not checks[-1].ok:
            return _report(checks, args.quiet)

        checks.extend(_check_db_rows(db_path))
        checks.append(_check_cli_export(db_path, export_root))
        if checks[-1].ok:
            checks.extend(_check_artifacts(export_root))

        checks.append(_check_export_json(db_path, json_root))
        if checks[-1].ok:
            checks.append(_check_json_payload(json_root))

        return _report(checks, args.quiet)
    finally:
        if cleanup:
            shutil.rmtree(work, ignore_errors=True)


def _check_imports() -> list[_Check]:
    out: list[_Check] = []
    for mod in _REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            out.append(_Check(f"import {mod}", True))
        except Exception as exc:
            out.append(_Check(f"import {mod}", False, f"{type(exc).__name__}: {exc}"))
    return out


def _check_init_db(db_path: Path) -> _Check:
    from parser.exporters.etp.init_db_cli import main as init_main
    try:
        rc = init_main(["--db", str(db_path), "--with-template"])
    except Exception as exc:
        return _Check("init-db", False, f"{type(exc).__name__}: {exc}")
    if rc != 0:
        return _Check("init-db", False, f"rc={rc}")
    if not db_path.exists():
        return _Check("init-db", False, "db file missing")
    return _Check("init-db", True)


def _check_db_rows(db_path: Path) -> list[_Check]:
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        expected = {
            "objects": 3,
            "object_etp_profile": 1,
            "lots": 1,
            "lot_items": 2,
        }
        out: list[_Check] = []
        for table, want in expected.items():
            got = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            out.append(_Check(
                f"db rows {table}",
                got == want,
                f"want {want}, got {got}" if got != want else "",
            ))
        return out
    finally:
        conn.close()


def _check_cli_export(db_path: Path, out_root: Path) -> _Check:
    from parser.exporters.etp.cli import main as export_main
    try:
        rc = export_main([
            "--lot", _SMOKE_LOT,
            "--db", str(db_path),
            "--platforms", _SMOKE_PLATFORM,
            "--modes", _SMOKE_MODES,
            "--out", str(out_root),
            "--quiet",
        ])
    except Exception as exc:
        return _Check("cli export", False, f"{type(exc).__name__}: {exc}")
    return _Check("cli export", rc == 0, f"rc={rc}" if rc != 0 else "")


def _check_artifacts(out_root: Path) -> list[_Check]:
    lot_dir = out_root / _SMOKE_LOT.replace(":", "_")
    platform_dir = lot_dir / _SMOKE_PLATFORM.replace(":", "_").replace("/", "_")
    expected = [
        lot_dir / "lot_appendix.md",
        platform_dir / "description.short.txt",
        platform_dir / "description.full.txt",
        platform_dir / "long_description.json",
    ]
    out: list[_Check] = []
    for path in expected:
        if not path.exists():
            out.append(_Check(f"artifact {path.name}", False, "missing"))
            continue
        size = path.stat().st_size
        out.append(_Check(
            f"artifact {path.name}",
            size > 0,
            f"empty file" if size == 0 else "",
        ))
    return out


def _check_export_json(db_path: Path, out_root: Path) -> _Check:
    from parser.exporters.etp.export_json_cli import main as ej_main
    try:
        rc = ej_main(["--db", str(db_path), "--out", str(out_root)])
    except Exception as exc:
        return _Check("export-json", False, f"{type(exc).__name__}: {exc}")
    return _Check("export-json", rc == 0, f"rc={rc}" if rc != 0 else "")


def _check_json_payload(json_root: Path) -> _Check:
    payload_path = json_root / "object_etp_profile.json"
    if not payload_path.exists():
        return _Check("json payload", False, f"missing: {payload_path}")
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _Check("json payload", False, f"parse: {exc}")
    required = {"$schema_version", "object_etp_profile", "lots", "lot_items"}
    missing = required - set(payload.keys())
    if missing:
        return _Check("json payload", False, f"missing keys: {sorted(missing)}")
    if not payload["object_etp_profile"] or not payload["lots"]:
        return _Check("json payload", False, "profiles/lots empty")
    return _Check("json payload", True)


def _report(checks: list[_Check], quiet: bool) -> int:
    failed = [c for c in checks if not c.ok]
    # --quiet подавляет [OK]-строки, но провалы печатаем всегда.
    visible = checks if not quiet else failed
    for c in visible:
        mark = "OK " if c.ok else "FAIL"
        line = f"[{mark}] {c.name}"
        if c.detail:
            line += f" — {c.detail}"
        stream = sys.stdout if c.ok else sys.stderr
        print(line, file=stream)
    if not quiet or failed:
        summary = f"smoke: {len(checks) - len(failed)}/{len(checks)} passed"
        print(summary, file=sys.stderr if failed else sys.stdout)
    return 1 if failed else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.smoke_cli",
        description="End-to-end smoke-тест ЭТП-экспортёра.",
    )
    p.add_argument("--work-dir", default=None,
                   help="Рабочая директория (по умолчанию — tmp с автоудалением).")
    p.add_argument("--keep", action="store_true",
                   help="Не удалять tmp-директорию после прогона (для отладки).")
    p.add_argument("--quiet", action="store_true",
                   help="Не печатать построчный отчёт; только exit-code.")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
