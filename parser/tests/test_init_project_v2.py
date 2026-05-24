"""Тесты EXIF UserComment v1.1: `doc_id` + формула `doc::<doc_id>`.

Покрывает (контракт KMZ 2.12.0 §5 + EXIF schema v1.1):
1. `load_documents_index` строит два индекса: by_artifact_file (точная привязка
   через `artifacts[].file`) и by_extract_cad (fallback для выписок через
   subjects.cadastrals).
2. `resolve_doc_id` приоритет: artifact-file > extract-cad > None.
3. `resolve_doc_graph_node_id` — формула `doc::<doc_id>` приоритетнее
   cad/inn/ogrn (v1.1+).
4. Backward-compat: без `documents.json` → `doc_id = None`, старая семантика
   v1 не нарушена.
"""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "_init_v2", SCRIPTS / "pirushin_sosn_rocha_07_init_project_v2.py")
_init = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_init)


# ─── 1. load_documents_index ────────────────────────────────────────────────

def test_load_documents_index_empty_when_missing(tmp_path: Path):
    out = _init.load_documents_index(tmp_path)
    assert out == {"by_artifact_file": {}, "by_extract_cad": {}}


def test_load_documents_index_builds_both_maps(tmp_path: Path):
    data_dir = tmp_path / "_data"
    data_dir.mkdir()
    (data_dir / "documents.json").write_text(json.dumps({
        "schema_version": "1.0",
        "documents": [
            {
                "doc_id": "ee_a1b2c3d4",
                "kind": "egrn_extract",
                "doc_date": "2026-04-15",
                "subjects": {"cadastrals": ["61:44:0050706:31"]},
                "artifacts": [{"file": "docs/egrn_61_44_0050706_31_p1.jpg"}],
            },
            {
                "doc_id": "nr_ef567890",
                "kind": "notarial_release",
                "doc_date": "2026-03-01",
                "subjects": {"cadastrals": ["61:44:0050706:31"]},
                "artifacts": [{"file": "docs/release.jpg"}],
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")

    out = _init.load_documents_index(tmp_path)
    # by_artifact_file — по basename из artifacts[].file
    assert out["by_artifact_file"]["egrn_61_44_0050706_31_p1.jpg"] == "ee_a1b2c3d4"
    assert out["by_artifact_file"]["release.jpg"] == "nr_ef567890"
    # by_extract_cad — только для kind ∈ {egrn,egrul,egrip}_extract
    assert out["by_extract_cad"][("61:44:0050706:31", "egrn_extract")] == "ee_a1b2c3d4"
    assert ("61:44:0050706:31", "notarial_release") not in out["by_extract_cad"]


# ─── 2. resolve_doc_id ──────────────────────────────────────────────────────

def test_resolve_doc_id_priority_artifact_first():
    doc_index = {
        "by_artifact_file": {"my.jpg": "ee_artifact"},
        "by_extract_cad": {("61:44:0050706:31", "egrn_extract"): "ee_fallback"},
    }
    meta = {"cad": "61:44:0050706:31", "kind": "egrn"}
    assert _init.resolve_doc_id(meta, doc_index, "my.jpg") == "ee_artifact"


def test_resolve_doc_id_fallback_to_extract_cad():
    doc_index = {
        "by_artifact_file": {},
        "by_extract_cad": {("61:44:0050706:31", "egrn_extract"): "ee_fallback"},
    }
    meta = {"cad": "61:44:0050706:31", "kind": "egrn"}
    assert _init.resolve_doc_id(meta, doc_index, "unknown.jpg") == "ee_fallback"


def test_resolve_doc_id_returns_none_when_no_match():
    doc_index = {"by_artifact_file": {}, "by_extract_cad": {}}
    meta = {"cad": "61:44:0050706:99", "kind": "egrn"}
    assert _init.resolve_doc_id(meta, doc_index, "x.jpg") is None


# ─── 3. resolve_doc_graph_node_id — формула doc::<doc_id> (v1.1+) ───────────

def test_graph_node_id_doc_takes_priority_over_cad():
    """v1.1+: doc_id даёт `doc::<doc_id>` сильнее cad/inn/ogrn."""
    meta = {"doc_id": "ee_abc123", "cad": "61:44:0050706:31",
            "inn": "7700000001"}
    gidx = {"by_cad_number": {"61:44:0050706:31": "61:44:0050706:31"}}
    assert _init.resolve_doc_graph_node_id(meta, gidx) == "doc::ee_abc123"


def test_graph_node_id_falls_back_to_cad_when_no_doc_id():
    """Backward-compat v1: doc_id отсутствует → стандартный резолв cad."""
    meta = {"cad": "61:44:0050706:31", "inn": "7700000001"}
    gidx = {"by_cad_number": {"61:44:0050706:31": "61:44:0050706:31"}}
    assert _init.resolve_doc_graph_node_id(meta, gidx) == "61:44:0050706:31"


def test_graph_node_id_none_doc_id_does_not_trigger_doc_formula():
    """doc_id = None / отсутствует — НЕ собираем `doc::None`."""
    meta = {"doc_id": None, "inn": "7700000001"}
    gidx = {"by_ben_inn": {"7700000001": "legal::inn::7700000001"}}
    assert _init.resolve_doc_graph_node_id(meta, gidx) == "legal::inn::7700000001"
