"""Опциональная HTTP Basic Auth (cycle 12).

Pragmatic минимум для single-user / pair-of-users сценариев. Для production
multi-tenant / SSO — рекомендуется reverse-proxy (oauth2-proxy, nginx auth,
traefik forward-auth) + полное отключение этого модуля.

Активация — через env `EKCELO_AUTH_USERS` (формат `user1:pass1,user2:pass2`).
Если переменная не задана — middleware не подключается, поведение как раньше.
"""
from __future__ import annotations

import os
import secrets
from base64 import b64decode
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass(frozen=True)
class _Creds:
    users: dict[str, str]  # username → password (plain — для production hashed-store см. cycle 13+)

    @classmethod
    def from_env(cls, raw: str | None = None) -> "_Creds | None":
        raw = raw if raw is not None else os.getenv("EKCELO_AUTH_USERS")
        if not raw:
            return None
        users = {}
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            user, _, password = entry.partition(":")
            users[user.strip()] = password.strip()
        return cls(users=users) if users else None


_EXEMPT_PATHS = frozenset({"/static", "/docs", "/openapi.json", "/redoc"})


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Защищает все routes кроме `/static/*`, `/docs`, `/openapi.json`, `/redoc`.

    Прокси-friendly: WWW-Authenticate header при 401 → браузер показывает диалог.
    """

    def __init__(self, app, creds: _Creds):
        super().__init__(app)
        self._creds = creds

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path == p or request.url.path.startswith(p + "/")
               for p in _EXEMPT_PATHS):
            return await call_next(request)
        if not _verify(request, self._creds):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Basic realm=\"ekcelo\""},
            )
        return await call_next(request)


def _verify(request: Request, creds: _Creds) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return False
    try:
        decoded = b64decode(auth.split(" ", 1)[1].strip()).decode("utf-8", errors="replace")
    except Exception:
        return False
    user, _, password = decoded.partition(":")
    expected = creds.users.get(user)
    if expected is None:
        return False
    # secrets.compare_digest — защита от timing-side-channel.
    return secrets.compare_digest(password, expected)


def maybe_install_basic_auth(app, *, raw_users_env: str | None = None) -> bool:
    """Подключает Basic Auth если `EKCELO_AUTH_USERS` задан. Возвращает True если установлен.

    Возможные значения raw_users_env (override env):
        "alice:secret"               — один пользователь
        "alice:s1,bob:s2"            — несколько
        None / пустая строка / env  → middleware не устанавливается
    """
    creds = _Creds.from_env(raw_users_env)
    if creds is None:
        return False
    app.add_middleware(BasicAuthMiddleware, creds=creds)
    return True
