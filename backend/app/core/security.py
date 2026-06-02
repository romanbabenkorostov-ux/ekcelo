"""Security — auth middleware.

Re-export `lot_orchestrator_web.auth` (Basic Auth middleware) — будет
доступен после merge PR #93. До merge — `ImportError` пробрасывается
лениво, чтобы импорт `backend.app.core` не падал на main.
"""
from __future__ import annotations


def install_basic_auth(app, *, raw_users_env: str | None = None) -> bool:
    """Подключает Basic Auth если EKCELO_AUTH_USERS задан.

    Lazy-import, чтобы на main (без PR #93) `from backend.app.core import *`
    не падал.
    """
    try:
        from lot_orchestrator_web.auth import maybe_install_basic_auth
    except ImportError:
        return False
    return maybe_install_basic_auth(app, raw_users_env=raw_users_env)


__all__ = ["install_basic_auth"]
