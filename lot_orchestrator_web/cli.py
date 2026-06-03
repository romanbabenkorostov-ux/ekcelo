"""CLI обёртка над uvicorn с поддержкой `--persistence-db` и `--redis-url`.

Usage:
    # Минимально (dev):
    ekcelo-orchestrate-web --host 0.0.0.0 --port 8000

    # Production с persistence:
    ekcelo-orchestrate-web --persistence-db ./runs.sqlite --workers 1

    # Production multi-worker через Redis:
    ekcelo-orchestrate-web \\
        --redis-url redis://localhost:6379/0 \\
        --persistence-db ./runs.sqlite \\
        --host 0.0.0.0 --port 8000 \\
        --workers 4

Env-переменные (взамен флагов):
    PERSISTENCE_DB=./runs.sqlite
    REDIS_URL=redis://localhost:6379/0
    ANTHROPIC_API_KEY=sk-ant-...
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    persistence_db = _resolve_persistence_db(args)
    redis_url = args.redis_url or os.getenv("REDIS_URL")
    auth_users = args.auth_users or os.getenv("AUTH_USERS")

    # Установка через env — create_app поднимет окружение при импорте.
    if persistence_db:
        os.environ["EKCELO_PERSISTENCE_DB"] = str(persistence_db)
    if redis_url:
        os.environ["EKCELO_REDIS_URL"] = redis_url
    if auth_users:
        os.environ["EKCELO_AUTH_USERS"] = auth_users

    try:
        import uvicorn
    except ImportError:
        print(
            "error: uvicorn не установлен. Установите extras:\n"
            "    pip install -e \".[orchestrator-web]\"",
            file=sys.stderr,
        )
        return 3

    uvicorn.run(
        "lot_orchestrator_web.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def _resolve_persistence_db(args) -> Path | None:
    val = args.persistence_db or os.getenv("PERSISTENCE_DB")
    return Path(val) if val else None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ekcelo-orchestrate-web",
        description="FastAPI web-сервер orchestrator'а (тонкая обёртка над uvicorn).",
    )
    p.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    p.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    p.add_argument("--workers", type=int, default=1,
                   help="Кол-во worker-процессов. >1 требует --redis-url (multi-worker store).")
    p.add_argument("--reload", action="store_true",
                   help="Auto-reload при изменении кода (dev only).")
    p.add_argument("--log-level", default="info",
                   choices=["critical", "error", "warning", "info", "debug", "trace"])
    p.add_argument("--persistence-db",
                   help="Путь к SQLite snapshot store. Также читается из env PERSISTENCE_DB.")
    p.add_argument("--redis-url",
                   help="Redis URL для multi-worker (например, redis://localhost:6379/0). "
                        "Также читается из env REDIS_URL.")
    p.add_argument("--auth-users",
                   help="HTTP Basic Auth: 'user1:pass1,user2:pass2'. Также читается из env "
                        "AUTH_USERS. Если не задано — auth отключён.")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
