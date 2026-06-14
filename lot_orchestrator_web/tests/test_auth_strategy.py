"""Auth strategy dispatcher: OIDC > Basic > none (cycle 14, M1)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI

from lot_orchestrator_web.oauth import OIDCConfig, maybe_install_auth


def test_dispatcher_returns_none_without_config(monkeypatch):
    for k in ("EKCELO_OIDC_ISSUER", "EKCELO_AUTH_USERS"):
        monkeypatch.delenv(k, raising=False)
    app = FastAPI()
    assert maybe_install_auth(app) == "none"


def test_dispatcher_picks_basic_when_users_set(monkeypatch):
    monkeypatch.delenv("EKCELO_OIDC_ISSUER", raising=False)
    app = FastAPI()
    with pytest.warns(UserWarning):
        result = maybe_install_auth(app, raw_users_env="alice:secret")
    assert result == "basic"


def test_dispatcher_picks_oidc_when_config_passed():
    cfg = OIDCConfig(
        issuer="https://idp", audience="api",
        jwks={"keys": []}, algorithms=("HS256",),
    )
    app = FastAPI()
    result = maybe_install_auth(
        app, oidc_config=cfg, hmac_secret="s",
        raw_users_env="alice:x",  # должен игнорироваться
    )
    assert result == "oidc"


def test_dispatcher_picks_oidc_when_env_set(monkeypatch):
    monkeypatch.setenv("EKCELO_OIDC_ISSUER", "https://idp")
    monkeypatch.setenv("EKCELO_OIDC_AUDIENCE", "api")
    monkeypatch.setenv("EKCELO_OIDC_JWKS_URL", "https://idp/jwks")
    app = FastAPI()
    result = maybe_install_auth(app, hmac_secret="s")
    assert result == "oidc"


def test_dispatcher_oidc_wins_over_basic(monkeypatch):
    """Если задан И OIDC, И BasicAuth — побеждает OIDC."""
    monkeypatch.setenv("EKCELO_OIDC_ISSUER", "https://idp")
    monkeypatch.setenv("EKCELO_OIDC_AUDIENCE", "api")
    monkeypatch.setenv("EKCELO_OIDC_JWKS_URL", "https://idp/jwks")
    app = FastAPI()
    result = maybe_install_auth(
        app, raw_users_env="alice:x", hmac_secret="s",
    )
    assert result == "oidc"
