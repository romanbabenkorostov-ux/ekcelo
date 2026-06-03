"""CLI обёртки над uvicorn (cycle 10)."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from lot_orchestrator_web.cli import _parse_args, _resolve_persistence_db, main


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.workers == 1
    assert args.persistence_db is None
    assert args.redis_url is None


def test_parse_args_custom():
    args = _parse_args([
        "--host", "0.0.0.0",
        "--port", "9000",
        "--workers", "4",
        "--persistence-db", "./runs.sqlite",
        "--redis-url", "redis://localhost:6379/0",
        "--reload",
    ])
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.workers == 4
    assert args.persistence_db == "./runs.sqlite"
    assert args.redis_url == "redis://localhost:6379/0"
    assert args.reload is True


def test_resolve_persistence_db_from_flag(monkeypatch):
    monkeypatch.delenv("PERSISTENCE_DB", raising=False)
    args = _parse_args(["--persistence-db", "./flag.db"])
    assert _resolve_persistence_db(args).name == "flag.db"


def test_resolve_persistence_db_from_env(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_DB", "./env.db")
    args = _parse_args([])
    assert _resolve_persistence_db(args).name == "env.db"


def test_resolve_persistence_db_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_DB", "./env.db")
    args = _parse_args(["--persistence-db", "./flag.db"])
    assert _resolve_persistence_db(args).name == "flag.db"


def test_resolve_persistence_db_none_when_unset(monkeypatch):
    monkeypatch.delenv("PERSISTENCE_DB", raising=False)
    args = _parse_args([])
    assert _resolve_persistence_db(args) is None


def test_main_calls_uvicorn_with_args(monkeypatch):
    """Вызов main() должен дёрнуть uvicorn.run с правильными параметрами."""
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = MagicMock()
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.delenv("PERSISTENCE_DB", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    rc = main(["--host", "1.2.3.4", "--port", "9999", "--log-level", "debug"])
    assert rc == 0
    fake_uvicorn.run.assert_called_once()
    args, kwargs = fake_uvicorn.run.call_args
    assert args[0] == "lot_orchestrator_web.main:app"
    assert kwargs["host"] == "1.2.3.4"
    assert kwargs["port"] == 9999
    assert kwargs["log_level"] == "debug"


def test_main_sets_env_vars_for_persistence_and_redis(monkeypatch):
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = MagicMock()
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.delenv("EKCELO_PERSISTENCE_DB", raising=False)
    monkeypatch.delenv("EKCELO_REDIS_URL", raising=False)
    monkeypatch.delenv("PERSISTENCE_DB", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    main([
        "--persistence-db", "./runs.sqlite",
        "--redis-url", "redis://example:6379/0",
    ])
    import os
    assert os.environ["EKCELO_PERSISTENCE_DB"] == "runs.sqlite"
    assert os.environ["EKCELO_REDIS_URL"] == "redis://example:6379/0"


def test_main_returns_3_when_uvicorn_missing(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    # При импорте `import uvicorn` Python взглянет в sys.modules; если там None → ImportError.
    # Но фактический ImportError может произойти позже. Проверим другой путь — удалим из sys.modules.
    monkeypatch.delitem(sys.modules, "uvicorn", raising=False)

    # Подменим финдер, чтобы любой import uvicorn возвращал ImportError.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _no_uvicorn(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("uvicorn not installed")
        return real_import(name, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "__import__", _no_uvicorn)
    rc = main([])
    assert rc == 3
    err = capsys.readouterr().err
    assert "uvicorn" in err
