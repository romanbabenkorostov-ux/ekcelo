"""Тесты слоя экспорта pkg-схемы → C2 (ADR-007)."""
import sqlite3

from egrn_parser import schema_export as SE


def _pkg_db(tmp_path):
    p = tmp_path / "pkg.db"
    c = sqlite3.connect(p)
    c.executescript("""
    CREATE TABLE building_objects(cad_number TEXT PRIMARY KEY, object_type TEXT, address TEXT,
        area REAL, permitted_uses TEXT, purpose TEXT, floors_above_ground INTEGER);
    CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, address TEXT, area REAL,
        land_category TEXT, permitted_uses TEXT);
    CREATE TABLE entity_registry(entity_id INTEGER PRIMARY KEY, inn TEXT, ogrn TEXT,
        entity_type TEXT, name_full TEXT, name_short TEXT);
    CREATE TABLE rights(right_id INTEGER PRIMARY KEY, object_key_type TEXT, object_key_value TEXT,
        right_category TEXT, right_type TEXT, right_number TEXT, right_date TEXT,
        share_numerator INT, share_denominator INT, valid_from TEXT, valid_until TEXT, basis TEXT);
    CREATE TABLE right_holders(holder_id INTEGER PRIMARY KEY, right_id INTEGER, inn TEXT);
    CREATE TABLE extracts(extract_id INTEGER PRIMARY KEY, extract_number TEXT, cad_number TEXT,
        extract_date TEXT, object_class TEXT, schema_id TEXT, extract_template TEXT);
    CREATE TABLE object_etp_profile(cad_number TEXT PRIMARY KEY, location_extra TEXT,
        building_extra TEXT, layout TEXT, legal_extra TEXT, risks TEXT, extras TEXT,
        source TEXT, confidence REAL, updated_at TEXT);
    CREATE TABLE lots(lot_id TEXT PRIMARY KEY, name TEXT, platform_targets TEXT, procedure_type TEXT,
        deal_type TEXT, primary_cad_number TEXT, notes_md TEXT, created_at TEXT);
    CREATE TABLE lot_items(lot_id TEXT, cad_number TEXT, role TEXT, ord INT);
    """)
    c.execute("INSERT INTO building_objects VALUES('23:15:0804000:200','building','ул. 1',500.0,'виноделие','произв.',2)")
    c.execute("INSERT INTO land_objects VALUES('23:15:0804000:66','поле',166600.0,'земли с/х','виноградники')")
    c.execute("INSERT INTO entity_registry VALUES(1,'2312000000','1022300000','ЮЛ','ООО Винодельня','Винодельня')")
    c.execute("INSERT INTO entity_registry VALUES(2,NULL,NULL,'ФЛ','Без ИНН',NULL)")
    c.execute("INSERT INTO rights VALUES(1,'cad_number','23:15:0804000:200','right','ownership','77-1','2020-01-01',1,1,NULL,NULL,NULL)")
    c.execute("INSERT INTO rights VALUES(2,'cad_number','23:15:0804000:200','encumbrance','ипотека','77-2','2021-01-01',NULL,NULL,'2021-01-01','2031-01-01','залог')")
    c.execute("INSERT INTO right_holders VALUES(1,1,'2312000000')")
    c.execute("INSERT INTO extracts VALUES(1,'99/2024','23:15:0804000:200','2024-05-01','building','v1.10','ЕГРН')")
    c.execute("INSERT INTO object_etp_profile VALUES('23:15:0804000:200',NULL,'{\"wear_degree\":30}',NULL,NULL,NULL,NULL,'manual',0.95,NULL)")
    c.execute("INSERT INTO lots VALUES('lot-1','Винохозяйство',NULL,NULL,'sale','23:15:0804000:66',NULL,NULL)")
    c.execute("INSERT INTO lot_items VALUES('lot-1','23:15:0804000:66','land',1)")
    c.commit(); c.close()
    return p


