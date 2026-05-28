"""tests/test_build_lot_context.py — Stage 1 ЭТП-экспортёра.

Покрывает:
- Загрузка фикстуры PR #53 в БД с миграцией 0001.
- build_lot_context для всех лотов фикстуры → структура соответствует SPEC §3.
- Multi-cad лот (lot:pirushin:001) — extras.notes содержит ссылку на доп. КН.
- Лот с llm-профилем (low confidence) — building/layout пусты.
- Ошибки: несуществующий лот; лот без items и без target_cad.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp import build_lot_context


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "etp" / "object_etp_profile_sample.json"


# ─────────────────────────────────────────────────────────────────────────────
#  Fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db() -> sqlite3.Connection:
    """БД in-memory с миграцией 0001 + загруженной фикстурой."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    # Минимальный objects + rights + entity_registry + object_restrictions.
    conn.executescript("""
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT,
            permitted_use TEXT, purpose TEXT, floors INTEGER
        );
        CREATE TABLE entity_registry (
            inn TEXT PRIMARY KEY,
            name_full TEXT NOT NULL, name_short TEXT, ogrn TEXT, entity_type TEXT
        );
        CREATE TABLE rights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cad_number TEXT NOT NULL REFERENCES objects(cad_number),
            right_type TEXT NOT NULL,
            right_holder_inn TEXT REFERENCES entity_registry(inn),
            share_numerator INTEGER, share_denominator INTEGER,
            registration_number TEXT, registration_date TEXT, source_extract_id INTEGER
        );
        CREATE TABLE object_restrictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cad_number TEXT NOT NULL REFERENCES objects(cad_number),
            restrict_type TEXT, description TEXT, registry_number TEXT,
            valid_from TEXT, valid_to TEXT, basis_doc TEXT
        );
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))

    # Подгружаем objects.
    objects = {
        "61:44:0050706:31": ("room", "г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII", 125.4, "офис", 3),
        "61:44:0050706:42": ("room", "г. Ростов-на-Дону, ул. Промышленная, 5", 380.0, "склад", 1),
        "61:44:0050706:7":  ("land", "Ростовская обл., с. Иваново, уч. 7", 5000.0, None, None),
    }
    for cad, (ot, addr, area, purp, floor) in objects.items():
        conn.execute(
            "INSERT INTO objects(cad_number, object_type, address, area, purpose, floors) "
            "VALUES (?,?,?,?,?,?)",
            (cad, ot, addr, area, purp, floor),
        )

    # entity + право для kase A
    conn.execute(
        "INSERT INTO entity_registry(inn, name_full, entity_type) VALUES (?,?,?)",
        ("7708078840", "Российская Федерация", "Гос"),
    )
    conn.execute(
        "INSERT INTO rights(cad_number, right_type, right_holder_inn, registration_number, registration_date) "
        "VALUES (?,?,?,?,?)",
        ("61:44:0050706:31", "собственность", "7708078840", "61-61/044-77/001/001/2015-123", "2015-06-10"),
    )

    # Ограничение для KN:42 (склад) — действующее
    conn.execute(
        "INSERT INTO object_restrictions(cad_number, restrict_type, description, valid_from, valid_to) "
        "VALUES (?,?,?,?,?)",
        ("61:44:0050706:42", "ипотека", "в пользу банка X", "2024-01-15", None),
    )

    # Фикстура profile + lots + lot_items
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for p in fx["object_etp_profile"]:
        conn.execute(
            "INSERT INTO object_etp_profile("
            "cad_number, location_extra, building_extra, layout, legal_extra, risks, extras,"
            "source, confidence, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                p["cad_number"],
                json.dumps(p.get("location_extra"), ensure_ascii=False) if p.get("location_extra") else None,
                json.dumps(p.get("building_extra"), ensure_ascii=False) if p.get("building_extra") else None,
                json.dumps(p.get("layout"), ensure_ascii=False) if p.get("layout") else None,
                json.dumps(p.get("legal_extra"), ensure_ascii=False) if p.get("legal_extra") else None,
                json.dumps(p.get("risks"), ensure_ascii=False) if p.get("risks") else None,
                json.dumps(p.get("extras"), ensure_ascii=False) if p.get("extras") else None,
                p["source"], p["confidence"], p["updated_at"],
            ),
        )
    for lot in fx["lots"]:
        conn.execute(
            "INSERT INTO lots(lot_id, name, platform_targets, procedure_type, deal_type, "
            "primary_cad_number, notes_md, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                lot["lot_id"], lot["name"],
                json.dumps(lot.get("platform_targets"), ensure_ascii=False) if lot.get("platform_targets") else None,
                lot.get("procedure_type"), lot.get("deal_type"),
                lot.get("primary_cad_number"), lot.get("notes_md"), lot["created_at"],
            ),
        )
    for it in fx["lot_items"]:
        conn.execute(
            "INSERT INTO lot_items(lot_id, cad_number, role, ord) VALUES (?,?,?,?)",
            (it["lot_id"], it["cad_number"], it["role"], it["ord"]),
        )
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты
# ─────────────────────────────────────────────────────────────────────────────

SPEC_SECTIONS = {"meta", "identity", "location", "building",
                 "layout_and_condition", "legal", "risks", "extras", "generated_text"}


def test_ctx_has_spec_sections(db):
    ctx = build_lot_context(db, "lot:pirushin:001")
    assert set(ctx.keys()) == SPEC_SECTIONS


def test_meta_carries_platform_and_procedure(db):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            platform="sberbank-ast.ru", platform_mode="full")
    assert ctx["meta"]["platform"] == "sberbank-ast.ru"
    assert ctx["meta"]["platform_mode"] == "full"
    assert ctx["meta"]["deal_type"] == "sale"
    assert "банкрот" in ctx["meta"]["procedure_type"]
    assert ctx["meta"]["locale"] == "ru-RU"


def test_identity_for_room_object(db):
    """Pirushin primary КН = :31 (room) — area_total_sqm заполнен, area_land_sqm пуст."""
    ctx = build_lot_context(db, "lot:pirushin:001")
    ident = ctx["identity"]
    assert ident["cadastral_number"] == "61:44:0050706:31"
    assert ident["title"] == "Нежилое помещение"
    assert ident["purpose"] == "офис"
    assert ident["area_total_sqm"] == 125.4
    assert ident["area_land_sqm"] is None
    assert ident["floor"] == 3
    assert ident["floors_total"] is None


def test_identity_for_land_object(db):
    """Лот с target_cad=:7 (land) — area_land_sqm заполнен."""
    ctx = build_lot_context(db, "lot:pirushin:001", target_cad_number="61:44:0050706:7")
    ident = ctx["identity"]
    assert ident["title"] == "Земельный участок"
    assert ident["area_total_sqm"] is None
    assert ident["area_land_sqm"] == 5000.0
    assert ident["floor"] is None


def test_location_uses_etp_profile_extras(db):
    ctx = build_lot_context(db, "lot:pirushin:001")
    loc = ctx["location"]
    assert loc["address_raw"] == "г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII"
    assert loc["landmark"] == "в 7 минутах пешком от станции метро «Тверская»"
    assert loc["environment_short"].startswith("зона смешанной")
    # Адрес теперь разбирается компонентно (address_parser).
    assert loc["locality"] == "г. Ростов-на-Дону"
    assert loc["street"] == "ул. Б.Садовая"
    assert loc["house"] == "111"
    assert loc["room"] == "пом. VII"


def test_building_filled_from_profile(db):
    ctx = build_lot_context(db, "lot:pirushin:001")
    b = ctx["building"]
    assert b["renovation_year"] == 2015
    assert b["wear_degree"] == "удовлетворительное"
    assert b["engineering"]["electricity"] == "подключено"
    assert "парковочные" in b["amenities"][1]


def test_building_empty_for_land(db):
    """Земельный участок (case C) — building_extra=null → ctx.building = {}."""
    ctx = build_lot_context(db, "lot:pirushin:001", target_cad_number="61:44:0050706:7")
    assert ctx["building"] == {}


def test_layout_empty_for_low_confidence_land(db):
    """Case C: layout=null в фикстуре → ctx.layout_and_condition = {}."""
    ctx = build_lot_context(db, "lot:pirushin:001", target_cad_number="61:44:0050706:7")
    assert ctx["layout_and_condition"] == {}


def test_legal_includes_right_and_encumbrances(db):
    """Case A (КН :31): право собственности на РФ."""
    ctx = build_lot_context(db, "lot:pirushin:001")
    legal = ctx["legal"]
    assert legal["right_type"] == "собственность"
    assert legal["right_holder"] == "Российская Федерация"
    assert legal["zoning"] == "общественно-деловая зона"
    assert legal["encumbrances"] == []  # у :31 нет ограничений
    assert "шумных" in legal["special_restrictions"][0]


def test_legal_encumbrances_for_storage(db):
    """Case B (КН :42): ипотека из object_restrictions попадает в encumbrances[]."""
    ctx = build_lot_context(db, "lot:sosna-rocha:042")
    enc = ctx["legal"]["encumbrances"]
    assert len(enc) == 1
    assert enc[0]["type"] == "ипотека"
    assert enc[0]["description"] == "в пользу банка X"


def test_risks_passthrough(db):
    """Case B имеет 2 technical + 1 legal + 1 location risk."""
    ctx = build_lot_context(db, "lot:sosna-rocha:042")
    r = ctx["risks"]
    assert len(r["technical_risks"]) == 2
    assert len(r["legal_risks"]) == 1
    assert len(r["location_risks"]) == 1
    assert r["other_risks"] == []


def test_extras_notes_mentions_other_lot_items(db):
    """Multi-cad лот pirushin:001 включает :31 (primary) + :7 (земля).
    extras.notes должен упомянуть :7."""
    ctx = build_lot_context(db, "lot:pirushin:001")
    notes = ctx["extras"]["notes"]
    assert notes is not None
    assert "61:44:0050706:7" in notes
    assert "land" in notes
    # Исходное notes из фикстуры тоже сохраняется.
    assert "отчёте об оценке" in notes


def test_extras_for_single_cad_lot(db):
    """sosna-rocha:042 — лот из одного КН: extras.notes = None (фикстура без notes)."""
    ctx = build_lot_context(db, "lot:sosna-rocha:042")
    assert ctx["extras"]["notes"] is None


def test_unknown_lot_raises(db):
    with pytest.raises(LookupError):
        build_lot_context(db, "lot:nonexistent:999")


def test_lot_without_items_or_target_raises(db):
    """Лот без primary_cad и без items → ValueError."""
    db.execute("INSERT INTO lots(lot_id, name) VALUES ('lot:empty:001', 'empty')")
    with pytest.raises(ValueError):
        build_lot_context(db, "lot:empty:001")
