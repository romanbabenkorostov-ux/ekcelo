"""ViewModel (C4) — catalog + object-ViewModel builders.

Покрывает `backend/app/services/viewmodel.py` (sub-stage C1).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.services.viewmodel import (
    CatalogCard,
    ObjectNotFound,
    ViewModel,
    build_catalog,
    build_object_viewmodel,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures — синтетическая БД (slice §1..§6 от egrn_current_schema.sql)
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(path: Path, *, with_lots: bool = True, with_etp: bool = True) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            address TEXT,
            area REAL,
            category TEXT,
            permitted_use TEXT,
            purpose TEXT,
            floors INTEGER
        );
        CREATE TABLE entity_registry (
            inn TEXT PRIMARY KEY,
            name_full TEXT NOT NULL,
            name_short TEXT,
            ogrn TEXT,
            entity_type TEXT
        );
        CREATE TABLE rights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cad_number TEXT NOT NULL,
            right_type TEXT NOT NULL,
            right_holder_inn TEXT,
            share_numerator INTEGER,
            share_denominator INTEGER,
            registration_number TEXT,
            registration_date TEXT
        );
        CREATE TABLE extracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extract_number TEXT,
            cad_number TEXT NOT NULL,
            extract_date TEXT NOT NULL
        );
        """)
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area, floors) "
            "VALUES ('61:44:0050706:31', 'room', 'г. Ростов, ул. Пушкина 1', 125.4, 5)"
        )
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area) "
            "VALUES ('61:44:0050706:99', 'land', 'г. Ростов, ул. Лермонтова 2', 880.0)"
        )
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, name_short, entity_type) "
            "VALUES ('7707083893', 'ООО Тест Полное', 'ООО Тест', 'legal')"
        )
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, entity_type) "
            "VALUES ('500100123456', 'Иванов Иван Иванович', 'person')"
        )
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn, "
            "share_numerator, share_denominator, registration_number, registration_date) "
            "VALUES ('61:44:0050706:31', 'собственность', '7707083893', "
            "1, 2, 'RR-001', '2024-05-10')"
        )
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn, "
            "share_numerator, share_denominator, registration_date) "
            "VALUES ('61:44:0050706:31', 'собственность', '500100123456', "
            "1, 2, '2026-01-15')"
        )
        conn.execute(
            "INSERT INTO extracts(extract_number, cad_number, extract_date) "
            "VALUES ('EX-1', '61:44:0050706:31', '2024-06-01')"
        )
        conn.execute(
            "INSERT INTO extracts(extract_number, cad_number, extract_date) "
            "VALUES ('EX-2', '61:44:0050706:31', '2026-05-20')"
        )

        if with_etp:
            conn.execute("""
            CREATE TABLE object_etp_profile (
                cad_number TEXT PRIMARY KEY,
                location_extra TEXT, building_extra TEXT, layout TEXT,
                legal_extra TEXT, risks TEXT, extras TEXT,
                source TEXT NOT NULL, confidence REAL NOT NULL,
                updated_at TEXT
            );""")
            conn.execute(
                "INSERT INTO object_etp_profile(cad_number, layout, risks, "
                "source, confidence) VALUES (?, ?, ?, ?, ?)",
                (
                    "61:44:0050706:31",
                    json.dumps({"ceiling_height_m": 3.1, "finish_state": "good"}),
                    json.dumps({"legal_risks": ["спор о праве"]}),
                    "osv",
                    0.85,
                ),
            )

        if with_lots:
            conn.execute("""
            CREATE TABLE lots (
                lot_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                platform_targets TEXT,
                procedure_type TEXT,
                deal_type TEXT,
                primary_cad_number TEXT,
                notes_md TEXT,
                created_at TEXT
            );""")
            conn.execute(
                "INSERT INTO lots(lot_id, name, primary_cad_number, deal_type) "
                "VALUES ('lot-001', 'Помещение Пушкина-1', '61:44:0050706:31', 'sale')"
            )
            conn.execute(
                "INSERT INTO lots(lot_id, name, primary_cad_number, deal_type) "
                "VALUES ('lot-002', 'Участок Лермонтова', '61:44:0050706:99', 'sale')"
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p)
    return p


@pytest.fixture
def db_no_etp(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p, with_etp=False)
    return p


@pytest.fixture
def db_no_lots(tmp_path: Path) -> Path:
    p = tmp_path / "ekcelo.sqlite"
    _make_db(p, with_lots=False)
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  build_catalog
# ─────────────────────────────────────────────────────────────────────────────

def test_build_catalog_returns_objects_and_lots(db: Path) -> None:
    cards = build_catalog(db)
    kinds = [c.kind for c in cards]
    assert kinds.count("object") == 2
    assert kinds.count("lot") == 2


def test_build_catalog_object_has_latest_extract_date(db: Path) -> None:
    cards = build_catalog(db, kind="object")
    by_id = {c.id: c for c in cards}
    assert by_id["61:44:0050706:31"].extract_date == "2026-05-20"
    # объект без выписок → extract_date None
    assert by_id["61:44:0050706:99"].extract_date is None


