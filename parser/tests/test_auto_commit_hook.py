"""tests/test_auto_commit_hook.py — флаг --commit поверх --export.

Каждый тест работает в собственном изолированном git-репо в tmp_path,
чтобы не трогать рабочий репо.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from parser.exporters.etp.etl_osv_cli import main as osv_main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
TEMPLATE = REPO_ROOT / "parser" / "exporters" / "etp" / "templates" / "osv_template.yaml"


def _git_env_no_sign() -> dict:
    """Подавить глобальный signing для изолированных тестовых репо."""
    env = os.environ.copy()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    env["GIT_CONFIG_VALUE_0"] = "false"
    return env


def _init_git_repo(path: Path) -> None:
    """git init + commit, чтобы можно было видеть последующие --commit'ы."""
    env = _git_env_no_sign()
    subprocess.check_call(["git", "init", "--initial-branch=main", "-q", str(path)], env=env)
    subprocess.check_call(["git", "-C", str(path), "config", "user.email", "test@example.com"], env=env)
    subprocess.check_call(["git", "-C", str(path), "config", "user.name", "Tester"], env=env)
    subprocess.check_call(["git", "-C", str(path), "config", "commit.gpgsign", "false"], env=env)
    (path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(path), "add", ".gitkeep"], env=env)
    subprocess.check_call(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"], env=env,
    )


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "ekcelo.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    for cad in ("61:44:0050706:31", "61:44:0050706:42", "61:44:0050706:7"):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    conn.commit()
    conn.close()
    return db


def _last_commit_subject(repo: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--pretty=%s"],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def _commit_count(repo: Path) -> int:
    r = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True,
    )
    return int(r.stdout.strip())


# ─────────────────────────────────────────────────────────────────────────────
#  Happy paths
# ─────────────────────────────────────────────────────────────────────────────

def test_commit_creates_commit_in_repo(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    db = _setup_db(repo)
    out = repo / "exports"
    rc = osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db),
        "--export",
        "--export-out", str(out),
        "--commit",
    ])
    assert rc == 0
    out_path = out / "object_etp_profile.json"
    assert out_path.exists()

    # Должен быть новый коммит.
    assert _commit_count(repo) == 2
    subject = _last_commit_subject(repo)
    assert "auto-export" in subject
    assert "from osv" in subject
    captured = capsys.readouterr().out
    assert "[exported]" in captured
    assert "[committed]" in captured


def test_commit_noop_when_no_changes(tmp_path, capsys, monkeypatch):
    """Повторный прогон без изменений → коммит не создаётся."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    db = _setup_db(repo)
    out = repo / "exports"

    osv_main(["--yaml", str(TEMPLATE), "--db", str(db),
              "--export", "--export-out", str(out), "--commit"])
    count_after_first = _commit_count(repo)

    # Прогон ещё раз — данные те же.
    osv_main(["--yaml", str(TEMPLATE), "--db", str(db),
              "--export", "--export-out", str(out), "--commit"])
    assert _commit_count(repo) == count_after_first
    assert "[commit-noop]" in capsys.readouterr().out


def test_commit_skips_outside_git_repo(tmp_path, capsys):
    """Каталог не git-репо → commit пропускается без падения."""
    db = _setup_db(tmp_path)
    out = tmp_path / "exports"
    rc = osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db),
        "--export",
        "--export-out", str(out),
        "--commit",
    ])
    assert rc == 0
    assert (out / "object_etp_profile.json").exists()
    assert "[commit-skipped]" in capsys.readouterr().out


def test_commit_respects_dry_run(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    db = _setup_db(repo)
    out = repo / "exports"
    initial = _commit_count(repo)
    rc = osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db),
        "--dry-run",
        "--export",
        "--export-out", str(out),
        "--commit",
    ])
    assert rc == 0
    assert _commit_count(repo) == initial  # ничего не закоммитили
    assert "[skip-export]" in capsys.readouterr().out


def test_commit_author_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    db = _setup_db(repo)
    out = repo / "exports"
    osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db),
        "--export",
        "--export-out", str(out),
        "--commit",
        "--commit-author", "Economist <e@example.com>",
    ])
    r = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--pretty=%an <%ae>"],
        capture_output=True, text=True,
    )
    assert r.stdout.strip() == "Economist <e@example.com>"


def test_no_commit_flag_does_not_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    db = _setup_db(repo)
    out = repo / "exports"
    initial = _commit_count(repo)
    osv_main([
        "--yaml", str(TEMPLATE),
        "--db", str(db),
        "--export",
        "--export-out", str(out),
        # без --commit
    ])
    assert _commit_count(repo) == initial
