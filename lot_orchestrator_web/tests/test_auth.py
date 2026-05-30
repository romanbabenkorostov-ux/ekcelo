"""HTTP Basic Auth middleware (cycle 12)."""
from __future__ import annotations

from base64 import b64encode

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.auth import _Creds, maybe_install_basic_auth
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _basic(user: str, password: str) -> dict:
    token = b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ─────────────────────────────────────────────────────────────────────────────
#  _Creds parser
# ─────────────────────────────────────────────────────────────────────────────

def test_creds_from_env_single_user():
    creds = _Creds.from_env("alice:secret")
    assert creds is not None
    assert creds.users == {"alice": "secret"}


def test_creds_from_env_multiple_users():
    creds = _Creds.from_env("alice:s1, bob:s2 ,charlie:s3")
    assert creds is not None
    assert creds.users == {"alice": "s1", "bob": "s2", "charlie": "s3"}


def test_creds_from_env_none_when_empty():
    assert _Creds.from_env("") is None
    assert _Creds.from_env(None) is None


def test_creds_from_env_skips_malformed():
    """Записи без `:` пропускаются."""
    creds = _Creds.from_env("alice:s1,bad-no-colon,bob:s2")
    assert creds is not None
    assert creds.users == {"alice": "s1", "bob": "s2"}


def test_creds_from_env_uses_env_if_not_passed(monkeypatch):
    monkeypatch.setenv("EKCELO_AUTH_USERS", "alice:secret")
    creds = _Creds.from_env()
    assert creds is not None
    assert "alice" in creds.users


# ─────────────────────────────────────────────────────────────────────────────
#  maybe_install_basic_auth
# ─────────────────────────────────────────────────────────────────────────────

def test_install_returns_false_when_no_creds(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x")
    # maybe_install_basic_auth уже вызван в create_app — без env вернёт False.
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200  # без auth


def test_install_protects_root_when_users_passed(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users="alice:secret")
    client = TestClient(app)
    # Без header → 401.
    response = client.get("/")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate", "").startswith("Basic")
    # С правильным header → 200.
    response = client.get("/", headers=_basic("alice", "secret"))
    assert response.status_code == 200


def test_wrong_password_rejected(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users="alice:secret")
    client = TestClient(app)
    response = client.get("/", headers=_basic("alice", "wrong"))
    assert response.status_code == 401


def test_unknown_user_rejected(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users="alice:secret")
    client = TestClient(app)
    response = client.get("/", headers=_basic("bob", "secret"))
    assert response.status_code == 401


def test_malformed_authorization_header_rejected(monkeypatch):
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users="alice:secret")
    client = TestClient(app)
    # Не "Basic".
    response = client.get("/", headers={"Authorization": "Bearer token"})
    assert response.status_code == 401
    # Невалидный base64.
    response = client.get("/", headers={"Authorization": "Basic !!!invalid!!!"})
    assert response.status_code == 401


def test_static_and_docs_paths_exempt(monkeypatch):
    """`/static/*`, `/docs`, `/openapi.json`, `/redoc` не требуют auth."""
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users="alice:secret")
    client = TestClient(app)
    # /openapi.json без auth → 200.
    response = client.get("/openapi.json")
    assert response.status_code == 200
    # /docs без auth → 200.
    response = client.get("/docs")
    assert response.status_code == 200


def test_api_endpoint_protected_too(monkeypatch, tmp_path):
    """POST /lots/.../run требует auth."""
    monkeypatch.delenv("EKCELO_AUTH_USERS", raising=False)
    settings = Settings(anthropic_api_key="dummy")
    app = create_app(settings=settings, mock_llm_text="x",
                     auth_users="alice:secret")
    client = TestClient(app)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    response = client.post(
        "/lots/x/run",
        json={"workspace_path": str(workspace)},
    )
    assert response.status_code == 401
    response = client.post(
        "/lots/x/run",
        json={"workspace_path": str(workspace)},
        headers=_basic("alice", "secret"),
    )
    assert response.status_code == 202
