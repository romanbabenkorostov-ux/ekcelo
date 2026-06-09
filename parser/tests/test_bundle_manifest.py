"""Тесты Bundle-manifest эмиттера (C3): sha256 файлов + сборка/валидация manifest."""
import sqlite3

from egrn_parser import bundle_manifest as BM
from egrn_parser import lot_assembler as LA


def test_sha256_and_file_entry(tmp_path):
    p = tmp_path / "db.sqlite"
    p.write_bytes(b"hello ekcelo")
    fe = BM.file_entry(p, arcname="db.sqlite")
    assert fe["path"] == "db.sqlite"
    assert fe["bytes"] == 12
    assert len(fe["sha256"]) == 64
    assert fe["sha256"] == BM.sha256_file(p)        # детерминирован


def test_build_and_validate_object_manifest(tmp_path):
    p = tmp_path / "project.kmz"
    p.write_bytes(b"PKzip-stub")
    m = BM.build_manifest(kind="object", files=[BM.file_entry(p, arcname="project.kmz")],
                          objects=["61:44:0050706:31"], primary_cad_number="61:44:0050706:31",
                          extract_date="2024-05-01", etp_layer_present=True)
    assert BM.validate_manifest(m) == []
    assert m["kind"] == "object" and m["etp_layer_present"] is True
    assert "lot" not in m


def test_lot_manifest_end_to_end(tmp_path):
    # собрать лот → фрагмент → manifest kind=lot
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE objects(cad_number TEXT PRIMARY KEY, object_type TEXT, updated_at TEXT);
    CREATE TABLE lots(lot_id TEXT PRIMARY KEY, name TEXT NOT NULL, primary_cad_number TEXT,
        created_at TEXT DEFAULT(datetime('now')));
    CREATE TABLE lot_items(lot_id TEXT, cad_number TEXT, role TEXT, ord INTEGER,
        PRIMARY KEY(lot_id, cad_number));
    """)
    c.executemany("INSERT INTO objects VALUES(?,?,?)", [
        ("61:44:0050706:31", "building", "2024-01-10"),
        ("61:44:0050706:10", "land", "2024-01-10")])
    c.commit()
    frag = LA.assemble_lot(c, "lot-1", "Лот", include={"globs": ["61:44:*"]},
                           as_of="2024-12-31")
    f = tmp_path / "db.sqlite"; f.write_bytes(b"x")
    m = BM.build_manifest(kind="lot", files=[BM.file_entry(f, arcname="db.sqlite")],
                          objects=frag["members"], lot=frag, etp_layer_present=False)
    assert BM.validate_manifest(m) == []
    assert m["lot"]["members"] == ["61:44:0050706:10", "61:44:0050706:31"]
    assert m["objects"] == m["lot"]["members"]


def test_validate_catches_errors():
    bad = {"kind": "lot", "objects": [], "files": [{"path": "x", "sha256": "ZZ"}],
           "bundle_version": "1.0", "contracts_version": "1.0.0",
           "kmz_contract_version": "2.12.0", "generated_at": "now"}
    errs = BM.validate_manifest(bad)
    assert any("lot" in e for e in errs)            # kind=lot без блока lot
    assert any("bundle_version" in e for e in errs) # не semver
    assert any("sha256" in e for e in errs)         # плохой хеш


def test_no_extra_keys():
    m = BM.build_manifest(kind="object", files=[], objects=[])
    m["rogue"] = 1
    assert any("недопустимое поле" in e for e in BM.validate_manifest(m))
