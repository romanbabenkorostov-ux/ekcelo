"""Lot ViewModel + object graph — sub-stage C2 service tests.

Покрывает `build_lot_viewmodel` и `build_object_graph` в
`backend/app/services/viewmodel.py`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.app.services.viewmodel import (
    LotNotFound,
    ObjectNotFound,
    build_lot_viewmodel,
    build_object_graph,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(
    path: Path,
    *,
    with_lots: bool = True,
    with_lot_items: bool = True,
    primary_cad_present: bool = True,
) -> None:
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
        """)
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area, floors) "
            "VALUES ('61:44:0050706:31', 'room', 'г. Ростов, Пушкина 1', 125.4, 5)"
        )
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area) "
            "VALUES ('61:44:0050706:99', 'land', 'г. Ростов, Лермонтова 2', 880.0)"
        )
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address) "
            "VALUES ('61:44:0050706:55', 'construction', 'г. Ростов, ангар')"
        )
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, name_short, entity_type) "
            "VALUES ('7707083893', 'ООО Тест Полное', 'ООО Тест', 'legal')"
        )
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, entity_type) "
            "VALUES ('500100123456', 'Иванов И. И.', 'person')"
        )
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn) "
            "VALUES ('61:44:0050706:31', 'собственность', '7707083893')"
        )
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn) "
            "VALUES ('61:44:0050706:31', 'аренда', '500100123456')"
        )
        conn.execute(
            "INSERT INTO extracts(extract_number, cad_number, extract_date) "
            "VALUES ('EX-1', '61:44:0050706:31', '2026-05-20')"
        )

        if with_lots:
            conn.executescript("""
            CREATE TABLE lots (
                lot_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                platform_targets TEXT, procedure_type TEXT, deal_type TEXT,
                primary_cad_number TEXT, notes_md TEXT, created_at TEXT
            );""")
            primary_for_001 = (
                "'61:44:0050706:31'"
                if primary_cad_present else "NULL"
            )
            conn.execute(
                f"INSERT INTO lots(lot_id, name, primary_cad_number) "
                f"VALUES ('lot-001', 'Объект Пушкина-1', {primary_for_001})"
            )
            conn.execute(
                "INSERT INTO lots(lot_id, name, primary_cad_number) "
                "VALUES ('lot-empty', 'Пустой лот', NULL)"
            )
            if with_lot_items:
                conn.executescript("""
                CREATE TABLE lot_items (
                    lot_id TEXT NOT NULL, cad_number TEXT NOT NULL,
                    role TEXT NOT NULL, ord INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (lot_id, cad_number)
                );""")
                # Порядок: ord=2, ord=1, ord=3 → сортировка по ord должна дать 1,2,3
                conn.execute("INSERT INTO lot_items VALUES "
                             "('lot-001', '61:44:0050706:55', 'structure', 2)")
                conn.execute("INSERT INTO lot_items VALUES "
                             "('lot-001', '61:44:0050706:31', 'room', 1)")
                conn.execute("INSERT INTO lot_items VALUES "
                             "('lot-001', '61:44:0050706:99', 'land', 3)")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p)
    return p


@pytest.fixture
def db_no_primary(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p, primary_cad_present=False)
    return p


@pytest.fixture
def db_no_lot_items(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p, with_lot_items=False)
    return p


@pytest.fixture
def db_no_lots(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p, with_lots=False)
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  build_lot_viewmodel
# ─────────────────────────────────────────────────────────────────────────────

def test_build_lot_viewmodel_basic(db: Path) -> None:
    vm = build_lot_viewmodel(db, "lot-001")
    assert vm.kind == "lot"
    assert vm.id == "lot-001"
    # 4 характеристики присутствуют
    assert vm.physical is not None
    assert vm.ownership is not None
    assert vm.geo is not None
    assert vm.temporal is not None


def test_build_lot_viewmodel_members_ordered_by_ord(db: Path) -> None:
    vm = build_lot_viewmodel(db, "lot-001")
    assert vm.members == [
        "61:44:0050706:31",   # ord=1
        "61:44:0050706:55",   # ord=2
        "61:44:0050706:99",   # ord=3
    ]


def test_build_lot_viewmodel_aggregates_from_primary_cad(db: Path) -> None:
    vm = build_lot_viewmodel(db, "lot-001")
    # primary_cad = 61:44:0050706:31 (room, area=125.4)
    assert vm.physical.object_type == "room"
    assert vm.physical.address == "г. Ростов, Пушкина 1"
    assert vm.physical.area_m2 == 125.4
    assert vm.temporal.extract_date == "2026-05-20"
    inns = {b.inn for b in vm.ownership.beneficiaries}
    assert inns == {"7707083893", "500100123456"}


