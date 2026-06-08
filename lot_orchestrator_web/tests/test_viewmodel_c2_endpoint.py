"""GET /lots/{lot_id} + GET /objects/{cad}/graph — ViewModel C2 endpoints."""
from __future__ import annotations

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
        CREATE TABLE lot_items (
            lot_id TEXT NOT NULL, cad_number TEXT NOT NULL,
            role TEXT NOT NULL, ord INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (lot_id, cad_number)
        );
        """)
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area) "
            "VALUES ('61:44:0050706:31', 'room', 'г. Ростов, Пушкина 1', 125.4)"
        )
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address) "
            "VALUES ('61:44:0050706:99', 'land', 'г. Ростов, Лермонтова 2')"
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
            "INSERT INTO lots(lot_id, name, primary_cad_number) "
            "VALUES ('lot-001', 'Помещение Пушкина', '61:44:0050706:31')"
        )
        conn.execute("INSERT INTO lot_items VALUES "
                     "('lot-001', '61:44:0050706:31', 'room', 1)")
        conn.execute("INSERT INTO lot_items VALUES "
                     "('lot-001', '61:44:0050706:99', 'land', 2)")
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
#  /lots/{lot_id}
# ─────────────────────────────────────────────────────────────────────────────

def test_lot_endpoint_returns_viewmodel(client: TestClient) -> None:
    resp = client.get("/lots/lot-001")
    assert resp.status_code == 200
    vm = resp.json()
    assert vm["kind"] == "lot"
    assert vm["id"] == "lot-001"
    assert vm["members"] == ["61:44:0050706:31", "61:44:0050706:99"]
    # primary cad → агрегация physical
    assert vm["physical"]["object_type"] == "room"


def test_lot_endpoint_as_of_propagates(client: TestClient) -> None:
    resp = client.get("/lots/lot-001?as_of=2026-01-01")
    assert resp.status_code == 200
    assert resp.json()["temporal"]["as_of_date"] == "2026-01-01"


def test_lot_endpoint_404(client: TestClient) -> None:
    resp = client.get("/lots/lot-does-not-exist")
    assert resp.status_code == 404
    assert "не найден" in resp.json()["detail"]


def test_lot_endpoint_503_without_db(client_no_db: TestClient) -> None:
    resp = client_no_db.get("/lots/lot-001")
    assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
#  /objects/{cad}/graph
# ─────────────────────────────────────────────────────────────────────────────

def test_graph_endpoint_returns_nodes_and_edges(client: TestClient) -> None:
    resp = client.get("/objects/61:44:0050706:31/graph")
    assert resp.status_code == 200
    g = resp.json()
    assert "nodes" in g and "edges" in g
    assert len(g["nodes"]) >= 1
    # должен быть object-узел с id=cad
    obj_ids = [n["id"] for n in g["nodes"]]
    assert "61:44:0050706:31" in obj_ids


def test_graph_endpoint_has_right_edge(client: TestClient) -> None:
    resp = client.get("/objects/61:44:0050706:31/graph")
    g = resp.json()
    edge_kinds = {e["kind"] for e in g["edges"]}
    assert "has_right" in edge_kinds
    assert "held_by" in edge_kinds


def test_graph_endpoint_404(client: TestClient) -> None:
    resp = client.get("/objects/99:99:9999999:99/graph")
    assert resp.status_code == 404


def test_graph_endpoint_503_without_db(client_no_db: TestClient) -> None:
    resp = client_no_db.get("/objects/61:44:0050706:31/graph")
    assert resp.status_code == 503
