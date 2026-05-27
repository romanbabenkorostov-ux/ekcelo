# -*- coding: utf-8 -*-
"""Tests для парсера ВТБ-выписки + store/merge на реальном фикстуре."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.rekvizity import canonical, merge as merge_mod, store
from parser.rekvizity.parsers import bank_vtb, detect_parser, doc_parser

FIXTURES = Path(__file__).parent / "fixtures" / "rekvizity"
VTB_DOC = FIXTURES / "vtb_nekso_2026.doc"
VTB_GOLDEN = FIXTURES / "vtb_nekso_2026.golden.json"

pytest.importorskip("olefile")
require_fixture = pytest.mark.skipif(
    not VTB_DOC.exists(), reason=f"fixture not present: {VTB_DOC}"
)


@require_fixture
def test_vtb_parses_all_banking_fields():
    rek = bank_vtb.parse(VTB_DOC)
    assert rek["bank"]["bic"] == "044525411"
    assert rek["bank"]["ks"] == "30101810145250000411"
    assert rek["bank"]["rs"] == "40702810604800001287"
    assert "ВТБ" in rek["bank"]["name"]
    assert rek["inn"] == "7810206482"
    assert rek["kpp"] == "780601001"
    assert rek["ogrn"] == "1027804847278"
    assert rek["signatory"]["fio"] == "Пирушин Вадим Александрович"


@require_fixture
def test_vtb_matches_golden():
    rek = bank_vtb.parse(VTB_DOC)
    golden = json.loads(VTB_GOLDEN.read_text(encoding="utf-8"))
    # Сравниваем без _sources (TS меняется при каждом парсе).
    rek_cmp = {k: v for k, v in rek.items() if not k.startswith("_")}
    assert rek_cmp == golden


@require_fixture
def test_detect_parser_picks_vtb_by_filename():
    fn = detect_parser(VTB_DOC)
    assert fn is bank_vtb.parse


@require_fixture
def test_generic_doc_parser_also_extracts_bank_fields():
    """Generic-парсер должен извлечь те же банковские поля regex'ами,
    т.к. ВТБ-формат использует стандартные ключи К/с, Р/с, БИК.
    """
    rek = doc_parser.parse_generic(VTB_DOC)
    assert rek["bank"]["bic"] == "044525411"
    assert rek["bank"]["ks"] == "30101810145250000411"
    assert rek["bank"]["rs"] == "40702810604800001287"
    assert rek["inn"] == "7810206482"


@require_fixture
def test_store_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("EKCELO_REKVIZITY_ROOT", str(tmp_path / "global"))
    project = tmp_path / "project"
    project.mkdir()

    fragment = bank_vtb.parse(VTB_DOC)
    result = store.save(fragment, project=project)
    assert not result["noop"]
    assert result["inn"] == "7810206482"

    latest = store.load_latest("7810206482")
    assert latest is not None
    assert latest["bank"]["bic"] == "044525411"

    # Локальный snapshot создан.
    local_snapshots = list((project / "Surveycontract" / "rekvizity").glob("*.json"))
    assert len(local_snapshots) == 1


@require_fixture
def test_store_save_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("EKCELO_REKVIZITY_ROOT", str(tmp_path / "global"))

    fragment = bank_vtb.parse(VTB_DOC)
    r1 = store.save(fragment)
    r2 = store.save(bank_vtb.parse(VTB_DOC))
    assert not r1["noop"]
    assert r2["noop"], "Повторный ingest того же файла должен быть no-op"


@require_fixture
def test_merge_priority_keeps_higher_source(tmp_path, monkeypatch):
    """Merge ВТБ-doc + json_manual: для bank.* побеждает ВТБ (выше priority)."""
    monkeypatch.setenv("EKCELO_REKVIZITY_ROOT", str(tmp_path / "global"))

    # Сначала «грузим» manual JSON с устаревшим БИК.
    manual = {
        "inn": "7810206482",
        "bank": {"bic": "999999999", "name": "Старый банк"},
        "_sources": [{
            "type": "json_manual",
            "file": "manual.json",
            "ts": "2020-01-01T00:00:00",
        }],
    }
    store.save(manual)

    # Потом ВТБ-doc — должен перебить bic.
    vtb = bank_vtb.parse(VTB_DOC)
    store.save(vtb)

    latest = store.load_latest("7810206482")
    assert latest["bank"]["bic"] == "044525411"
    assert "ВТБ" in latest["bank"]["name"]
    # История обоих источников сохранена.
    src_types = [s["type"] for s in latest["_sources"]]
    assert "json_manual" in src_types
    assert "doc_bank_vtb" in src_types


def test_canonical_validate_catches_bad_inn():
    rek = canonical.empty_canonical()
    rek["inn"] = "12345"  # слишком короткий
    errs = canonical.validate(rek)
    assert any("inn" in e for e in errs)


def test_canonical_validate_passes_valid():
    rek = canonical.empty_canonical()
    rek["inn"] = "7810206482"
    rek["kpp"] = "780601001"
    rek["ogrn"] = "1027804847278"
    rek["bank"] = {
        "name": "Банк",
        "bic": "044525411",
        "ks": "30101810145250000411",
        "rs": "40702810604800001287",
    }
    assert canonical.validate(rek) == []
