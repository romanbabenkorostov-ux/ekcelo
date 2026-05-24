"""Тесты PR-γ: temporal.py (resolve_state, founder_chain) + report_builder.py."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from egrn_parser.temporal import (
    apply_effect, collect_pledge_holders,
    founder_chain_has_pledge, resolve_state,
)
from utils.report_builder import (
    DocxNativeBuilder, MarkdownBuilder, SourceTracker,
)


# ─── resolve_state — snapshot-overlay (§3.3) ────────────────────────────────


def _fixture_structure() -> dict:
    return {
        "cadastre_objects": [
            {"id": "c1", "cadastral_number": "61:44:0050706:31",
             "restrictions": [{"type": "арест", "since": "2025-12-01"}]},
        ],
    }


def test_resolve_state_no_documents_returns_structure_copy():
    st = _fixture_structure()
    out = resolve_state(st, [], date(2026, 5, 1))
    assert out == st
    assert out is not st  # deepcopy


def test_resolve_state_overlay_removes_arrest():
    docs = [
        {"doc_id": "ee_01", "kind": "egrn_extract", "doc_date": "2026-01-15"},
        {"doc_id": "nr_01", "kind": "notarial_release", "doc_date": "2026-03-01",
         "effects": [{"op": "remove",
                      "target": "cadastre_objects[id=c1].restrictions",
                      "payload": {"type": "арест"}}]},
    ]
    out = resolve_state(_fixture_structure(), docs, date(2026, 3, 15))
    assert out["cadastre_objects"][0]["restrictions"] == []


def test_resolve_state_overlay_absorbed_by_newer_extract():
    docs = [
        {"doc_id": "ee_01", "kind": "egrn_extract", "doc_date": "2026-01-15"},
        {"doc_id": "nr_01", "kind": "notarial_release", "doc_date": "2026-03-01",
         "effects": [{"op": "remove",
                      "target": "cadastre_objects[id=c1].restrictions",
                      "payload": {"type": "арест"}}]},
        {"doc_id": "ee_02", "kind": "egrn_extract", "doc_date": "2026-04-15"},
    ]
    # На 2026-05-01: новая выписка ee_02 поглотила overlay → restrictions
    # из структуры (= base snapshot) сохранились как есть.
    out = resolve_state(_fixture_structure(), docs, date(2026, 5, 1))
    assert out["cadastre_objects"][0]["restrictions"][0]["type"] == "арест"


def test_apply_effect_add_with_source_doc_id():
    state = {"cadastre_objects": [{"id": "c1", "restrictions": []}]}
    apply_effect(state, {
        "op": "add",
        "target": "cadastre_objects[id=c1].restrictions",
        "payload": {"type": "ипотека", "beneficiary_inn": "7700000099"},
    }, source_doc_id="mg_01")
    r = state["cadastre_objects"][0]["restrictions"][0]
    assert r["type"] == "ипотека"
    assert r["_source_doc_id"] == "mg_01"


def test_apply_effect_unknown_target_silent():
    state = {"cadastre_objects": []}
    apply_effect(state, {"op": "remove",
                         "target": "cadastre_objects[id=missing].restrictions",
                         "payload": {}})
    # silently skipped, no exception, no mutation
    assert state == {"cadastre_objects": []}


# ─── founder_chain_has_pledge — §7.2 BFS ────────────────────────────────────


def test_founder_chain_finds_pledge_in_parent():
    bens = {
        "ben_main": {"_kind": "legal", "Бенефициар (ключ)": "ben_holding",
                     "has_pledge": False},
        "ben_holding": {"_kind": "legal", "has_pledge": True,
                        "Обременения доли": [{"Тип обременения": "залог"}]},
    }
    found, path = founder_chain_has_pledge("ben_main", bens)
    assert found is True
    assert path == ["ben_main", "ben_holding"]


def test_founder_chain_no_pledge_returns_false():
    bens = {
        "ben_main": {"_kind": "legal", "Бенефициар (ключ)": "ben_top",
                     "has_pledge": False},
        "ben_top": {"_kind": "legal", "has_pledge": False},
    }
    found, path = founder_chain_has_pledge("ben_main", bens)
    assert found is False
    assert path == []


def test_founder_chain_excludes_pledge_holders():
    """Если в exclude — пропускаем (по требованию пользователя)."""
    bens = {
        "ben_main": {"_kind": "legal", "Бенефициар (ключ)": "ben_bank"},
        "ben_bank": {"_kind": "legal", "has_pledge": True},
    }
    found, _ = founder_chain_has_pledge("ben_main", bens,
                                         exclude_pledge_holders={"ben_bank"})
    assert found is False


def test_founder_chain_safe_with_cycle():
    """Циклы безопасны через visited-set."""
    bens = {
        "a": {"Бенефициар (ключ)": "b"},
        "b": {"Бенефициар (ключ)": "c"},
        "c": {"Бенефициар (ключ)": "a"},  # цикл
    }
    found, _ = founder_chain_has_pledge("a", bens)
    assert found is False  # никто не has_pledge — терминация по visited


def test_collect_pledge_holders_from_both_sources():
    bens = {
        "ben_main": {"attrs": {"ИНН": "6164098765"}},
        "ben_holding": {"attrs": {"ИНН": "7700000001"},
                        "Обременения доли": [{
                            "Сведения о залогодержателе": {"ИНН": "7700000099"},
                        }]},
        "ben_bank": {"attrs": {"ИНН": "7700000099"}},
    }
    cads = [{"id": "c1", "restrictions": [{"beneficiary_inn": "7700000099"}]}]
    holders = collect_pledge_holders(bens, cads)
    assert holders == {"ben_bank"}


# ─── SourceTracker (§10.3) ──────────────────────────────────────────────────


def test_source_tracker_dedup_and_render():
    t = SourceTracker()
    a = t.ref("doc:ee_01", "ЕГРН от 2026-04-15, КН 61:...")
    b = t.ref("doc:ee_01", "duplicate description ignored")
    c = t.ref("doc:nr_01", "Снятие ареста от 2026-03-01")
    assert a == "[^1]" and b == "[^1]" and c == "[^2]"

    block = t.render_block()
    assert "<details>" in block
    assert "[^1]: ЕГРН от 2026-04-15" in block
    assert "[^2]: Снятие ареста от 2026-03-01" in block
    assert "duplicate description ignored" not in block


# ─── MarkdownBuilder ────────────────────────────────────────────────────────


def test_markdown_builder_full_report(tmp_path: Path):
    mb = MarkdownBuilder(title="Тест-отчёт")
    mb.heading("§1. Без залога", level=2)
    mb.table(["Адрес", "КН", "Источник"],
             [["г.Москва", "77:01:001:1", mb.tracker.ref("doc:ee_01",
                                                          "ЕГРН 2026-04-15")]])
    mb.sources_block()
    out = mb.save(tmp_path / "test.md")
    text = out.read_text(encoding="utf-8")
    assert "# Тест-отчёт" in text
    assert "## §1. Без залога" in text
    assert "| Адрес | КН | Источник |" in text
    assert "[^1]" in text
    assert "<details>" in text
    assert "[^1]: ЕГРН 2026-04-15" in text


# ─── DocxNativeBuilder ──────────────────────────────────────────────────────


def test_docx_native_builder_emits_file(tmp_path: Path):
    pytest.importorskip("docx")
    db = DocxNativeBuilder(title="Тест-отчёт DOCX")
    db.heading("§1. Раздел", level=2)
    db.paragraph("Текст параграфа.")
    db.table(["A", "B"], [["1", "2"]], title="Тестовая таблица")
    db.tracker.ref("doc:ee_01", "ЕГРН 2026-04-15")
    db.sources_block()
    out = db.save(tmp_path / "test.docx")
    assert out.exists()
    assert out.stat().st_size > 1000  # валидный DOCX > 1KB

    # Открыть docx обратно, проверить что содержит heading'и
    from docx import Document  # type: ignore[import]
    d = Document(str(out))
    texts = [p.text for p in d.paragraphs]
    assert "Тест-отчёт DOCX" in texts
    assert "§1. Раздел" in texts
    assert "Текст параграфа." in texts
    assert any("Источники" in t for t in texts)