def test_build_catalog_kind_filter_object(db: Path) -> None:
    cards = build_catalog(db, kind="object")
    assert all(c.kind == "object" for c in cards)
    assert {c.id for c in cards} == {"61:44:0050706:31", "61:44:0050706:99"}


def test_build_catalog_kind_filter_lot(db: Path) -> None:
    cards = build_catalog(db, kind="lot")
    assert all(c.kind == "lot" for c in cards)
    ids = {c.id for c in cards}
    assert ids == {"lot-001", "lot-002"}
    # title для lot = lots.name; address подтянут из primary_cad
    lot1 = next(c for c in cards if c.id == "lot-001")
    assert lot1.title == "Помещение Пушкина-1"
    assert lot1.address == "г. Ростов, ул. Пушкина 1"


def test_build_catalog_q_filter_address_case_insensitive(db: Path) -> None:
    cards = build_catalog(db, q="ПУШКИНА")
    ids = {c.id for c in cards}
    # объект Пушкина + лот Пушкина
    assert ids == {"61:44:0050706:31", "lot-001"}


def test_build_catalog_q_filter_no_match_returns_empty(db: Path) -> None:
    assert build_catalog(db, q="несуществующее") == []


def test_build_catalog_handles_missing_lots_table(db_no_lots: Path) -> None:
    cards = build_catalog(db_no_lots)
    assert all(c.kind == "object" for c in cards)
    assert len(cards) == 2


# ─────────────────────────────────────────────────────────────────────────────
#  build_object_viewmodel
# ─────────────────────────────────────────────────────────────────────────────

def test_build_object_viewmodel_basic_fields(db: Path) -> None:
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    assert vm.kind == "object"
    assert vm.id == "61:44:0050706:31"
    assert vm.physical.object_type == "room"
    assert vm.physical.address == "г. Ростов, ул. Пушкина 1"
    assert vm.physical.area_m2 == 125.4
    assert vm.physical.floors == 5


def test_build_object_viewmodel_etp_block_parsed(db: Path) -> None:
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    assert vm.physical.etp is not None
    assert vm.physical.etp["source"] == "osv"
    assert vm.physical.etp["confidence"] == 0.85
    assert vm.physical.etp["layout"] == {"ceiling_height_m": 3.1, "finish_state": "good"}
    assert vm.physical.etp["risks"] == {"legal_risks": ["спор о праве"]}


def test_build_object_viewmodel_etp_absent_when_no_profile(db: Path) -> None:
    vm = build_object_viewmodel(db, "61:44:0050706:99")
    assert vm.physical.etp is None


def test_build_object_viewmodel_etp_absent_when_table_missing(db_no_etp: Path) -> None:
    vm = build_object_viewmodel(db_no_etp, "61:44:0050706:31")
    assert vm.physical.etp is None


def test_build_object_viewmodel_rights_with_share_and_beneficiaries(db: Path) -> None:
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    assert len(vm.ownership.rights) == 2
    first = vm.ownership.rights[0]
    assert first.right_type == "собственность"
    assert first.right_holder_inn == "7707083893"
    assert first.share == "1/2"
    assert first.registration_number == "RR-001"
    inns = {b.inn for b in vm.ownership.beneficiaries}
    assert inns == {"7707083893", "500100123456"}


def test_build_object_viewmodel_beneficiaries_dedup_by_inn(db: Path) -> None:
    # Оба права тянут разные ИНН — оба бенефициара уникальны.
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    assert len(vm.ownership.beneficiaries) == 2


def test_build_object_viewmodel_temporal_latest_extract(db: Path) -> None:
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    assert vm.temporal.extract_date == "2026-05-20"
    assert vm.temporal.as_of_date is None


def test_build_object_viewmodel_as_of_filters_future_rights(db: Path) -> None:
    # as_of = 2025-12-31 → не показывать право 2026-01-15
    vm = build_object_viewmodel(db, "61:44:0050706:31", as_of="2025-12-31")
    assert len(vm.ownership.rights) == 1
    assert vm.ownership.rights[0].registration_date == "2024-05-10"
    assert vm.temporal.as_of_date == "2025-12-31"


def test_build_object_viewmodel_geo_stub(db: Path) -> None:
    # C1: гео ещё не материализовано — пустой stub валиден по схеме.
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    assert vm.geo.center is None
    assert vm.geo.geometry is None
    assert vm.geo.extrude is False


def test_build_object_viewmodel_not_found_raises(db: Path) -> None:
    with pytest.raises(ObjectNotFound):
        build_object_viewmodel(db, "00:00:0000000:00")


def test_build_object_viewmodel_serializes_to_dict(db: Path) -> None:
    # Защита от расхождения с openapi/viewmodel.schema.json: structure smoke.
    vm = build_object_viewmodel(db, "61:44:0050706:31")
    d = vm.model_dump(exclude_none=False)
    for key in ("kind", "id", "physical", "ownership", "geo", "temporal"):
        assert key in d
    assert d["kind"] == "object"
