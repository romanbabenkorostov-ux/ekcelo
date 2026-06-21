"""Cycle 15 M4 — enforce_rbac wire-up + Basic Auth roles-карта.

Проверяет:
- `create_app(enforce_rbac=True)` навешивает require_action на боевые роуты.
- Basic Auth кладёт Subject с ролями из auth_roles в request.state.
- backward-compat: enforce_rbac=False (default) — роуты открыты как раньше.
"""
from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.auth import parse_roles_map
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.rbac import (
    Action,
    Grant,
    Resource,
    ResourceType,
)
from lot_orchestrator_web.rbac_store import SQLiteGrantStore
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _seed_ekcelo(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT,
            area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER
        );
        CREATE TABLE entity_registry (inn TEXT PRIMARY KEY, name_full TEXT NOT NULL,
            name_short TEXT, ogrn TEXT, entity_type TEXT);
        CREATE TABLE rights (id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
            right_type TEXT NOT NULL, right_holder_inn TEXT, share_numerator INTEGER,
            share_denominator INTEGER, registration_number TEXT, registration_date TEXT);
        CREATE TABLE extracts (id INTEGER PRIMARY KEY AUTOINCREMENT, extract_number TEXT,
            cad_number TEXT NOT NULL, extract_date TEXT NOT NULL);
        """)
        conn.execute("INSERT INTO objects(cad_number, object_type, address) "
                     "VALUES ('61:44:0050706:31', 'room', 'Ростов')")
        conn.commit()
    finally:
        conn.close()


def _basic(user: str, pw: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ─────────────────────────────────────────────────────────────────────────────
#  parse_roles_map
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_roles_map_basic():
    m = parse_roles_map("alice:assessor,bob:client")
    assert m == {"alice": ("assessor",), "bob": ("client",)}


def test_parse_roles_map_multiple_roles():
    m = parse_roles_map("root:superadmin|assessor")
    assert m == {"root": ("superadmin", "assessor")}


def test_parse_roles_map_empty():
    assert parse_roles_map(None) == {}
    assert parse_roles_map("") == {}


def test_parse_roles_map_skips_malformed():
    m = parse_roles_map("alice:assessor,garbage-no-colon,bob:client")
    assert set(m) == {"alice", "bob"}


# ─────────────────────────────────────────────────────────────────────────────
#  enforce_rbac=False (backward-compat)
# ─────────────────────────────────────────────────────────────────────────────

def test_routes_open_when_enforce_rbac_false(tmp_path: Path):
    db = tmp_path / "ekcelo.sqlite"
    _seed_ekcelo(db)
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    client = TestClient(create_app(
        settings=settings, mock_llm_text="x", ekcelo_db=db,
        enforce_rbac=False,
    ))
    # без auth и без enforce — 200
    resp = client.get("/objects/61:44:0050706:31")
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
#  enforce_rbac=True — полный путь с Basic Auth + roles + grants
# ─────────────────────────────────────────────────────────────────────────────

def _app_enforced(tmp_path: Path, *, grants: list[Grant] | None = None):
    ekcelo = tmp_path / "ekcelo.sqlite"
    _seed_ekcelo(ekcelo)
    access = tmp_path / "access.sqlite"
    store = SQLiteGrantStore(access)
    for g in (grants or []):
        store.add(g)
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(
        settings=settings, mock_llm_text="x",
        ekcelo_db=ekcelo, access_db=access,
        auth_users="alice:secret,root:secret,charlie:secret",
        auth_roles="alice:assessor,root:superadmin,charlie:client",
        enforce_rbac=True,
    )
    return TestClient(app)


def test_enforce_denies_assessor_without_grant(tmp_path: Path):
    client = _app_enforced(tmp_path)
    resp = client.get("/objects/61:44:0050706:31", headers=_basic("alice", "secret"))
    assert resp.status_code == 403


def test_enforce_allows_assessor_with_grant(tmp_path: Path):
    grant = Grant(
        subject_sub="alice", action=Action.VIEW,
        resource=Resource(ResourceType.OBJECT, "61:44:0050706:31"),
        granted_by="root",
    )
    client = _app_enforced(tmp_path, grants=[grant])
    resp = client.get("/objects/61:44:0050706:31", headers=_basic("alice", "secret"))
    assert resp.status_code == 200


def test_enforce_superadmin_bypasses(tmp_path: Path):
    client = _app_enforced(tmp_path)
    resp = client.get("/objects/61:44:0050706:31", headers=_basic("root", "secret"))
    assert resp.status_code == 200


def test_enforce_lot_route_protected(tmp_path: Path):
    client = _app_enforced(tmp_path)
    # lot-route требует VIEW lot; alice без гранта → 403
    resp = client.get("/lots/lot-001", headers=_basic("alice", "secret"))
    assert resp.status_code == 403


def test_enforce_graph_route_protected(tmp_path: Path):
    client = _app_enforced(tmp_path)
    resp = client.get("/objects/61:44:0050706:31/graph", headers=_basic("alice", "secret"))
    assert resp.status_code == 403


def test_enforce_graph_allowed_with_object_grant(tmp_path: Path):
    grant = Grant(
        subject_sub="alice", action=Action.VIEW,
        resource=Resource(ResourceType.OBJECT, "61:44:0050706:31"),
        granted_by="root",
    )
    client = _app_enforced(tmp_path, grants=[grant])
    resp = client.get("/objects/61:44:0050706:31/graph", headers=_basic("alice", "secret"))
    assert resp.status_code == 200


def test_enforce_catalog_not_protected(tmp_path: Path):
    """/catalog — листинг, не per-resource; в M4 НЕ под require_action."""
    client = _app_enforced(tmp_path)
    resp = client.get("/catalog", headers=_basic("alice", "secret"))
    assert resp.status_code == 200


def test_basic_auth_injects_subject_with_roles(tmp_path: Path):
    """root (superadmin) проходит — значит Subject с ролью лёг в request.state."""
    client = _app_enforced(tmp_path)
    # superadmin минует проверку гранта → если бы Subject не лёг,
    # был бы anonymous → 403. Получаем 200 → роль доехала.
    resp = client.get("/objects/61:44:0050706:31", headers=_basic("root", "secret"))
    assert resp.status_code == 200
    # а client (charlie) без гранта → 403 (роль client, нет VIEW-гранта)
    resp2 = client.get("/objects/61:44:0050706:31", headers=_basic("charlie", "secret"))
    assert resp2.status_code == 403


def test_enforce_no_auth_is_anonymous_denied(tmp_path: Path):
    """enforce_rbac=True + Basic Auth: без credentials → 401 от auth middleware."""
    client = _app_enforced(tmp_path)
    resp = client.get("/objects/61:44:0050706:31")
    assert resp.status_code == 401  # auth middleware раньше require_action
