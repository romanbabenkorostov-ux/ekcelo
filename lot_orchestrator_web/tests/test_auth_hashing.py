"""Cycle 13: интеграция hash-паролей в auth middleware."""
from __future__ import annotations

import warnings
from base64 import b64encode

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.auth import _Creds
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.password import hash_password
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _basic(user: str, password: str) -> dict:
    return {"Authorization": "Basic " + b64encode(f"{user}:{password}".encode()).decode()}


# ── _Creds: plaintext detection + warning ─────────────────────────────────────

def test_creds_detect_plaintext_users():
    creds = _Creds.from_env("alice:plain,bob:plain2")
    assert sorted(creds.plaintext_users()) == ["alice", "bob"]


def test_creds_detect_no_plaintext_when_all_hashed():
    h_a = hash_password("a")
    h_b = hash_password("b")
    creds = _Creds.from_env(f"alice:{h_a},bob:{h_b}")
    assert creds.plaintext_users() == []


def test_warning_emitted_for_plaintext(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _Creds.from_env("alice:plain")
    msgs = [str(w.message) for w in caught]
    assert any("plaintext" in m and "alice" in m for m in msgs)


def test_no_warning_for_hashed(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    h = hash_password("secret")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _Creds.from_env(f"alice:{h}")
    msgs = [str(w.message) for w in caught]
    assert not any("plaintext" in m for m in msgs)


# ── HTTP-уровень: хешированный пароль принимается ─────────────────────────────

def test_hashed_user_can_login(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    h = hash_password("topsecret")
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users=f"alice:{h}")
    client = TestClient(app)
    # Без header → 401.
    assert client.get("/").status_code == 401
    # Правильный пароль → 200.
    assert client.get("/", headers=_basic("alice", "topsecret")).status_code == 200
    # Неверный пароль → 401.
    assert client.get("/", headers=_basic("alice", "wrong")).status_code == 401


def test_hashed_and_plaintext_coexist(monkeypatch):
    """Hashed пользователь + plaintext пользователь работают одновременно."""
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    h = hash_password("h_secret")
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users=f"alice:{h},bob:plain")
    client = TestClient(app)
    assert client.get("/", headers=_basic("alice", "h_secret")).status_code == 200
    assert client.get("/", headers=_basic("bob", "plain")).status_code == 200
    assert client.get("/", headers=_basic("alice", "plain")).status_code == 401
    assert client.get("/", headers=_basic("bob", "h_secret")).status_code == 401


def test_hash_not_accidentally_matched_as_password(monkeypatch):
    """Атака: попытка авторизоваться, передав сам хеш как пароль → 401."""
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    h = hash_password("real_secret")
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users=f"alice:{h}")
    client = TestClient(app)
    # Передаём сам хеш как пароль → должно быть 401.
    assert client.get("/", headers=_basic("alice", h)).status_code == 401
