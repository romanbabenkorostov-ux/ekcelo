"""Cycle 15 M2 — SQLiteGrantStore + контракт-эквивалентность с InMemory."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lot_orchestrator_web.rbac import (
    Action,
    Grant,
    InMemoryGrantStore,
    Principal,
    Resource,
    ResourceType,
    Role,
    can,
    delegate,
    share,
)
from lot_orchestrator_web.rbac_store import SQLiteGrantStore


LOT1 = Resource(ResourceType.LOT, "lot-001")
LOT2 = Resource(ResourceType.LOT, "lot-002")
OBJ1 = Resource(ResourceType.OBJECT, "61:44:0050706:31")
BUN1 = Resource(ResourceType.BUNDLE, "bundle-abc")


# ─────────────────────────────────────────────────────────────────────────────
#  Parametrized fixtures — оба store ведут себя одинаково (контракт)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path: Path):
    """Контракт-эквивалентность: тест должен пройти на любой реализации."""
    if request.param == "memory":
        return InMemoryGrantStore()
    return SQLiteGrantStore(tmp_path / "access.sqlite")


@pytest.fixture
def admin() -> Principal:
    return Principal(sub="root@x", roles=frozenset({Role.SUPERADMIN}))


@pytest.fixture
def assessor_a() -> Principal:
    return Principal(sub="alice@x", roles=frozenset({Role.ASSESSOR}))


@pytest.fixture
def assessor_b() -> Principal:
    return Principal(sub="bob@x", roles=frozenset({Role.ASSESSOR}))


@pytest.fixture
def client_c() -> Principal:
    return Principal(sub="charlie@x", roles=frozenset({Role.CLIENT}))


# ─────────────────────────────────────────────────────────────────────────────
#  Контракт: GrantStore protocol — те же 8 тестов, два бэкенда
# ─────────────────────────────────────────────────────────────────────────────

def test_add_grant_returns_id(store, assessor_a):
    gid = store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    assert gid


def test_find_returns_matching_grant(store, assessor_a):
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT1,
        granted_by="root",
    ))
    found = store.find(assessor_a.sub, Action.EDIT, LOT1)
    assert found is not None
    assert found.subject_sub == assessor_a.sub
    assert found.action == Action.EDIT


def test_find_returns_none_for_missing(store, assessor_a):
    assert store.find(assessor_a.sub, Action.VIEW, LOT1) is None


def test_revoke_removes_grant(store, assessor_a):
    gid = store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    assert store.revoke(gid) is True
    assert store.find(assessor_a.sub, Action.VIEW, LOT1) is None


def test_revoke_returns_false_for_unknown(store):
    assert store.revoke("nonexistent") is False


def test_revoke_non_revocable_returns_false(store, assessor_a):
    gid = store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root", revocable=False,
    ))
    assert store.revoke(gid) is False
    # запись осталась
    assert store.find(assessor_a.sub, Action.VIEW, LOT1) is not None


def test_list_for_subject(store, assessor_a):
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


def test_expires_at_roundtrip(store, assessor_a):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    gid = store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root", expires_at=future,
    ))
    found = store.find(assessor_a.sub, Action.VIEW, LOT1)
    assert found is not None
    assert found.expires_at is not None
    # сравниваем с tolerance, ISO round-trip не теряет минуты
    assert abs((found.expires_at - future).total_seconds()) < 1


# ─────────────────────────────────────────────────────────────────────────────
#  Интеграция с can/delegate/share — тоже работает на обоих
# ─────────────────────────────────────────────────────────────────────────────

def test_can_with_persistent_grant(store, assessor_a):
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    assert can(assessor_a, Action.VIEW, LOT1, store) is True


def test_delegate_persists_in_store(store, assessor_a, assessor_b):
    store.add(Grant(
        subject_sub=assessor_a.sub, action=Action.EDIT, resource=LOT1,
        granted_by="root",
    ))
    delegate(
        grantor=assessor_a, grantee_sub=assessor_b.sub,
        action=Action.EDIT, resource=LOT1, store=store,
    )
    assert can(assessor_b, Action.EDIT, LOT1, store) is True


def test_share_persists_in_store(store, client_c):
    store.add(Grant(
        subject_sub=client_c.sub, action=Action.VIEW, resource=BUN1,
        granted_by="root",
    ))
    share(
        sharer=client_c, recipient_sub="guest@x",
        resource=BUN1, store=store,
    )
    third = Principal(sub="guest@x", roles=frozenset({Role.CLIENT}))
    assert can(third, Action.VIEW, BUN1, store) is True


# ─────────────────────────────────────────────────────────────────────────────
#  Специфичные для SQLite — persistence через перезапуск
# ─────────────────────────────────────────────────────────────────────────────

def test_sqlite_persistence_survives_reopen(tmp_path: Path, assessor_a):
    db = tmp_path / "access.sqlite"
    store1 = SQLiteGrantStore(db)
    gid = store1.add(Grant(
        subject_sub=assessor_a.sub, action=Action.VIEW, resource=LOT1,
        granted_by="root",
    ))
    # новый процесс — новый коннект
    store2 = SQLiteGrantStore(db)
    found = store2.find(assessor_a.sub, Action.VIEW, LOT1)
    assert found is not None
    assert found.grant_id == gid


def test_sqlite_creates_parent_dirs(tmp_path: Path):
    nested = tmp_path / "deep" / "nested" / "access.sqlite"
    assert not nested.parent.exists()
    SQLiteGrantStore(nested)
    assert nested.parent.is_dir()
    assert nested.exists()


def test_sqlite_schema_has_indices(tmp_path: Path):
    """Sanity: индексы созданы — хочется ловить деградацию миграции."""
    db = tmp_path / "access.sqlite"
    SQLiteGrantStore(db)
    conn = sqlite3.connect(db)
    try:
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='access_grants'"
        )}
    finally:
        conn.close()
    assert "idx_access_grants_lookup" in idx
    assert "idx_access_grants_subject" in idx
