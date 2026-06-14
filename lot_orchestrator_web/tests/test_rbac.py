"""RBAC ядро (cycle 15, M1) — Principal/Grant/can()/delegate/share по C6."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lot_orchestrator_web.oauth import Subject as OAuthSubject
from lot_orchestrator_web.rbac import (
    Action,
    AuthorizationError,
    Grant,
    InMemoryGrantStore,
    Principal,
    Resource,
    ResourceType,
    Role,
    can,
    delegate,
    require,
    share,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

LOT1 = Resource(ResourceType.LOT, "lot-001")
LOT2 = Resource(ResourceType.LOT, "lot-002")
OBJ1 = Resource(ResourceType.OBJECT, "61:44:0050706:31")
BUN1 = Resource(ResourceType.BUNDLE, "bundle-abc")


@pytest.fixture
def store() -> InMemoryGrantStore:
    return InMemoryGrantStore()


@pytest.fixture
def admin() -> Principal:
    return Principal(sub="root@example", roles=frozenset({Role.SUPERADMIN}))


@pytest.fixture
def assessor_a() -> Principal:
    return Principal(sub="assessor-a@example", roles=frozenset({Role.ASSESSOR}))


@pytest.fixture
def assessor_b() -> Principal:
    return Principal(sub="assessor-b@example", roles=frozenset({Role.ASSESSOR}))


@pytest.fixture
def client_c() -> Principal:
    return Principal(sub="client-c@example", roles=frozenset({Role.CLIENT}))


# ─────────────────────────────────────────────────────────────────────────────
#  Principal.from_oauth_subject
# ─────────────────────────────────────────────────────────────────────────────

def test_principal_from_oauth_subject_extracts_known_roles():
    s = OAuthSubject(sub="x@y", roles=("assessor", "superadmin", "custom-noise"),
                     claims={})
    p = Principal.from_oauth_subject(s)
    assert p.sub == "x@y"
    assert p.roles == frozenset({Role.ASSESSOR, Role.SUPERADMIN})


def test_principal_from_oauth_subject_empty_roles():
    s = OAuthSubject(sub="x", roles=(), claims={})
    p = Principal.from_oauth_subject(s)
    assert p.roles == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
#  superadmin bypass
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("resource", [LOT1, OBJ1, BUN1])
def test_superadmin_can_anything(admin, store, action, resource):
    assert can(admin, action, resource, store) is True


# ─────────────────────────────────────────────────────────────────────────────
#  Client: hard-deny на input/edit/delegate (C6 read-only)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("action", [Action.INPUT, Action.EDIT, Action.DELEGATE])
def test_client_hard_denied_for_write_actions(client_c, store, action):
    # Даже если по ошибке выдан грант — client не может INPUT/EDIT
    store.add(Grant(
        subject_sub=client_c.sub, action=action, resource=LOT1,
        granted_by="root@example",
    ))
    assert can(client_c, action, LOT1, store) is False


def test_client_can_view_with_grant(client_c, store):
    store.add(Grant(
        subject_sub=client_c.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root@example",
    ))
    assert can(client_c, Action.VIEW, LOT1, store) is True


def test_client_cannot_view_without_grant(client_c, store):
    assert can(client_c, Action.VIEW, LOT1, store) is False


# ─────────────────────────────────────────────────────────────────────────────
#  Assessor: гранты scoped
# ─────────────────────────────────────────────────────────────────────────────

def test_assessor_cannot_view_without_grant(assessor_a, store):
    assert can(assessor_a, Action.VIEW, LOT1, store) is False


def test_assessor_view_after_grant(assessor_a, store):
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root@example",
    ))
    assert can(assessor_a, Action.VIEW, LOT1, store) is True
    # другой лот — нет гранта
    assert can(assessor_a, Action.VIEW, LOT2, store) is False


def test_assessor_edit_requires_explicit_grant(assessor_a, store):
    # view-грант НЕ даёт edit (action-grain)
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root@example",
    ))
    assert can(assessor_a, Action.EDIT, LOT1, store) is False
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT1,
        granted_by="root@example",
    ))
    assert can(assessor_a, Action.EDIT, LOT1, store) is True


# ─────────────────────────────────────────────────────────────────────────────
#  Delegation: assessor → assessor
# ─────────────────────────────────────────────────────────────────────────────

def test_delegate_grants_scoped_access(assessor_a, assessor_b, store):
    # A имеет edit-грант на LOT1
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT1,
        granted_by="root",
    ))
    # A делегирует EDIT на LOT1 → B
    grant_id = delegate(
        grantor=assessor_a, grantee_sub=assessor_b.sub,
        action=Action.EDIT, resource=LOT1, store=store,
    )
    assert grant_id
    assert can(assessor_b, Action.EDIT, LOT1, store) is True
    # B не получил доступ к LOT2 (scoping)
    assert can(assessor_b, Action.EDIT, LOT2, store) is False


def test_delegate_fails_if_grantor_cannot(assessor_a, assessor_b, store):
    # A без гранта пытается делегировать
    with pytest.raises(AuthorizationError, match="не может делегировать"):
        delegate(
            grantor=assessor_a, grantee_sub=assessor_b.sub,
            action=Action.EDIT, resource=LOT1, store=store,
        )


def test_delegate_rejects_non_assessor(client_c, assessor_b, store):
    store.add(Grant(
        subject_sub=client_c.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    with pytest.raises(AuthorizationError, match="assessor/superadmin"):
        delegate(
            grantor=client_c, grantee_sub=assessor_b.sub,
            action=Action.VIEW, resource=LOT1, store=store,
        )


def test_superadmin_can_delegate_anything(admin, assessor_b, store):
    grant_id = delegate(
        grantor=admin, grantee_sub=assessor_b.sub,
        action=Action.EDIT, resource=LOT1, store=store,
    )
    assert grant_id
    assert can(assessor_b, Action.EDIT, LOT1, store) is True


# ─────────────────────────────────────────────────────────────────────────────
#  Revoke
# ─────────────────────────────────────────────────────────────────────────────

def test_revoke_removes_access(assessor_a, store):
    gid = store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT1,
        granted_by="root",
    ))
    assert can(assessor_a, Action.EDIT, LOT1, store) is True
    assert store.revoke(gid) is True
    assert can(assessor_a, Action.EDIT, LOT1, store) is False


def test_revoke_unknown_grant_returns_false(store):
    assert store.revoke("nonexistent-id") is False


def test_revoke_non_revocable_grant_fails(assessor_a, store):
    gid = store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT1,
        granted_by="root", revocable=False,
    ))
    assert store.revoke(gid) is False
    # доступ остался
    assert can(assessor_a, Action.EDIT, LOT1, store) is True


# ─────────────────────────────────────────────────────────────────────────────
#  Share: client → третье лицо (view-only token)
# ─────────────────────────────────────────────────────────────────────────────

def test_share_creates_view_only_grant(client_c, store):
    # client сам видит BUN1
    store.add(Grant(
        subject_sub=client_c.sub, action=Action.VIEW, resource=BUN1,
        granted_by="root",
    ))
    # шерит третьему лицу
    grant_id = share(
        sharer=client_c, recipient_sub="guest@external",
        resource=BUN1, store=store,
    )
    assert grant_id
    third_party = Principal(sub="guest@external", roles=frozenset({Role.CLIENT}))
    assert can(third_party, Action.VIEW, BUN1, store) is True
    # шеринг не даёт edit/export автоматически
    assert can(third_party, Action.EDIT, BUN1, store) is False
    assert can(third_party, Action.EXPORT, BUN1, store) is False


def test_share_fails_if_sharer_cannot_view(client_c, store):
    with pytest.raises(AuthorizationError, match="не видит"):
        share(
            sharer=client_c, recipient_sub="guest@x",
            resource=BUN1, store=store,
        )


def test_share_rejects_assessor(assessor_a, store):
    """assessor использует delegate, не share."""
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=BUN1,
        granted_by="root",
    ))
    with pytest.raises(AuthorizationError, match="client/superadmin"):
        share(
            sharer=assessor_a, recipient_sub="guest",
            resource=BUN1, store=store,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Expiry (TTL)
# ─────────────────────────────────────────────────────────────────────────────

def test_expired_grant_denies(assessor_a, store):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root", expires_at=past,
    ))
    assert can(assessor_a, Action.VIEW, LOT1, store) is False


def test_future_expiry_allows(assessor_a, store):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root", expires_at=future,
    ))
    assert can(assessor_a, Action.VIEW, LOT1, store) is True


def test_naive_datetime_treated_as_utc(assessor_a, store):
    past_naive = datetime.utcnow() - timedelta(hours=1)  # без tz
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root", expires_at=past_naive,
    ))
    assert can(assessor_a, Action.VIEW, LOT1, store) is False


# ─────────────────────────────────────────────────────────────────────────────
#  require() — императивная версия
# ─────────────────────────────────────────────────────────────────────────────

def test_require_raises_on_denial(assessor_a, store):
    with pytest.raises(AuthorizationError):
        require(assessor_a, Action.EDIT, LOT1, store)


def test_require_passes_for_superadmin(admin, store):
    require(admin, Action.INPUT, LOT1, store)  # не должно бросать


# ─────────────────────────────────────────────────────────────────────────────
#  list_for_subject
# ─────────────────────────────────────────────────────────────────────────────

def test_list_for_subject_returns_all_grants(assessor_a, store):
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT2,
        granted_by="root",
    ))
    store.add(Grant(
        subject_sub="other@x", action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    grants = store.list_for_subject(assessor_a.sub)
    assert len(grants) == 2
    assert {g.action for g in grants} == {Action.VIEW, Action.EDIT}
