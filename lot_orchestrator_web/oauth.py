"""OIDC/JWT auth middleware (cycle 14).

Реализует Bearer-JWT валидацию по конфигу OIDC-провайдера (issuer, audience,
JWKS). Используется вместо/совместно с Basic Auth (`auth.py`).

Стратегия диспетчера (см. `maybe_install_auth`):
1. Если задан `EKCELO_OIDC_ISSUER` (+ JWKS источник) → `OAuthMiddleware`.
2. Иначе если `EKCELO_AUTH_USERS` → `BasicAuthMiddleware`.
3. Иначе — без auth (dev-режим).

Архитектура (M1 — этот sub-stage):
- `OIDCConfig` — нормированный конфиг (issuer, audience, JWKS).
- `JWKSProvider` — источник публичных ключей (dict, URL, или callable).
- `verify_jwt(token, config) → Claims` — основная валидация.
- `OAuthMiddleware` — ASGI: извлекает Bearer → verify → `request.state.subject`.
- `Subject(sub, roles, claims)` — что middleware кладёт в request.state.

M2 (будущий sub-stage): `/auth/login` + `/auth/callback` browser code-flow.
M3 (cycle 15): RBAC поверх `Subject.roles`.

См. также:
- `lot_orchestrator_web/auth.py` (Basic Auth, остаётся работать).
- `obsidian/Architecture/roadmap-2026-06.md` §Cycle 14.
- `contracts/roles/ROLES_SPEC.md` (C6, что роли значат).

Зависимости:
- `PyJWT[crypto]` (RS256) ИЛИ `PyJWT` без crypto (только HS256, для теста/dev).
- Если PyJWT недоступен — модуль импортируется, но `OAuthMiddleware` падает с
  ясной ошибкой при попытке использования.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


# ─────────────────────────────────────────────────────────────────────────────
#  Опц. зависимость PyJWT — soft import
# ─────────────────────────────────────────────────────────────────────────────

try:
    import jwt as _pyjwt
    from jwt import PyJWKClient
    _PYJWT_AVAILABLE = True
except ImportError:  # pragma: no cover — путь для CI без extras
    _pyjwt = None  # type: ignore[assignment]
    PyJWKClient = None  # type: ignore[assignment,misc]
    _PYJWT_AVAILABLE = False


class OAuthConfigError(Exception):
    """Невалидный/неполный OIDC-конфиг."""


class JWTVerificationError(Exception):
    """Токен не прошёл валидацию (подпись, expiry, audience, issuer)."""


# ─────────────────────────────────────────────────────────────────────────────
#  Конфиг
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OIDCConfig:
    """Нормированный OIDC-конфиг.

    issuer       — URL Identity Provider (значение `iss` claim, точное совпадение).
    audience     — ожидаемое `aud` (string ИЛИ tuple строк; при tuple — хотя бы одно).
    jwks         — dict {"keys": [JWK,...]} ИЛИ URL для скачивания, ИЛИ callable.
    algorithms   — допустимые alg (`["RS256"]` стандарт; HS256 для теста).
    leeway_s     — допуск к expiry/nbf (для clock-skew).
    roles_claim  — путь к ролям в claims (строка типа "roles" или "realm_access.roles").
    """
    issuer: str
    audience: str | tuple[str, ...]
    jwks: dict[str, Any] | str | Callable[[], dict[str, Any]]
    algorithms: tuple[str, ...] = ("RS256",)
    leeway_s: int = 30
    roles_claim: str = "roles"

    @classmethod
    def from_env(cls) -> "OIDCConfig | None":
        """Читает env `EKCELO_OIDC_*`. Возвращает None если issuer не задан."""
        issuer = os.environ.get("EKCELO_OIDC_ISSUER")
        if not issuer:
            return None
        audience = os.environ.get("EKCELO_OIDC_AUDIENCE")
        if not audience:
            raise OAuthConfigError(
                "EKCELO_OIDC_ISSUER задан, но EKCELO_OIDC_AUDIENCE пуст"
            )
        jwks_url = os.environ.get("EKCELO_OIDC_JWKS_URL")
        if not jwks_url:
            raise OAuthConfigError(
                "EKCELO_OIDC_ISSUER задан, но EKCELO_OIDC_JWKS_URL пуст"
            )
        algorithms_env = os.environ.get("EKCELO_OIDC_ALGORITHMS", "RS256")
        algorithms = tuple(a.strip() for a in algorithms_env.split(",") if a.strip())
        roles_claim = os.environ.get("EKCELO_OIDC_ROLES_CLAIM", "roles")
        return cls(
            issuer=issuer, audience=audience, jwks=jwks_url,
            algorithms=algorithms, roles_claim=roles_claim,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  JWKS provider (опц. cache)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _CachedJWKS:
    data: dict[str, Any]
    fetched_at: float


class JWKSProvider:
    """Тонкая обёртка с TTL-кешем над dict/URL/callable.

    Для тестов используйте `JWKSProvider(static={"keys":[...]})` — без HTTP.
    Для прод используйте URL — pulled с TTL 10 минут.
    """

    def __init__(
        self,
        source: dict[str, Any] | str | Callable[[], dict[str, Any]],
        *,
        ttl_s: int = 600,
        http_timeout_s: int = 5,
    ) -> None:
        self._source = source
        self._ttl_s = ttl_s
        self._timeout = http_timeout_s
        self._cache: _CachedJWKS | None = None

    def get_keys(self) -> dict[str, Any]:
        now = time.time()
        if self._cache and (now - self._cache.fetched_at) < self._ttl_s:
            return self._cache.data
        data = self._fetch()
        self._cache = _CachedJWKS(data=data, fetched_at=now)
        return data

    def _fetch(self) -> dict[str, Any]:
        src = self._source
        if isinstance(src, dict):
            return src
        if callable(src):
            return src()
        # URL
        req = urllib.request.Request(src, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
#  JWT verify
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Subject:
    """Что middleware кладёт в `request.state.subject` после валидации."""
    sub: str
    roles: tuple[str, ...] = ()
    claims: dict[str, Any] = field(default_factory=dict)


def verify_jwt(
    token: str,
    config: OIDCConfig,
    jwks_provider: JWKSProvider,
    *,
    hmac_secret: str | None = None,
) -> Subject:
    """Валидирует JWT и возвращает `Subject`.

    Алгоритм:
    1. Decode header → получить `kid`/`alg`.
    2. Найти JWK по `kid` в JWKS (для RS256+). Для HS256 (тест) — `hmac_secret`.
    3. `jwt.decode(token, key, algorithms, audience, issuer, leeway)`.
    4. Извлечь `sub` + роли по `roles_claim`.

    Raises:
        JWTVerificationError — любая ошибка валидации (подпись, expiry, aud, iss).
        OAuthConfigError — PyJWT не установлен / конфиг невалидный.
    """
    if not _PYJWT_AVAILABLE:
        raise OAuthConfigError(
            "PyJWT не установлен. Установите: pip install 'PyJWT[crypto]'"
        )
    try:
        header = _pyjwt.get_unverified_header(token)
    except Exception as exc:
        raise JWTVerificationError(f"битый JWT-header: {exc}") from exc

    alg = header.get("alg")
    if alg not in config.algorithms:
        raise JWTVerificationError(
            f"alg={alg} не в разрешённых {list(config.algorithms)}"
        )

    if alg.startswith("HS"):
        if not hmac_secret:
            raise OAuthConfigError(
                "HS-алгоритм требует hmac_secret (для теста/dev)"
            )
        key: Any = hmac_secret
    else:
        kid = header.get("kid")
        key = _resolve_jwk(jwks_provider.get_keys(), kid)
        if key is None:
            raise JWTVerificationError(f"JWK с kid={kid!r} не найден")

    try:
        claims = _pyjwt.decode(
            token, key,
            algorithms=list(config.algorithms),
            audience=config.audience,
            issuer=config.issuer,
            leeway=config.leeway_s,
        )
    except _pyjwt.ExpiredSignatureError as exc:
        raise JWTVerificationError(f"expired: {exc}") from exc
    except _pyjwt.InvalidAudienceError as exc:
        raise JWTVerificationError(f"audience: {exc}") from exc
    except _pyjwt.InvalidIssuerError as exc:
        raise JWTVerificationError(f"issuer: {exc}") from exc
    except _pyjwt.InvalidSignatureError as exc:
        raise JWTVerificationError(f"signature: {exc}") from exc
    except _pyjwt.PyJWTError as exc:
        raise JWTVerificationError(f"jwt: {exc}") from exc

    sub_val = claims.get("sub")
    if not sub_val:
        raise JWTVerificationError("отсутствует claim 'sub'")

    roles = _extract_roles(claims, config.roles_claim)
    return Subject(sub=str(sub_val), roles=tuple(roles), claims=claims)


def _resolve_jwk(jwks: dict[str, Any], kid: str | None) -> Any:
    """Найти PyJWK по `kid` из набора. Возвращает None если не найден."""
    keys = jwks.get("keys", [])
    if not keys:
        return None
    if not kid:
        # Без kid возвращаем первый ключ (legacy провайдеры)
        return _pyjwt.PyJWK(keys[0]).key if _PYJWT_AVAILABLE else None
    for k in keys:
        if k.get("kid") == kid:
            return _pyjwt.PyJWK(k).key
    return None


def _extract_roles(claims: dict[str, Any], path: str) -> list[str]:
    """Извлекает роли по dotted-path (например 'realm_access.roles')."""
    cur: Any = claims
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return []
        cur = cur[part]
    if isinstance(cur, str):
        return [cur]
    if isinstance(cur, list):
        return [str(x) for x in cur]
    return []


# ─────────────────────────────────────────────────────────────────────────────
#  ASGI middleware
# ─────────────────────────────────────────────────────────────────────────────

# Пути, не требующие auth (по аналогии с BasicAuthMiddleware):
_EXEMPT_PREFIXES = ("/static/", "/docs", "/openapi.json", "/redoc")


class OAuthMiddleware(BaseHTTPMiddleware):
    """Bearer-JWT валидация для всех роутов кроме статики/докуменации."""

    def __init__(
        self,
        app,
        *,
        config: OIDCConfig,
        jwks_provider: JWKSProvider | None = None,
        hmac_secret: str | None = None,
    ) -> None:
        super().__init__(app)
        self._config = config
        self._jwks = jwks_provider or JWKSProvider(config.jwks)
        self._hmac_secret = hmac_secret

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES) or path == "/":
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return _unauthorized("missing Bearer token")
        token = auth.split(" ", 1)[1].strip()

        try:
            subject = verify_jwt(
                token, self._config, self._jwks,
                hmac_secret=self._hmac_secret,
            )
        except JWTVerificationError as exc:
            return _unauthorized(str(exc))

        request.state.subject = subject
        return await call_next(request)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": 'Bearer realm="ekcelo"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Стратегия диспетчер
# ─────────────────────────────────────────────────────────────────────────────

def maybe_install_auth(
    app,
    *,
    oidc_config: OIDCConfig | None = None,
    raw_users_env: str | None = None,
    raw_roles_env: str | None = None,
    hmac_secret: str | None = None,
) -> str:
    """Выбирает auth-стратегию: OIDC > Basic > none. Возвращает имя установленной.

    OIDC побеждает если `oidc_config` передан явно ИЛИ env `EKCELO_OIDC_*` задан.
    Иначе fallback на Basic Auth (как раньше).

    hmac_secret — для тестов/dev (HS256 algoritm). В prod — RS256 через JWKS URL.
    raw_roles_env — cycle 15 M4: связь username с RBAC-ролями для Basic Auth.
    """
    from lot_orchestrator_web.auth import maybe_install_basic_auth

    cfg = oidc_config or OIDCConfig.from_env()
    if cfg is not None:
        app.add_middleware(
            OAuthMiddleware,
            config=cfg, jwks_provider=JWKSProvider(cfg.jwks),
            hmac_secret=hmac_secret,
        )
        return "oidc"
    if maybe_install_basic_auth(
        app, raw_users_env=raw_users_env, raw_roles_env=raw_roles_env,
    ):
        return "basic"
    return "none"
