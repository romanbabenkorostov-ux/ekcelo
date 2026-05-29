"""tests/test_etl_pipeline_cli.py — bulk-применение YAML из inbox."""
from __future__ import annotations

import sqlite3
import textwrap
from datetime import date
from pathlib import Path

import pytest

from parser.exporters.etp.etl_pipeline_cli import main as pipeline_main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"


@pytest.fixture
def db_file(tmp_path) -> Path:
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


def _yaml(name: str, content: str, inbox: Path) -> Path:
    p = inbox / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  Happy paths
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_inbox_rc0(db_file, tmp_path, capsys):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    rc = pipeline_main(["--db", str(db_file), "--inbox", str(inbox)])
    assert rc == 0
    assert "no-yaml" in capsys.readouterr().out


def test_applies_multiple_yamls_alphabetical(db_file, tmp_path, capsys):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("2026-06-01-a.yml", """
        profiles:
          - cad_number: "61:44:0050706:31"
    """, inbox)
    _yaml("2026-06-02-b.yml", """
        profiles:
          - cad_number: "61:44:0050706:42"
    """, inbox)
    rc = pipeline_main(["--db", str(db_file), "--inbox", str(inbox)])
    assert rc == 0
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 2
    out = capsys.readouterr().out
    assert "files: 2/2 ok" in out


def test_continues_on_single_file_failure_rc3(db_file, tmp_path, capsys):
    """Один битый YAML не должен остановить остальные. rc=3 (partial)."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("good.yml", """
        profiles:
          - cad_number: "61:44:0050706:31"
    """, inbox)
    _yaml("bad.yml", """
        profiles:
          - cad_number: "61:44:0050706:42"
            confidence: 1.5
    """, inbox)
    rc = pipeline_main(["--db", str(db_file), "--inbox", str(inbox)])
    assert rc == 3
    # «good.yml» применился: 1 профиль в БД.
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 1
    out = capsys.readouterr()
    assert "FAIL" in out.err
    assert "1 failed" in out.out


def test_dry_run_skips_writes_and_export(db_file, tmp_path, capsys):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("a.yml", """
        profiles:
          - cad_number: "61:44:0050706:31"
    """, inbox)
    rc = pipeline_main([
        "--db", str(db_file), "--inbox", str(inbox),
        "--dry-run", "--export", "--export-out", str(tmp_path / "exp"),
    ])
    assert rc == 0
    # БД не изменилась.
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 0
    # Export пропущен.
    assert not (tmp_path / "exp" / "object_etp_profile.json").exists()
    out = capsys.readouterr().out
    assert "[DRY-RUN]" in out


def test_move_applied_relocates_files(db_file, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("a.yml", "profiles:\n  - cad_number: \"61:44:0050706:31\"\n", inbox)
    pipeline_main([
        "--db", str(db_file), "--inbox", str(inbox), "--move-applied",
    ])
    assert not (inbox / "a.yml").exists()
    today = date.today().isoformat()
    assert (inbox / "_applied" / today / "a.yml").exists()


def test_move_applied_only_successful_files(db_file, tmp_path):
    """Битый YAML остаётся в inbox, корректный — переезжает."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("good.yml", "profiles:\n  - cad_number: \"61:44:0050706:31\"\n", inbox)
    _yaml("bad.yml", """
        profiles:
          - cad_number: "61:44:0050706:42"
            confidence: 1.5
    """, inbox)
    pipeline_main([
        "--db", str(db_file), "--inbox", str(inbox), "--move-applied",
    ])
    today = date.today().isoformat()
    assert (inbox / "_applied" / today / "good.yml").exists()
    assert (inbox / "bad.yml").exists()  # FAIL → остался
    assert not (inbox / "good.yml").exists()


def test_export_after_bulk(db_file, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("a.yml", "profiles:\n  - cad_number: \"61:44:0050706:31\"\n", inbox)
    out = tmp_path / "exports"
    pipeline_main([
        "--db", str(db_file), "--inbox", str(inbox),
        "--export", "--export-out", str(out),
    ])
    assert (out / "object_etp_profile.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
#  Errors
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_db_returns_2(tmp_path, capsys):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    rc = pipeline_main(["--db", str(tmp_path / "nope.sqlite"), "--inbox", str(inbox)])
    assert rc == 2
    assert "db not found" in capsys.readouterr().err


def test_missing_inbox_returns_2(db_file, tmp_path, capsys):
    rc = pipeline_main(["--db", str(db_file), "--inbox", str(tmp_path / "nope")])
    assert rc == 2
    assert "inbox not found" in capsys.readouterr().err


def test_only_yaml_files_picked_not_md(db_file, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _yaml("a.yml", "profiles:\n  - cad_number: \"61:44:0050706:31\"\n", inbox)
    (inbox / "README.md").write_text("# readme", encoding="utf-8")
    rc = pipeline_main(["--db", str(db_file), "--inbox", str(inbox)])
    assert rc == 0
    # README.md остался.
    assert (inbox / "README.md").exists()
