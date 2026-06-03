"""serve.py launcher — smoke + edge cases."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVE_PY = REPO_ROOT / "serve.py"


def test_serve_module_imports_without_running():
    """serve.py импортируется без падений (sanity)."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import serve
        assert hasattr(serve, "main")
        assert hasattr(serve, "_ensure_pythonpath")
        assert hasattr(serve, "_warn_if_foreign_venv")
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_ensure_pythonpath_adds_repo_root(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        serve._ensure_pythonpath()
        assert str(REPO_ROOT) in os.environ["PYTHONPATH"].split(os.pathsep)
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_ensure_pythonpath_preserves_existing(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/some/other/path")
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        serve._ensure_pythonpath()
        parts = os.environ["PYTHONPATH"].split(os.pathsep)
        assert str(REPO_ROOT) in parts
        assert "/some/other/path" in parts
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_warn_when_foreign_venv(monkeypatch, capsys, tmp_path):
    foreign = tmp_path / "foreign_venv"
    foreign.mkdir()
    monkeypatch.setenv("VIRTUAL_ENV", str(foreign))
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        serve._warn_if_foreign_venv()
        err = capsys.readouterr().err
        assert "WARNING" in err
        assert "venv находится вне корня репо" in err
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_no_warn_when_no_venv(monkeypatch, capsys):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        serve._warn_if_foreign_venv()
        err = capsys.readouterr().err
        assert "WARNING" not in err
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_no_warn_when_venv_inside_repo(monkeypatch, capsys, tmp_path):
    inside = REPO_ROOT / ".venv-test-only"
    monkeypatch.setenv("VIRTUAL_ENV", str(inside))
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        serve._warn_if_foreign_venv()
        err = capsys.readouterr().err
        assert "WARNING" not in err
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_install_hint_text_mentions_uvicorn_and_pip():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        hint = serve._install_hint()
        assert "uvicorn" in hint
        assert "pip install" in hint
        assert "fastapi" in hint
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_argparse_defaults():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        args = serve._parse_args([])
        assert args.host == "127.0.0.1"
        assert args.port == 8000
        assert args.no_reload is False
        assert args.log_level == "info"
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_argparse_custom():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib
        import serve
        importlib.reload(serve)
        args = serve._parse_args([
            "--host", "0.0.0.0", "--port", "9000",
            "--no-reload", "--log-level", "debug",
        ])
        assert args.host == "0.0.0.0"
        assert args.port == 9000
        assert args.no_reload is True
        assert args.log_level == "debug"
    finally:
        sys.path.remove(str(REPO_ROOT))


def test_subprocess_help_exits_zero():
    """Sanity: `python serve.py --help` отрабатывает без ошибок."""
    result = subprocess.run(
        [sys.executable, str(SERVE_PY), "--help"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    assert "Foolproof launcher" in result.stdout
    assert "--port" in result.stdout