def test_build_lot_viewmodel_no_primary_cad_empty_characteristics(db_no_primary: Path) -> None:
    vm = build_lot_viewmodel(db_no_primary, "lot-001")
    assert vm.physical.object_type is None
    assert vm.physical.area_m2 is None
    assert vm.ownership.rights == []
    assert vm.ownership.beneficiaries == []
    # members сохраняются — они независимы от primary
    assert len(vm.members) == 3


def test_build_lot_viewmodel_empty_lot_has_no_members_and_empty_chars(db: Path) -> None:
    vm = build_lot_viewmodel(db, "lot-empty")
    assert vm.members == []
    assert vm.physical.object_type is None
    assert vm.ownership.rights == []


def test_build_lot_viewmodel_as_of_propagates(db: Path) -> None:
    vm = build_lot_viewmodel(db, "lot-001", as_of="2025-01-01")
    assert vm.temporal.as_of_date == "2025-01-01"


def test_build_lot_viewmodel_not_found_raises(db: Path) -> None:
    with pytest.raises(LotNotFound):
        build_lot_viewmodel(db, "lot-does-not-exist")


def test_build_lot_viewmodel_without_lots_table_raises(db_no_lots: Path) -> None:
    with pytest.raises(LotNotFound):
        build_lot_viewmodel(db_no_lots, "lot-001")


def test_build_lot_viewmodel_without_lot_items_table_returns_empty_members(
    db_no_lot_items: Path,
) -> None:
    vm = build_lot_viewmodel(db_no_lot_items, "lot-001")
    assert vm.members == []


# ─────────────────────────────────────────────────────────────────────────────
#  build_object_graph
# ─────────────────────────────────────────────────────────────────────────────

def test_build_object_graph_includes_object_rights_beneficiaries(db: Path) -> None:
    g = build_object_graph(db, "61:44:0050706:31")
    kinds = {n["kind"] for n in g["nodes"]}
    # object kind для room → "room", + 2 right + 2 beneficiary
    assert "room" in kinds
    assert "right" in kinds
    assert "beneficiary_legal" in kinds
    assert "beneficiary_person" in kinds


def test_build_object_graph_node_ids_follow_contract(db: Path) -> None:
    g = build_object_graph(db, "61:44:0050706:31")
    ids = {n["id"] for n in g["nodes"]}
    # object id = cad как есть
    assert "61:44:0050706:31" in ids
    # right id = `right:{db_id}`
    assert any(i.startswith("right:") for i in ids)
    # beneficiary id = `inn:{inn}`
    assert "inn:7707083893" in ids
    assert "inn:500100123456" in ids


def test_build_object_graph_edges_connect_object_right_beneficiary(db: Path) -> None:
    g = build_object_graph(db, "61:44:0050706:31")
    has_right = [e for e in g["edges"] if e["kind"] == "has_right"]
    held_by = [e for e in g["edges"] if e["kind"] == "held_by"]
    assert len(has_right) == 2
    assert all(e["from"] == "61:44:0050706:31" for e in has_right)
    assert len(held_by) == 2
    # каждое held_by идёт от right-узла к inn-узлу
    for e in held_by:
        assert e["from"].startswith("right:")
        assert e["to"].startswith("inn:")


def test_build_object_graph_object_without_rights(db: Path) -> None:
    g = build_object_graph(db, "61:44:0050706:99")
    assert len(g["nodes"]) == 1
    assert g["nodes"][0]["id"] == "61:44:0050706:99"
    assert g["nodes"][0]["kind"] == "land"
    assert g["edges"] == []


def test_build_object_graph_construction_maps_to_structure_kind(db: Path) -> None:
    g = build_object_graph(db, "61:44:0050706:55")
    obj_node = next(n for n in g["nodes"] if n["id"] == "61:44:0050706:55")
    assert obj_node["kind"] == "structure"


def test_build_object_graph_object_not_found(db: Path) -> None:
    with pytest.raises(ObjectNotFound):
        build_object_graph(db, "00:00:0000000:00")


def test_build_object_graph_nodes_unique(db: Path) -> None:
    g = build_object_graph(db, "61:44:0050706:31")
    ids = [n["id"] for n in g["nodes"]]
    assert len(ids) == len(set(ids))
