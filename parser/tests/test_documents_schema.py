"""Тесты documents.json schema/validator (PR-β, dev/SPEC_TEMPORAL_REPORTS.md §4)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from egrn_parser.documents_schema import (
    EXTRACT_KINDS, KIND_PREFIXES, load_documents,
    parse_date, validate_documents_json,
)


# ─── parse_date ─────────────────────────────────────────────────────────────

def test_parse_date_iso_ok():
    assert parse_date("2026-04-15") == date(2026, 4, 15)


@pytest.mark.parametrize("bad", ["15.04.2026", "2026-4-15", "", None, "2026/04/15"])
def test_parse_date_rejects_non_iso(bad):
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        parse_date(bad)


# ─── validate_documents_json — happy path ───────────────────────────────────

def test_validate_empty_documents():
    assert validate_documents_json({}) == []
    assert validate_documents_json({"documents": None}) == []
    assert validate_documents_json({"documents": []}) == []


def test_validate_full_fixture():
    data = {
        "schema_version": "1.0",
        "project_slug": "test",
        "documents": [
            {"doc_id": "ee_abc12345", "kind": "egrn_extract",
             "doc_date": "2026-04-15",
             "subjects": {"cadastrals": ["61:44:0050706:31"]},
             "effects": [],
             "artifacts": [{"file": "docs/x.jpg", "page_count": 8,
                            "external_url": "https://disk.yandex.ru/i/a"}]},
            {"doc_id": "nr_xy567890", "kind": "notarial_release",
             "doc_date": "2026-03-01",
             "subjects": {"cadastrals": ["61:44:0050706:31"]},
             "effects": [{"op": "remove",
                          "target": "cadastre_objects[id=c2].restrictions",
                          "payload": {"type": "арест"}}]},
        ],
    }
    docs = validate_documents_json(data)
    assert len(docs) == 2
    assert docs[0]["doc_id"] == "ee_abc12345"


def test_validate_tolerates_unknown_fields():
    """Forward-compat: незнакомые поля не валятся."""
    data = {"documents": [{
        "doc_id": "ee_a1", "kind": "egrn_extract", "doc_date": "2026-04-15",
        "notes": "freeform", "future_field_xyz": {"any": "data"},
    }]}
    docs = validate_documents_json(data)
    assert docs[0]["future_field_xyz"] == {"any": "data"}


# ─── validate_documents_json — rejection ────────────────────────────────────

def test_validate_rejects_doc_id_kind_mismatch():
    data = {"documents": [{
        "doc_id": "ee_x1", "kind": "purchase",  # ee_ префикс не соответствует purchase
        "doc_date": "2026-04-15",
    }]}
    with pytest.raises(ValueError, match="должен начинаться с 'pc_'"):
        validate_documents_json(data)


def test_validate_rejects_unknown_kind():
    data = {"documents": [{
        "doc_id": "xx_a1", "kind": "wat",
        "doc_date": "2026-04-15",
    }]}
    with pytest.raises(ValueError, match="kind.*должен быть"):
        validate_documents_json(data)


def test_validate_rejects_bad_doc_id_format():
    data = {"documents": [{
        "doc_id": "ee-abc", "kind": "egrn_extract",  # дефис вместо underscore
        "doc_date": "2026-04-15",
    }]}
    with pytest.raises(ValueError, match=r"\[a-z\]\+_\[A-Za-z0-9\]\+"):
        validate_documents_json(data)


def test_validate_rejects_bad_doc_date():
    data = {"documents": [{
        "doc_id": "ee_a1", "kind": "egrn_extract",
        "doc_date": "15-04-2026",
    }]}
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        validate_documents_json(data)


def test_validate_rejects_bad_effect_op():
    data = {"documents": [{
        "doc_id": "nr_a1", "kind": "notarial_release",
        "doc_date": "2026-03-01",
        "effects": [{"op": "DROP_TABLE", "target": "x"}],
    }]}
    with pytest.raises(ValueError, match="op должен быть"):
        validate_documents_json(data)


# ─── load_documents (filesystem) ────────────────────────────────────────────

def test_load_documents_returns_empty_when_missing(tmp_path: Path):
    assert load_documents(tmp_path) == []


def test_load_documents_returns_parsed(tmp_path: Path):
    data = {"documents": [{
        "doc_id": "ee_a1b2c3d4", "kind": "egrn_extract",
        "doc_date": "2026-04-15",
    }]}
    (tmp_path / "_data").mkdir()
    (tmp_path / "_data" / "documents.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    docs = load_documents(tmp_path)
    assert len(docs) == 1 and docs[0]["doc_id"] == "ee_a1b2c3d4"


# ─── Константы ──────────────────────────────────────────────────────────────

def test_extract_kinds_constants():
    assert EXTRACT_KINDS == frozenset({"egrn_extract", "egrul_extract", "egrip_extract"})


def test_kind_prefixes_uniqueness():
    """Каждый префикс уникален — иначе ambiguity при resolve."""
    prefixes = list(KIND_PREFIXES.values())
    assert len(prefixes) == len(set(prefixes))
