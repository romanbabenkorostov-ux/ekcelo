"""tests/test_text_render.py — Stage 2 ЭТП-экспортёра (Jinja-рендер).

Покрывает render_lot_description(ctx) для 3 платформ × 2 mode, сравнением
с golden-файлами в parser/tests/golden/etp/.

Golden-файлы фиксируют текущее поведение шаблона
`parser/exporters/etp/templates/torgi_long_description.j2` (импортирован
из docs/etp_export/05_*.md как есть). Изменения в шаблоне → re-generate
goldens явно: `python3 parser/scripts/dev/gen_etp_golden.py`.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp import (
    available_modes,
    available_platforms,
    build_lot_context,
    render_lot_description,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "etp" / "object_etp_profile_sample.json"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "etp"


# ─────────────────────────────────────────────────────────────────────────────
#  Fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db() -> sqlite3.Connection:
    """БД in-memory: schema + миграция 0001 + загруженная фикстура.

    Минимальное состояние: 3 КН в objects (одинаковое для всех тестов),
    одно право на :31, одно ограничение на :42.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
        CREATE TABLE entity_registry (inn TEXT PRIMARY KEY, name_full TEXT NOT NULL,
            name_short TEXT, ogrn TEXT, entity_type TEXT);
        CREATE TABLE rights (id INTEGER PRIMARY KEY AUTOINCREMENT,
            cad_number TEXT NOT NULL REFERENCES objects(cad_number),
            right_type TEXT NOT NULL, right_holder_inn TEXT REFERENCES entity_registry(inn),
            share_numerator INTEGER, share_denominator INTEGER,
            registration_number TEXT, registration_date TEXT, source_extract_id INTEGER);
        CREATE TABLE object_restrictions (id INTEGER PRIMARY KEY AUTOINCREMENT,
            cad_number TEXT NOT NULL REFERENCES objects(cad_number),
            restrict_type TEXT, description TEXT, registry_number TEXT,
            valid_from TEXT, valid_to TEXT, basis_doc TEXT);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))

    for cad, ot, addr, area, purp, floor in [
        ("61:44:0050706:31", "room", "г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII", 125.4, "офис", 3),
        ("61:44:0050706:42", "room", "г. Ростов-на-Дону, ул. Промышленная, 5", 380.0, "склад", 1),
        ("61:44:0050706:7",  "land", "Ростовская обл., с. Иваново, уч. 7", 5000.0, None, None),
    ]:
        conn.execute("INSERT INTO objects(cad_number,object_type,address,area,purpose,floors) "
                     "VALUES(?,?,?,?,?,?)", (cad, ot, addr, area, purp, floor))
    conn.execute("INSERT INTO entity_registry(inn,name_full,entity_type) VALUES(?,?,?)",
                 ("7708078840", "Российская Федерация", "Гос"))
    conn.execute("INSERT INTO rights(cad_number,right_type,right_holder_inn,registration_number,"
                 "registration_date) VALUES(?,?,?,?,?)",
                 ("61:44:0050706:31", "собственность", "7708078840",
                  "61-61/044-77/001/001/2015-123", "2015-06-10"))
    conn.execute("INSERT INTO object_restrictions(cad_number,restrict_type,description,"
                 "valid_from,valid_to) VALUES(?,?,?,?,?)",
                 ("61:44:0050706:42", "ипотека", "в пользу банка X", "2024-01-15", None))

    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for p in fx["object_etp_profile"]:
        conn.execute(
            "INSERT INTO object_etp_profile(cad_number, location_extra, building_extra, layout,"
            " legal_extra, risks, extras, source, confidence, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p["cad_number"],
             json.dumps(p.get("location_extra"), ensure_ascii=False) if p.get("location_extra") else None,
             json.dumps(p.get("building_extra"), ensure_ascii=False) if p.get("building_extra") else None,
             json.dumps(p.get("layout"), ensure_ascii=False) if p.get("layout") else None,
             json.dumps(p.get("legal_extra"), ensure_ascii=False) if p.get("legal_extra") else None,
             json.dumps(p.get("risks"), ensure_ascii=False) if p.get("risks") else None,
             json.dumps(p.get("extras"), ensure_ascii=False) if p.get("extras") else None,
             p["source"], p["confidence"], p["updated_at"]))
    for lot in fx["lots"]:
        conn.execute(
            "INSERT INTO lots(lot_id, name, platform_targets, procedure_type, deal_type,"
            " primary_cad_number, notes_md, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (lot["lot_id"], lot["name"],
             json.dumps(lot.get("platform_targets"), ensure_ascii=False) if lot.get("platform_targets") else None,
             lot.get("procedure_type"), lot.get("deal_type"),
             lot.get("primary_cad_number"), lot.get("notes_md"), lot["created_at"]))
    for it in fx["lot_items"]:
        conn.execute("INSERT INTO lot_items(lot_id, cad_number, role, ord) VALUES (?,?,?,?)",
                     (it["lot_id"], it["cad_number"], it["role"], it["ord"]))
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  Метаданные
# ─────────────────────────────────────────────────────────────────────────────

