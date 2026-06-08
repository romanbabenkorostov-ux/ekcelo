"""GET /catalog + GET /objects/{cad} — ViewModel REST endpoints (sub-stage C1).

Покрывает регистрацию маршрутов в `lot_orchestrator_web/main.py` и контракт
`contracts/api/openapi.yaml` (paths /catalog, /objects/{cad}).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lot_orchestrator.config import Settings
from lot_orchestrator_web.main import create_app
from lot_orchestrator_web.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT,
            purpose TEXT, floors INTEGER
        );
        CREATE TABLE entity_registry (
            inn TEXT PRIMARY KEY, name_full TEXT NOT NULL,
            name_short TEXT, ogrn TEXT, entity_type TEXT
        );
        CREATE TABLE rights (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
            right_type TEXT NOT NULL, right_holder_inn TEXT,
            share_numerator INTEGER, share_denominator INTEGER,
            registration_number TEXT, registration_date TEXT
        );
        CREATE TABLE extracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extract_number TEXT, cad_number TEXT NOT NULL,
            extract_date TEXT NOT NULL
        );
        CREATE TABLE lots (
            lot_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            platform_targets TEXT, procedure_type TEXT, deal_type TEXT,
            primary_cad_number TEXT, notes_md TEXT, created_at TEXT
        );
        """)
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area, floors) "
            "VALUES ('61:44:0050706:31', 'room', 'г. Ростов, ул. Пушкина 1', 125.4, 5)"
        )
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, entity_type) "
            "VALUES ('7707083893', 'ООО Тест', 'legal')"
        )
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn) "
            "VALUES ('61:44:0050706:31', 'собственность', '7707083893')"
        )
        conn.execute(
            "INSERT INTO extracts(extract_number, cad_number, extract_date) "
            "VALUES ('EX-1', '61:44:0050706:31', '2026-05-20')"
        )
        conn.execute(
            "INSERT INTO lots(lot_id, name, primary_cad_number, deal_type) "
            "VALUES ('lot-001', 'Помещение Пушкина-1', '61:44:0050706:31', 'sale')"
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _seed_db(p)
    return p


@pytest.fixture
def client(db_path: Path) -> TestClient:
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    return TestClient(create_app(
        settings=settings, mock_llm_text="x", ekcelo_db=db_path,
    ))


@pytest.fixture
def client_no_db() -> TestClient:
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    return TestClient(create_app(settings=settings, mock_llm_text="x"))


# ─────────────────────────────────────────────────────────────────────────────
#  /catalog
# ─────────────────────────────────────────────────────────────────────────────

def test_catalog_returns_200_with_cards(client: TestClient) -> None:
    resp = client.get("/catalog")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    kinds = {item["kind"] for item in payload}
    assert kinds == {"object", "lot"}


def test_catalog_kind_filter_object(client: TestClient) -> None:
    resp = client.get("/catalog?kind=object")
    assert resp.status_code == 200
    payload = resp.json()
    assert all(item["kind"] == "object" for item in payload)
    assert payload[0]["id"] == "61:44:0050706:31"


def test_catalog_q_filter(client: TestClient) -> None:
    resp = client.get("/catalog?q=Пушкина")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert ids == {"61:44:0050706:31", "lot-001"}


def test_catalog_invalid_kind_returns_422(client: TestClient) -> None:
    resp = client.get("/catalog?kind=ploho")
    assert resp.status_code == 422


def test_catalog_returns_503_when_db_not_configured(client_no_db: TestClient) -> None:
    resp = client_no_db.get("/catalog")
    assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
#  /objects/{cad}
# ─────────────────────────────────────────────────────────────────────────────

def test_object_returns_viewmodel_with_4_characteristics(client: TestClient) -> None:
    resp = client.get("/objects/61:44:0050706:31")
    assert resp.status_code == 200
    vm = resp.json()
    for key in ("kind", "id", "physical", "ownership", "geo", "temporal"):
        assert key in vm
    assert vm["kind"] == "object"
    assert vm["id"] == "61:44:0050706:31"
    assert vm["physical"]["area_m2"] == 125.4
    assert vm["temporal"]["extract_date"] == "2026-05-20"


def test_object_ownership_rights_resolved(client: TestClient) -> None:
    resp = client.get("/objects/61:44:0050706:31")
    vm = resp.json()
    assert len(vm["ownership"]["rights"]) == 1
    assert vm["ownership"]["rights"][0]["right_holder_inn"] == "7707083893"
    assert vm["ownership"]["beneficiaries"][0]["name_full"] == "ООО Тест"


def test_object_not_found_returns_404(client: TestClient) -> None:
    resp = client.get("/objects/99:99:9999999:99")
    assert resp.status_code == 404
    assert "не найден" in resp.json()["detail"]


def test_object_as_of_parameter_round_trips(client: TestClient) -> None:
    resp = client.get("/objects/61:44:0050706:31?as_of=2026-05-01")
    assert resp.status_code == 200
    assert resp.json()["temporal"]["as_of_date"] == "2026-05-01"


def test_object_returns_503_when_db_not_configured(client_no_db: TestClient) -> None:
    resp = client_no_db.get("/objects/61:44:0050706:31")
    assert resp.status_code == 503
