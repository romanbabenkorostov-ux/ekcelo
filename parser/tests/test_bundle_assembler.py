"""Тесты оркестратора каталога Bundle (C3): сборка + manifest + verify."""
import json
import sqlite3

from egrn_parser import bundle_assembler as BA
from egrn_parser import lot_assembler as LA


def _inputs(tmp_path):
    (tmp_path / "src").mkdir()
    kmz = tmp_path / "src" / "project.kmz"; kmz.write_bytes(b"PKkmz-stub")
    db = tmp_path / "src" / "db.sqlite"; db.write_bytes(b"sqlite-stub")
    j1 = tmp_path / "src" / "structure_20240501.json"; j1.write_text('{"s":1}')
    obj = tmp_path / "src" / "obj.json"; obj.write_text('{"cad":"x"}')
    return kmz, db, j1, obj


def test_assemble_object_bundle(tmp_path):
    kmz, db, j1, obj = _inputs(tmp_path)
    out = tmp_path / "bundle"
    m = BA.assemble_bundle(
        out, kmz=kmz, db=db, json_files=[j1],
        objects_json={"61:44:0050706:31": obj},
        kind="object", objects=["61:44:0050706:31"],
        primary_cad_number="61:44:0050706:31", extract_date="2024-05-01",
        etp_layer_present=True, generated_at="2024-05-01T10:00:00+00:00")
    # структура каталога
    assert (out / "project.kmz").exists() and (out / "db.sqlite").exists()
    assert (out / "json" / "structure_20240501.json").exists()
    assert (out / "json" / "objects" / "61:44:0050706:31.json").exists()
    assert (out / "manifest.json").exists()
    # manifest
    paths = {f["path"] for f in m["files"]}
    assert "project.kmz" in paths and "db.sqlite" in paths
    assert "json/structure_20240501.json" in paths
    assert "json/objects/61:44:0050706:31.json" in paths
    assert m["kind"] == "object" and m["etp_layer_present"] is True
    # files[] детерминированно отсортирован
    assert [f["path"] for f in m["files"]] == sorted(f["path"] for f in m["files"])
    assert BA.verify_bundle(out) == []


def test_assemble_lot_bundle_with_fragment(tmp_path):
    kmz, db, j1, obj = _inputs(tmp_path)
    c = sqlite3.connect(":memory:")
    c.executescript("""CREATE TABLE objects(cad_number TEXT PRIMARY KEY, object_type TEXT, updated_at TEXT);
        CREATE TABLE lots(lot_id TEXT PRIMARY KEY, name TEXT NOT NULL, primary_cad_number TEXT, created_at TEXT);
        CREATE TABLE lot_items(lot_id TEXT, cad_number TEXT, role TEXT, ord INTEGER, PRIMARY KEY(lot_id,cad_number));""")
    c.executemany("INSERT INTO objects VALUES(?,?,?)",
                  [("61:44:0050706:31", "building", "2024-01-01"),
                   ("61:44:0050706:10", "land", "2024-01-01")])
    c.commit()
    frag = LA.assemble_lot(c, "lot-1", "Лот", include={"globs": ["61:44:*"]}, as_of="2024-12-31")
    out = tmp_path / "lot_bundle"
    m = BA.assemble_bundle(out, kmz=kmz, db=db, json_files=[j1],
                           kind="lot", objects=frag["members"], lot=frag,
                           generated_at="2024-05-01T10:00:00+00:00")
    assert m["kind"] == "lot" and m["lot"]["members"] == frag["members"]
    assert m["objects"] == frag["members"]
    assert BA.verify_bundle(out) == []


def test_deterministic_file_hashes(tmp_path):
    kmz, db, j1, obj = _inputs(tmp_path)
    m1 = BA.assemble_bundle(tmp_path / "b1", kmz=kmz, db=db, kind="object",
                            objects=["x"], generated_at="2024-05-01T10:00:00+00:00")
    m2 = BA.assemble_bundle(tmp_path / "b2", kmz=kmz, db=db, kind="object",
                            objects=["x"], generated_at="2024-09-09T20:00:00+00:00")
    # те же входы → те же sha256 файлов (несмотря на разный generated_at)
    h1 = {f["path"]: f["sha256"] for f in m1["files"]}
    h2 = {f["path"]: f["sha256"] for f in m2["files"]}
    assert h1 == h2


def test_verify_detects_tampering(tmp_path):
    kmz, db, j1, obj = _inputs(tmp_path)
    out = tmp_path / "b"
    BA.assemble_bundle(out, kmz=kmz, db=db, kind="object", objects=["x"],
                       generated_at="2024-05-01T10:00:00+00:00")
    (out / "db.sqlite").write_bytes(b"tampered")          # порча файла
    errs = BA.verify_bundle(out)
    assert any("db.sqlite" in e and "sha256" in e for e in errs)


def test_lot_kind_requires_lot_block(tmp_path):
    kmz, db, j1, obj = _inputs(tmp_path)
    try:
        BA.assemble_bundle(tmp_path / "b", kmz=kmz, db=db, kind="lot",
                           objects=["x"], generated_at="2024-05-01T10:00:00+00:00")
        assert False
    except ValueError as e:
        assert "lot" in str(e)