def test_available_platforms_and_modes():
    plats = available_platforms()
    assert "torgi.gov.ru" in plats
    assert "roseltorg.ru" in plats
    assert "sberbank-ast.ru" in plats
    assert set(available_modes()) == {"short", "full"}


def test_invalid_platform_raises(db):
    ctx = build_lot_context(db, "lot:pirushin:001")
    ctx["meta"]["platform"] = "nonexistent.ru"
    with pytest.raises(ValueError, match="Unknown platform"):
        render_lot_description(ctx)


def test_invalid_mode_raises(db):
    ctx = build_lot_context(db, "lot:pirushin:001")
    ctx["meta"]["platform_mode"] = "verbose"
    with pytest.raises(ValueError, match="Unknown platform_mode"):
        render_lot_description(ctx)


# ─────────────────────────────────────────────────────────────────────────────
#  Параметризованные golden-сравнения (case A, office :31)
# ─────────────────────────────────────────────────────────────────────────────

PLATFORM_SLUGS = {
    "torgi.gov.ru":     "torgi_gov_ru",
    "roseltorg.ru":     "roseltorg_ru",
    "sberbank-ast.ru":  "sberbank-ast_ru",
}


def _read_golden(path):
    """Прочитать golden, нормализуя CRLF→LF для Windows-checkout'ов
    (даже если .gitattributes не сработал у клиента — например, после
    переноса архивом или ручного редактирования в Notepad)."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("platform", list(PLATFORM_SLUGS.keys()))
@pytest.mark.parametrize("mode", ["short", "full"])
def test_render_caseA_office_matches_golden(db, platform, mode):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            platform=platform, platform_mode=mode,
                            target_cad_number="61:44:0050706:31")
    text = render_lot_description(ctx)
    golden = GOLDEN_DIR / f"caseA_office_{PLATFORM_SLUGS[platform]}_{mode}.txt"
    expected = _read_golden(golden)
    assert text == expected, (
        f"Diverged from {golden.name}. Re-generate via "
        f"`python3 parser/scripts/dev/gen_etp_golden.py` if change is intentional."
    )


def test_render_caseC_land_torgi_short(db):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            platform="torgi.gov.ru", platform_mode="short",
                            target_cad_number="61:44:0050706:7")
    text = render_lot_description(ctx)
    golden = GOLDEN_DIR / "caseC_land_torgi_gov_ru_short.txt"
    assert text == _read_golden(golden)


def test_render_caseB_storage_sberbank_full(db):
    ctx = build_lot_context(db, "lot:sosna-rocha:042",
                            platform="sberbank-ast.ru", platform_mode="full")
    text = render_lot_description(ctx)
    golden = GOLDEN_DIR / "caseB_storage_sberbank_ast_ru_full.txt"
    assert text == _read_golden(golden)


# ─────────────────────────────────────────────────────────────────────────────
#  Семантические инварианты (не зависят от точного текста)
# ─────────────────────────────────────────────────────────────────────────────

def test_render_contains_cadastral_number(db):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            target_cad_number="61:44:0050706:31")
    text = render_lot_description(ctx)
    assert "61:44:0050706:31" in text


def test_render_includes_address(db):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            target_cad_number="61:44:0050706:31")
    text = render_lot_description(ctx)
    assert "Ростов" in text or "Б.Садовая" in text


def test_render_sberbank_full_mentions_bankruptcy(db):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            platform="sberbank-ast.ru", platform_mode="full",
                            target_cad_number="61:44:0050706:31")
    text = render_lot_description(ctx)
    assert "банкрот" in text.lower()


def test_render_storage_lot_includes_encumbrance(db):
    """Case B (sosna-rocha:042): ипотека из object_restrictions попадает в текст."""
    ctx = build_lot_context(db, "lot:sosna-rocha:042",
                            platform="torgi.gov.ru", platform_mode="full")
    text = render_lot_description(ctx)
    assert "ипотека" in text


def test_render_land_lot_uses_land_paragraph(db):
    """Земельный участок (case C) должен включать «земельный участок» а не «помещение»."""
    ctx = build_lot_context(db, "lot:pirushin:001",
                            platform="torgi.gov.ru", platform_mode="short",
                            target_cad_number="61:44:0050706:7")
    text = render_lot_description(ctx).lower()
    assert "земельный участок" in text


def test_render_strips_excessive_blank_lines(db):
    ctx = build_lot_context(db, "lot:pirushin:001",
                            target_cad_number="61:44:0050706:31")
    text = render_lot_description(ctx)
    assert "\n\n\n" not in text  # 3+ переносов нет
    assert text.endswith("\n")   # один trailing newline


def test_render_returns_non_empty_for_all_platforms(db):
    for plat in available_platforms():
        for mode in available_modes():
            ctx = build_lot_context(db, "lot:pirushin:001",
                                    platform=plat, platform_mode=mode,
                                    target_cad_number="61:44:0050706:31")
            text = render_lot_description(ctx)
            assert text.strip(), f"Empty render for {plat}/{mode}"