def test_objects_merge_building_and_land(tmp_path):
    SE.export_to_c2(_pkg_db(tmp_path), tmp_path / "c2.db")
    d = sqlite3.connect(tmp_path / "c2.db"); d.row_factory = sqlite3.Row
    rows = {r["cad_number"]: r for r in d.execute("SELECT * FROM objects")}
    assert rows["23:15:0804000:200"]["object_type"] == "building"
    assert rows["23:15:0804000:200"]["floors"] == 2
    assert rows["23:15:0804000:66"]["object_type"] == "land"
    assert rows["23:15:0804000:66"]["category"] == "земли с/х"


def test_entity_requires_inn(tmp_path):
    SE.export_to_c2(_pkg_db(tmp_path), tmp_path / "c2.db")
    d = sqlite3.connect(tmp_path / "c2.db")
    inns = [r[0] for r in d.execute("SELECT inn FROM entity_registry")]
    assert inns == ["2312000000"]                    # строка без ИНН пропущена


def test_rights_vs_restrictions_split(tmp_path):
    SE.export_to_c2(_pkg_db(tmp_path), tmp_path / "c2.db")
    d = sqlite3.connect(tmp_path / "c2.db"); d.row_factory = sqlite3.Row
    rights = list(d.execute("SELECT * FROM rights"))
    assert len(rights) == 1 and rights[0]["right_type"] == "ownership"
    assert rights[0]["right_holder_inn"] == "2312000000"   # из right_holders
    restr = list(d.execute("SELECT * FROM object_restrictions"))
    assert len(restr) == 1 and restr[0]["restrict_type"] == "ипотека"
    assert restr[0]["valid_to"] == "2031-01-01"


def test_section6_copied_and_counts(tmp_path):
    counts = SE.export_to_c2(_pkg_db(tmp_path), tmp_path / "c2.db")
    assert counts["objects"] == 2 and counts["rights"] == 1
    assert counts["object_restrictions"] == 1 and counts["entity_registry"] == 1
    assert counts["object_etp_profile"] == 1 and counts["lots"] == 1 and counts["lot_items"] == 1
    d = sqlite3.connect(tmp_path / "c2.db")
    import json
    be = json.loads(d.execute("SELECT building_extra FROM object_etp_profile").fetchone()[0])
    assert be["wear_degree"] == 30                   # §6 скопирован дословно


def test_fk_integrity_no_orphans(tmp_path):
    SE.export_to_c2(_pkg_db(tmp_path), tmp_path / "c2.db")
    d = sqlite3.connect(tmp_path / "c2.db")
    orphan_rights = d.execute(
        "SELECT COUNT(*) FROM rights WHERE cad_number NOT IN (SELECT cad_number FROM objects)").fetchone()[0]
    orphan_inn = d.execute(
        "SELECT COUNT(*) FROM rights WHERE right_holder_inn IS NOT NULL "
        "AND right_holder_inn NOT IN (SELECT inn FROM entity_registry)").fetchone()[0]
    assert orphan_rights == 0 and orphan_inn == 0


def test_cli_export_c2(tmp_path):
    """CLI `egrn-parser export-c2` создаёт C2-БД из рабочей."""
    from egrn_parser import cli
    pkg = _pkg_db(tmp_path)
    out = tmp_path / "c2.sqlite"
    try:
        cli.main(["export-c2", "--db", str(pkg), "--out", str(out)])
    except SystemExit as e:
        assert e.code == 0
    d = sqlite3.connect(out)
    assert d.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 2
    # C2-таблицы созданы
    tabs = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"objects", "rights", "object_restrictions", "extracts",
            "entity_registry", "object_etp_profile"} <= tabs


def test_graceful_missing_tables(tmp_path):
    """pkg-БД без некоторых таблиц → экспорт не падает, счётчики 0."""
    p = tmp_path / "min.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE building_objects(cad_number TEXT PRIMARY KEY, object_type TEXT, address TEXT, area REAL, permitted_uses TEXT, purpose TEXT, floors_above_ground INTEGER)")
    c.execute("INSERT INTO building_objects VALUES('1:1:1:1','building',NULL,NULL,NULL,NULL,NULL)")
    c.commit(); c.close()
    counts = SE.export_to_c2(p, tmp_path / "c2.db")
    assert counts["objects"] == 1 and counts["rights"] == 0 and counts["lots"] == 0
