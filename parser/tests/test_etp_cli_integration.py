"""tests/test_etp_cli_integration.py — Stage 3 ЭТП-экспортёра (CLI integration).

End-to-end: реальная sqlite-БД на диске + миграция + фикстура →
запуск CLI через main() → проверка структуры файлов и содержимого.

Покрывает:
- Все 6 комбинаций (3 платформы × 2 mode) создают .txt файлы.
- long_description.json пишется по одному на платформу.
- lot_appendix.md один на лот.
- Содержимое description.txt совпадает с goldens (regression check).
- Невалидные платформа/mode выходят с SystemExit.
- Несуществующий lot_id → LookupError из build_lot_appendix.
- Несуществующая БД → exit code 2.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from parser.exporters.etp.cli import main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "etp" / "object_etp_profile_sample.json"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "etp"


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """Реальная SQLite-БД на диске с миграцией + фикстурой + минимальным objects."""
    db = tmp_path / "ekcelo.sqlite"
    conn = sqlite3.connect(db)
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
    conn.close()
    return db


# ─────────────────────────────────────────────────────────────────────────────
#  Happy-path: full export
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_creates_expected_file_tree(db_file, tmp_path, capsys):
    """3 платформы × 2 mode + 1 appendix + 3 JSON = 10 файлов."""
    out = tmp_path / "etp_out"
    rc = main([
        "--lot", "lot:pirushin:001",
        "--db", str(db_file),
        "--platforms", "torgi.gov.ru,roseltorg.ru,sberbank-ast.ru",
        "--modes", "short,full",
        "--target-cad", "61:44:0050706:31",
        "--out", str(out),
    ])
    assert rc == 0

    lot_root = out / "lot_pirushin_001"
    assert (lot_root / "lot_appendix.md").exists()

    for plat in ["torgi.gov.ru", "roseltorg.ru", "sberbank-ast.ru"]:
        platform_dir = lot_root / plat.replace(":", "_").replace("/", "_")
        for mode in ["short", "full"]:
            txt = platform_dir / f"description.{mode}.txt"
            assert txt.exists(), f"missing {txt}"
            assert txt.read_text(encoding="utf-8").strip(), f"empty {txt}"
        assert (platform_dir / "long_description.json").exists()


def test_cli_description_matches_golden(db_file, tmp_path):
    """Содержимое description.short/full для torgi == golden из Stage 2."""
    out = tmp_path / "etp_out"
    main([
        "--lot", "lot:pirushin:001",
        "--db", str(db_file),
        "--platforms", "torgi.gov.ru",
        "--modes", "short,full",
        "--target-cad", "61:44:0050706:31",
        "--out", str(out),
        "--quiet",
    ])
    lot_dir = out / "lot_pirushin_001" / "torgi.gov.ru"
    for mode in ["short", "full"]:
        actual = (lot_dir / f"description.{mode}.txt").read_text(encoding="utf-8")
        expected = (GOLDEN_DIR / f"caseA_office_torgi_gov_ru_{mode}.txt").read_text(encoding="utf-8")
        assert actual == expected


def test_cli_appendix_includes_lot_data(db_file, tmp_path):
    """lot_appendix.md содержит lot_id, name, КН-членов."""
    out = tmp_path / "etp_out"
    main([
        "--lot", "lot:pirushin:001",
        "--db", str(db_file),
        "--platforms", "torgi.gov.ru",
        "--modes", "short",
        "--out", str(out),
        "--quiet",
    ])
    md = (out / "lot_pirushin_001" / "lot_appendix.md").read_text(encoding="utf-8")
    assert "lot:pirushin:001" in md
    assert "Пирушин" in md  # из lots.name
    assert "61:44:0050706:31" in md
    assert "61:44:0050706:7" in md  # второй КН из lot_items
    assert "банкрот" in md.lower()  # procedure_type


def test_cli_json_contains_ctx_meta(db_file, tmp_path):
    """long_description.json содержит meta.platform = тот же, что dir name."""
    out = tmp_path / "etp_out"
    main([
        "--lot", "lot:pirushin:001",
        "--db", str(db_file),
        "--platforms", "sberbank-ast.ru",
        "--modes", "full",
        "--target-cad", "61:44:0050706:31",
        "--out", str(out),
        "--quiet",
    ])
    j = json.loads((out / "lot_pirushin_001" / "sberbank-ast.ru" / "long_description.json").read_text(encoding="utf-8"))
    assert j["meta"]["platform"] == "sberbank-ast.ru"
    assert j["identity"]["cadastral_number"] == "61:44:0050706:31"


# ─────────────────────────────────────────────────────────────────────────────
#  Selective platforms / modes
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_single_platform_single_mode(db_file, tmp_path):
    out = tmp_path / "etp_out"
    rc = main([
        "--lot", "lot:sosna-rocha:042",
        "--db", str(db_file),
        "--platforms", "torgi.gov.ru",
        "--modes", "short",
        "--out", str(out),
        "--quiet",
    ])
    assert rc == 0
    lot_dir = out / "lot_sosna-rocha_042"
    assert (lot_dir / "torgi.gov.ru" / "description.short.txt").exists()
    assert not (lot_dir / "torgi.gov.ru" / "description.full.txt").exists()
    assert not (lot_dir / "roseltorg.ru").exists()


# ─────────────────────────────────────────────────────────────────────────────
#  Error handling
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_unknown_platform_exits(db_file, tmp_path):
    with pytest.raises(SystemExit) as ei:
        main(["--lot", "lot:pirushin:001", "--db", str(db_file),
              "--platforms", "nonexistent.ru", "--modes", "short",
              "--out", str(tmp_path / "out")])
    assert "nonexistent.ru" in str(ei.value)


def test_cli_unknown_mode_exits(db_file, tmp_path):
    with pytest.raises(SystemExit) as ei:
        main(["--lot", "lot:pirushin:001", "--db", str(db_file),
              "--platforms", "torgi.gov.ru", "--modes", "verbose",
              "--out", str(tmp_path / "out")])
    assert "verbose" in str(ei.value)


def test_cli_missing_db_returns_2(tmp_path, capsys):
    rc = main(["--lot", "lot:pirushin:001", "--db", str(tmp_path / "nope.sqlite"),
               "--platforms", "torgi.gov.ru", "--modes", "short",
               "--out", str(tmp_path / "out")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "db not found" in err


def test_cli_unknown_lot_raises(db_file, tmp_path):
    with pytest.raises(LookupError):
        main(["--lot", "lot:nonexistent:999", "--db", str(db_file),
              "--platforms", "torgi.gov.ru", "--modes", "short",
              "--out", str(tmp_path / "out")])
