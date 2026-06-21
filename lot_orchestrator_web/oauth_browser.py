"""OAuth2 Authorization Code flow для браузера (cycle 14 M2).

Дополняет cycle 14 M1 (Bearer-валидация) browser-сценарием:
- `GET /auth/login` → редирект на authorize_url IdP с state (CSRF-защита).
- `GET /auth/callback?code&state` → обмен code на токен, установка
  session-cookie `ekcelo_token`, редирект на `post_login_redirect`.
- `GET /auth/logout` → очистка cookie.

После callback OAuthMiddleware (M1) читает токен из cookie (см.
`oauth.SESSION_COOKIE`) и валидирует как обычный Bearer.

Token-exchange (`code → token`) вынесен в инъектируемый `token_exchanger`
callable — production использует urllib (stdlib, без httpx), тесты подменяют
mock'ом без реального IdP.

Конфиг через env (browser-flow):
- `EKCELO_OIDC_CLIENT_ID`
- `EKCELO_OIDC_CLIENT_SECRET`
- `EKCELO_OIDC_AUTHORIZE_URL`  (IdP authorize endpoint)
- `EKCELO_OIDC_TOKEN_URL`      (IdP token endpoint)
- `EKCELO_OIDC_REDIRECT_URI`   (наш /auth/callback URL)
- `EKCELO_OIDC_SCOPES`         (default "openid profile email")

См. также: `oauth.py` (M1 Bearer + OIDCConfig + OAuthMiddleware).
"""
from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from lot_orchestrator_web.oauth import SESSION_COOKIE


_STATE_COOKIE = "ekcelo_oauth_state"


class OAuthBrowserConfigError(Exception):
    """Неполный browser-flow конфиг."""


# Тип инъектируемого обменника: (code, config) → token-response dict.
TokenExchanger = Callable[[str, "OAuthBrowserConfig"], dict]


@dataclass(frozen=True)
class OAuthBrowserConfig:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scopes: str = "openid profile email"
    post_login_redirect: str = "/"
    cookie_secure: bool = True       # Secure-флаг cookie (HTTPS). False для local dev.
    cookie_max_age_s: int = 3600

    @classmethod
    def from_env(cls) -> "OAuthBrowserConfig | None":
        """Читает env. None если client_id не задан (browser-flow выключен)."""
        client_id = os.environ.get("EKCELO_OIDC_CLIENT_ID")
        if not client_id:
            return None
        required = {
            "EKCELO_OIDC_CLIENT_SECRET": os.environ.get("EKCELO_OIDC_CLIENT_SECRET"),
            "EKCELO_OIDC_AUTHORIZE_URL": os.environ.get("EKCELO_OIDC_AUTHORIZE_URL"),
            "EKCELO_OIDC_TOKEN_URL": os.environ.get("EKCELO_OIDC_TOKEN_URL"),
            "EKCELO_OIDC_REDIRECT_URI": os.environ.get("EKCELO_OIDC_REDIRECT_URI"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise OAuthBrowserConfigError(
                f"browser-flow: заданы не все env: отсутствуют {missing}"
            )
        return cls(
            client_id=client_id,
            client_secret=required["EKCELO_OIDC_CLIENT_SECRET"],
            authorize_url=required["EKCELO_OIDC_AUTHORIZE_URL"],
            token_url=required["EKCELO_OIDC_TOKEN_URL"],
            redirect_uri=required["EKCELO_OIDC_REDIRECT_URI"],
            scopes=os.environ.get("EKCELO_OIDC_SCOPES", "openid profile email"),
            post_login_redirect=os.environ.get("EKCELO_OIDC_POST_LOGIN", "/"),
            cookie_secure=os.environ.get("EKCELO_OIDC_COOKIE_SECURE", "true").lower()
                          not in {"0", "false", "no"},
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Token exchange (default: urllib)
# ─────────────────────────────────────────────────────────────────────────────

def urllib_token_exchanger(code: str, config: OAuthBrowserConfig) -> dict:
    """POST code на token_url IdP. Возвращает JSON-ответ (с access_token/id_token)."""
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
    }).encode("utf-8")
    req = urllib.request.Request(
        config.token_url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _token_from_response(payload: dict) -> str:
    """Достаёт JWT для session-cookie. Предпочитает id_token, затем access_token."""
    return payload.get("id_token") or payload.get("access_token") or ""


# ─────────────────────────────────────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────────────────────────────────────

def register_auth_routes(
    app: FastAPI,
    *,
    config: OAuthBrowserConfig | None = None,
    token_exchanger: TokenExchanger | None = None,
) -> bool:
    """Регистрирует `/auth/login`, `/auth/callback`, `/auth/logout`.

    Если `config` None (browser-flow не сконфигурирован) — роуты НЕ регистрируются,
    возвращает False. Иначе True.

    `token_exchanger` — для тестов; default `urllib_token_exchanger`.
    """
    cfg = config or OAuthBrowserConfig.from_env()
    if cfg is None:
        return False
    exchanger = token_exchanger or urllib_token_exchanger

    @app.get("/auth/login")
    async def auth_login() -> RedirectResponse:
        state = secrets.token_urlsafe(24)
        params = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": cfg.scopes,
            "state": state,
        })
        resp = RedirectResponse(
            url=f"{cfg.authorize_url}?{params}", status_code=307,
        )
        # state в httponly-cookie для проверки на callback (CSRF-защита)
        resp.set_cookie(
            _STATE_COOKIE, state, max_age=600, httponly=True,
            secure=cfg.cookie_secure, samesite="lax",
        )
        return resp

    @app.get("/auth/callback")
    async def auth_callback(request: Request, code: str = "", state: str = ""):
        if not code:
            raise HTTPException(status_code=400, detail="missing code")
        expected_state = request.cookies.get(_STATE_COOKIE)
        if not expected_state or state != expected_state:
            raise HTTPException(status_code=400, detail="state mismatch (CSRF)")
        try:
            payload = exchanger(code, cfg)
        except Exception as exc:  # noqa: BLE001 — внешний IdP, любой сбой → 502
            raise HTTPException(
                status_code=502, detail=f"token exchange failed: {exc}",
            ) from exc
        token = _token_from_response(payload)
        if not token:
            raise HTTPException(
                status_code=502,
                detail="token endpoint не вернул id_token/access_token",
            )
        resp = RedirectResponse(url=cfg.post_login_redirect, status_code=307)
        resp.set_cookie(
            SESSION_COOKIE, token, max_age=cfg.cookie_max_age_s,
            httponly=True, secure=cfg.cookie_secure, samesite="lax",
        )
        resp.delete_cookie(_STATE_COOKIE)
        return resp

    @app.get("/auth/logout")
    async def auth_logout() -> JSONResponse:
        resp = JSONResponse(content={"detail": "logged out"})
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    return True
