"""Cycle 15 M3 — RBAC FastAPI integration (grant endpoints + require_action)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from lot_orchestrator_web.oauth import Subject as OAuthSubject
from lot_orchestrator_web.rbac import (
    Action,
    Grant,
    InMemoryGrantStore,
    Resource,
    ResourceType,
    Role,
)
from lot_orchestrator_web.rbac_api import (
    get_principal,
    register_grant_routes,
    require_action,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Тестовое приложение с инъекцией Subject + grant_store
# ─────────────────────────────────────────────────────────────────────────────

def _build_app(store, subject: OAuthSubject | None):
    """FastAPI с middleware кладущим фиксированный subject + grant_store."""
    app = FastAPI()
    app.state.grant_store = store

    @app.middleware("http")
    async def _inject_subject(request: Request, call_next):
        if subject is not None:
            request.state.subject = subject
        return await call_next(request)

    register_grant_routes(app)

    # защищённый роут для тестов require_action
    @app.get(
        "/objects/{cad}/secret",
        dependencies=[Depends(require_action(Action.VIEW, ResourceType.OBJECT, "cad"))],
    )
    async def secret(cad: str):
        return {"cad": cad, "ok": True}

    return app


def _subject(sub: str, roles: tuple[str, ...]) -> OAuthSubject:
    return OAuthSubject(sub=sub, roles=roles, claims={})


OBJ = Resource(ResourceType.OBJECT, "61:44:0050706:31")
LOT = Resource(ResourceType.LOT, "lot-001")


# ─────────────────────────────────────────────────────────────────────────────
#  get_principal
# ─────────────────────────────────────────────────────────────────────────────

def test_get_principal_anonymous_when_no_subject():
    app = FastAPI()

    @app.get("/who")
    async def who(request: Request):
        p = get_principal(request)
        return {"sub": p.sub, "roles": sorted(r.value for r in p.roles)}

    resp = TestClient(app).get("/who")
    assert resp.json() == {"sub": "", "roles": []}


def test_get_principal_from_subject():
    app = _build_app(InMemoryGrantStore(), _subject("alice@x", ("assessor",)))

    @app.get("/who")
    async def who(request: Request):
        p = get_principal(request)
        return {"sub": p.sub, "roles": sorted(r.value for r in p.roles)}

    resp = TestClient(app).get("/who")
    assert resp.json() == {"sub": "alice@x", "roles": ["assessor"]}


# ─────────────────────────────────────────────────────────────────────────────
#  require_action — opt-in enforcement
# ─────────────────────────────────────────────────────────────────────────────

def test_require_action_open_when_no_store():
    # store=None → enforcement выключен → 200
    app = _build_app(None, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).get("/objects/61:44:0050706:31/secret")
    assert resp.status_code == 200


def test_require_action_denies_without_grant():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).get("/objects/61:44:0050706:31/secret")
    assert resp.status_code == 403


def test_require_action_allows_with_grant():
    store = InMemoryGrantStore()
    store.add(Grant(
        subject_sub="alice@x", action=Action.VIEW, resource=OBJ,
        granted_by="root",
    ))
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).get("/objects/61:44:0050706:31/secret")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_require_action_superadmin_bypasses():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("root@x", ("superadmin",)))
    resp = TestClient(app).get("/objects/61:44:0050706:31/secret")
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
#  POST /grants
# ─────────────────────────────────────────────────────────────────────────────

def test_post_grant_503_without_store():
    app = _build_app(None, _subject("root@x", ("superadmin",)))
    resp = TestClient(app).post("/grants", json={
        "subject_sub": "bob@x", "action": "view",
        "resource_type": "lot", "resource_id": "lot-001",
    })
    assert resp.status_code == 503


def test_post_grant_superadmin_delegates():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("root@x", ("superadmin",)))
    resp = TestClient(app).post("/grants", json={
        "subject_sub": "bob@x", "action": "edit",
        "resource_type": "lot", "resource_id": "lot-001",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["subject_sub"] == "bob@x"
    assert body["action"] == "edit"
    assert body["granted_by"] == "root@x"
    assert body["grant_id"]


def test_post_grant_assessor_delegates_what_they_have():
    store = InMemoryGrantStore()
    # alice имеет edit на lot-001
    store.add(Grant(
        subject_sub="alice@x", action=Action.EDIT, resource=LOT,
        granted_by="root",
    ))
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).post("/grants", json={
        "subject_sub": "bob@x", "action": "edit",
        "resource_type": "lot", "resource_id": "lot-001",
    })
    assert resp.status_code == 201


def test_post_grant_assessor_cannot_delegate_what_they_lack():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).post("/grants", json={
        "subject_sub": "bob@x", "action": "edit",
        "resource_type": "lot", "resource_id": "lot-001",
    })
    assert resp.status_code == 403


def test_post_grant_client_shares_view():
    store = InMemoryGrantStore()
    # charlie (client) видит bundle
    bundle = Resource(ResourceType.BUNDLE, "bundle-x")
    store.add(Grant(
        subject_sub="charlie@x", action=Action.VIEW, resource=bundle,
        granted_by="root",
    ))
    app = _build_app(store, _subject("charlie@x", ("client",)))
    resp = TestClient(app).post("/grants", json={
        "subject_sub": "guest@x", "action": "view",
        "resource_type": "bundle", "resource_id": "bundle-x",
    })
    assert resp.status_code == 201
    assert resp.json()["subject_sub"] == "guest@x"


def test_post_grant_client_cannot_share_edit():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("charlie@x", ("client",)))
    resp = TestClient(app).post("/grants", json={
        "subject_sub": "guest@x", "action": "edit",
        "resource_type": "bundle", "resource_id": "bundle-x",
    })
    # client + action=edit → попадает в delegate-ветку → 403 (не assessor)
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE /grants/{id}
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_grant_by_author():
    store = InMemoryGrantStore()
    gid = store.add(Grant(
        subject_sub="bob@x", action=Action.VIEW, resource=LOT,
        granted_by="alice@x",
    ))
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).delete(f"/grants/{gid}")
    assert resp.status_code == 204
    assert store.get(gid) is None


def test_delete_grant_superadmin_can_revoke_others():
    store = InMemoryGrantStore()
    gid = store.add(Grant(
        subject_sub="bob@x", action=Action.VIEW, resource=LOT,
        granted_by="alice@x",
    ))
    app = _build_app(store, _subject("root@x", ("superadmin",)))
    resp = TestClient(app).delete(f"/grants/{gid}")
    assert resp.status_code == 204


def test_delete_grant_non_author_forbidden():
    store = InMemoryGrantStore()
    gid = store.add(Grant(
        subject_sub="bob@x", action=Action.VIEW, resource=LOT,
        granted_by="alice@x",
    ))
    app = _build_app(store, _subject("mallory@x", ("assessor",)))
    resp = TestClient(app).delete(f"/grants/{gid}")
    assert resp.status_code == 403
    # грант остался
    assert store.get(gid) is not None


def test_delete_unknown_grant_404():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("root@x", ("superadmin",)))
    resp = TestClient(app).delete("/grants/nonexistent-id")
    assert resp.status_code == 404


def test_delete_non_revocable_grant_409():
    store = InMemoryGrantStore()
    gid = store.add(Grant(
        subject_sub="bob@x", action=Action.VIEW, resource=LOT,
        granted_by="alice@x", revocable=False,
    ))
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).delete(f"/grants/{gid}")
    assert resp.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
#  GET /grants/me
# ─────────────────────────────────────────────────────────────────────────────

def test_get_my_grants():
    store = InMemoryGrantStore()
    store.add(Grant(
        subject_sub="alice@x", action=Action.VIEW, resource=LOT,
        granted_by="root",
    ))
    store.add(Grant(
        subject_sub="alice@x", action=Action.EDIT, resource=OBJ,
        granted_by="root",
    ))
    store.add(Grant(
        subject_sub="other@x", action=Action.VIEW, resource=LOT,
        granted_by="root",
    ))
    app = _build_app(store, _subject("alice@x", ("assessor",)))
    resp = TestClient(app).get("/grants/me")
    assert resp.status_code == 200
    grants = resp.json()
    assert len(grants) == 2
    assert {g["action"] for g in grants} == {"view", "edit"}


def test_get_my_grants_empty():
    store = InMemoryGrantStore()
    app = _build_app(store, _subject("nobody@x", ("client",)))
    resp = TestClient(app).get("/grants/me")
    assert resp.status_code == 200
    assert resp.json() == []
