"""Cycle 15 M5 — пост-фильтр `/catalog` по VIEW-грантам.

Проверяет:
- enforce_rbac=False → no-op (все карточки видны без auth).
- enforce_rbac=True + grant_store:
    * superadmin видит всё (минует фильтр в `can`);
    * assessor с view-грантом на конкретный объект — видит только его;
    * assessor без грантов → [];
    * client с view-грантом — видит только разрешённое (read-only роль OK для VIEW);
    * q/kind работают совместно с фильтром (фильтр применяется ПОСЛЕ build_catalog,
      результат — пересечение).
- Лоты тоже фильтруются (kind="lot" → ResourceType.LOT).
"""
from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.rbac import Action, Grant, Resource, ResourceType
from lot_orchestrator_web.rbac_store import SQLiteGrantStore
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _seed_ekcelo(path: Path) -> None:
    """3 объекта + 2 лота (для проверки kind-фильтрации)."""
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
        CREATE TABLE lots (lot_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                           primary_cad_number TEXT);
        """)
        conn.executemany(
            "INSERT INTO objects(cad_number, object_type, address) VALUES (?, ?, ?)",
            [
                ("61:44:0050706:31", "room", "Ростов"),
                ("61:44:0050706:32", "room", "Краснодар"),
                ("61:44:0050706:33", "room", "Сочи"),
            ],
        )
        conn.executemany(
            "INSERT INTO lots(lot_id, name, primary_cad_number) VALUES (?, ?, ?)",
            [("lot-A", "Лот А", "61:44:0050706:31"),
             ("lot-B", "Лот Б", "61:44:0050706:32")],
        )
        conn.commit()
    finally:
        conn.close()


def _basic(user: str, pw: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _app(tmp_path: Path, *, enforce: bool, grants: list[Grant] | None = None):
    ekcelo = tmp_path / "ekcelo.sqlite"
    _seed_ekcelo(ekcelo)
    access = tmp_path / "access.sqlite"
    store = SQLiteGrantStore(access)
    for g in (grants or []):
        store.add(g)
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    app = create_app(
        settings=settings,
        mock_llm_text="x",
        ekcelo_db=ekcelo,
        access_db=access if enforce else None,
        auth_users="alice:secret,root:secret,charlie:secret" if enforce else None,
        auth_roles="alice:assessor,root:superadmin,charlie:client" if enforce else None,
        enforce_rbac=enforce,
    )
    return TestClient(app)


def _ids(resp) -> set[str]:
    return {c["id"] for c in resp.json()}


# ─────────────────────────────────────────────────────────────────────────────
#  enforce_rbac=False → no-op (backward-compat)
# ─────────────────────────────────────────────────────────────────────────────

def test_catalog_unfiltered_when_enforce_off(tmp_path: Path):
    client = _app(tmp_path, enforce=False)
    resp = client.get("/catalog")
    assert resp.status_code == 200
    assert _ids(resp) >= {"61:44:0050706:31", "61:44:0050706:32", "61:44:0050706:33",
                          "lot-A", "lot-B"}


# ─────────────────────────────────────────────────────────────────────────────
#  enforce_rbac=True
# ─────────────────────────────────────────────────────────────────────────────

def test_catalog_superadmin_sees_all(tmp_path: Path):
    client = _app(tmp_path, enforce=True)  # без грантов — superadmin минует
    resp = client.get("/catalog", headers=_basic("root", "secret"))
    assert resp.status_code == 200
    assert _ids(resp) == {
        "61:44:0050706:31", "61:44:0050706:32", "61:44:0050706:33",
        "lot-A", "lot-B",
    }


def test_catalog_assessor_no_grants_sees_empty(tmp_path: Path):
    client = _app(tmp_path, enforce=True)
    resp = client.get("/catalog", headers=_basic("alice", "secret"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_catalog_assessor_with_view_grant_sees_only_granted(tmp_path: Path):
    grants = [
        Grant(
            grant_id="g1",
            subject_sub="alice",
            action=Action.VIEW,
            resource=Resource(ResourceType.OBJECT, "61:44:0050706:32"),
            granted_by="root",
        ),
    ]
    client = _app(tmp_path, enforce=True, grants=grants)
    resp = client.get("/catalog", headers=_basic("alice", "secret"))
    assert resp.status_code == 200
    assert _ids(resp) == {"61:44:0050706:32"}


def test_catalog_client_can_view_granted(tmp_path: Path):
    """client read-only, но VIEW не запрещён (только input/edit/delegate)."""
    grants = [
        Grant(
            grant_id="g-cli",
            subject_sub="charlie",
            action=Action.VIEW,
            resource=Resource(ResourceType.LOT, "lot-A"),
            granted_by="root",
        ),
    ]
    client = _app(tmp_path, enforce=True, grants=grants)
    resp = client.get("/catalog", headers=_basic("charlie", "secret"))
    assert resp.status_code == 200
    assert _ids(resp) == {"lot-A"}


def test_catalog_filter_intersects_with_q(tmp_path: Path):
    """q+фильтр: q сужает по тексту, грант-фильтр — по разрешению. Пересечение."""
    grants = [
        Grant(
            grant_id="g-a",
            subject_sub="alice",
            action=Action.VIEW,
            resource=Resource(ResourceType.OBJECT, "61:44:0050706:31"),
            granted_by="root",
        ),
        Grant(
            grant_id="g-b",
            subject_sub="alice",
            action=Action.VIEW,
            resource=Resource(ResourceType.OBJECT, "61:44:0050706:33"),
            granted_by="root",
        ),
    ]
    client = _app(tmp_path, enforce=True, grants=grants)
    # q="Сочи" совпадёт только с :33; на :33 есть грант → 1 карточка
    resp = client.get("/catalog?q=Сочи", headers=_basic("alice", "secret"))
    assert resp.status_code == 200
    assert _ids(resp) == {"61:44:0050706:33"}


def test_catalog_filter_with_kind_lot(tmp_path: Path):
    """kind=lot ограничивает построение → фильтр применяется только к лотам."""
    grants = [
        Grant(
            grant_id="g-obj",
            subject_sub="alice",
            action=Action.VIEW,
            resource=Resource(ResourceType.OBJECT, "61:44:0050706:31"),
            granted_by="root",
        ),
        Grant(
            grant_id="g-lot",
            subject_sub="alice",
            action=Action.VIEW,
            resource=Resource(ResourceType.LOT, "lot-B"),
            granted_by="root",
        ),
    ]
    client = _app(tmp_path, enforce=True, grants=grants)
    resp = client.get("/catalog?kind=lot", headers=_basic("alice", "secret"))
    assert resp.status_code == 200
    assert _ids(resp) == {"lot-B"}


def test_catalog_filter_export_action_does_not_grant_view(tmp_path: Path):
    """Грант на EXPORT не даёт VIEW (action-specific). Карточек 0."""
    grants = [
        Grant(
            grant_id="g-x",
            subject_sub="alice",
            action=Action.EXPORT,
            resource=Resource(ResourceType.OBJECT, "61:44:0050706:31"),
            granted_by="root",
        ),
    ]
    client = _app(tmp_path, enforce=True, grants=grants)
    resp = client.get("/catalog", headers=_basic("alice", "secret"))
    assert resp.status_code == 200
    assert resp.json() == []
