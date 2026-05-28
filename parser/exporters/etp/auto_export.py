"""auto_export: общий хелпер «после ETL → перегенерация JSON-экспорта + опц. git commit».

Все ETL CLI (`etl_osv_cli`, `nspd_enrich_cli`, `etl_exif_cli`) принимают
общий набор флагов:

| Флаг | Значение |
|---|---|
| `--export` | После commit'а в БД перегенерировать JSON-экспорт. |
| `--export-out <dir>` | Корневая директория (default: `parser/exports/etp/`). |
| `--export-project <slug>` | Project-фильтр (default: всё). |
| `--commit` | Дополнительно `git add` + `git commit` экспортированного JSON. |
| `--commit-author "Name <email>"` | Override author для commit (default: git config). |

С `--dry-run` оба этапа пропускаются.

См. `obsidian/Architecture/etp-exporter.md` § «Полный пайплайн».
"""
from __future__ import annotations

import argparse
import shlex
import sqlite3
import subprocess
from pathlib import Path

from parser.exporters.etp.export_json import DEFAULT_OUT_DIR, write_export


def add_export_args(parser: argparse.ArgumentParser) -> None:
    """Зарегистрировать общие --export / --commit флаги."""
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
    group.add_argument(
        "--commit",
        action="store_true",
        help="После --export: git add + git commit экспортированного JSON. "
             "Требует, чтобы текущий каталог был внутри git-репо.",
    )
    group.add_argument(
        "--commit-author",
        default=None,
        help='Override Git author для авто-коммита (формат: "Name <email>"). '
             "По умолчанию — git config user.name / user.email.",
    )


def run_export_if_requested(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    *,
    dry_run: bool = False,
    source_label: str | None = None,
) -> Path | None:
    """Если в args был --export — записать JSON; при --commit — закоммитить.

    Args:
        conn: открытое соединение, в котором уже зафиксированы изменения ETL.
        args: namespace argparse с полями export / commit / *_out / *_project / *_author.
        dry_run: если True, экспорт и коммит пропускаются с сообщением.
        source_label: метка источника ETL для commit message (например "osv", "nspd", "exif").
                      По умолчанию — "etl".

    Returns:
        Path к сгенерированному JSON либо None.
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

    if getattr(args, "commit", False):
        _git_commit_export(out_path, args, source_label or "etl")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
#  Git commit helper
# ─────────────────────────────────────────────────────────────────────────────

def _git_commit_export(
    out_path: Path,
    args: argparse.Namespace,
    source_label: str,
) -> None:
    """Безопасный git add + commit одного файла.

    Не падает на ошибке (печатает [commit-skipped] с причиной) — это hook,
    а не основной workflow. Реальный sync пользователь делает руками.
    """
    if not _is_inside_git_repo(out_path.parent):
        print(f"[commit-skipped] {out_path} не внутри git-репо")
        return

    # Проверяем, есть ли что коммитить.
    try:
        diff = subprocess.run(
            ["git", "diff", "--quiet", "--", str(out_path)],
            cwd=out_path.parent, capture_output=True,
        )
    except FileNotFoundError:
        print("[commit-skipped] git недоступен в PATH")
        return

    # `git diff --quiet` exit 0 — нет изменений, exit 1 — есть.
    if diff.returncode == 0:
        # Проверим, отслеживается ли вообще файл.
        ls = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(out_path)],
            cwd=out_path.parent, capture_output=True,
        )
        if ls.returncode == 0:
            print(f"[commit-noop] {out_path}: нет изменений")
            return

    add = subprocess.run(
        ["git", "add", "--", str(out_path)],
        cwd=out_path.parent, capture_output=True, text=True,
    )
    if add.returncode != 0:
        print(f"[commit-skipped] git add failed: {add.stderr.strip()}")
        return

    msg = _build_commit_message(out_path, source_label)
    cmd = ["git", "commit", "-m", msg]
    if args.commit_author:
        cmd.extend(["--author", args.commit_author])
    cmd.extend(["--", str(out_path)])

    commit = subprocess.run(cmd, cwd=out_path.parent, capture_output=True, text=True)
    if commit.returncode != 0:
        print(f"[commit-skipped] git commit failed: {commit.stderr.strip()}")
        return

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=out_path.parent, capture_output=True, text=True,
    ).stdout.strip()
    print(f"[committed] {sha} {shlex.quote(str(out_path))}")


def _is_inside_git_repo(path: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path, capture_output=True, text=True,
        )
    except FileNotFoundError:
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def _build_commit_message(out_path: Path, source_label: str) -> str:
    rel = out_path.name
    return (
        f"chore(etp): auto-export {rel} from {source_label}\n"
        "\n"
        "Регенерация JSON-экспорта для viewer после ETL-прогона.\n"
        "См. obsidian/Architecture/etl-osv.md § auto-export hook."
    )
