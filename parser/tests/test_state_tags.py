"""Тесты PR-η: state_tags.py — namespaces + validation + resolve + ingester."""
from __future__ import annotations

from datetime import date

import pytest

from egrn_parser.state_tags import (
    NAMESPACES, collect_tags_from_documents,
    resolve_active_tags, validate_state_tag,
)


# ─── NAMESPACES ─────────────────────────────────────────────────────────────


def test_namespaces_present():
    assert "legal_state" in NAMESPACES
    assert "physical_state" in NAMESPACES
    assert "руинировано" in NAMESPACES["physical_state"]
    assert "признан_аварийным" in NAMESPACES["legal_state"]


# ─── validate_state_tag ─────────────────────────────────────────────────────


def test_validate_tag_ok():
    validate_state_tag({"namespace": "legal_state",
                        "value": "введён_в_эксплуатацию"})
    validate_state_tag({"namespace": "physical_state",
                        "value": "руинировано", "since": "2024-01-15"})


def test_validate_tag_rejects_bad_namespace():
    with pytest.raises(ValueError, match="namespace должен быть"):
        validate_state_tag({"namespace": "wat", "value": "x"})


def test_validate_tag_rejects_empty_value():
    with pytest.raises(ValueError, match="value должен быть"):
        validate_state_tag({"namespace": "legal_state", "value": ""})


def test_validate_tag_rejects_bad_date():
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        validate_state_tag({"namespace": "legal_state",
                            "value": "x", "since": "01.01.2024"})


def test_validate_strict_values_rejects_unknown():
    """strict_values=True проверяет values против whitelist."""
    with pytest.raises(ValueError, match="не в whitelist"):
        validate_state_tag(
            {"namespace": "physical_state", "value": "не_в_списке"},
            strict_values=True,
        )


# ─── resolve_active_tags ────────────────────────────────────────────────────


def test_resolve_active_tags_window():
    tags = [
        {"namespace": "physical_state", "value": "хорошее",
         "since": "2023-01-01", "until": "2024-06-01"},
        {"namespace": "physical_state", "value": "руинировано",
         "since": "2024-06-01"},
        {"namespace": "legal_state", "value": "признан_аварийным",
         "since": "2024-08-01"},
    ]
    # 2024-03-01: только "хорошее" действует
    active = resolve_active_tags(tags, date(2024, 3, 1))
    assert {t["value"] for t in active} == {"хорошее"}
    # 2024-07-01: "руинировано" (без until) — да; "признан_аварийным" — нет (since 08-01)
    active = resolve_active_tags(tags, date(2024, 7, 1))
    assert {t["value"] for t in active} == {"руинировано"}
    # 2024-09-01: оба
    active = resolve_active_tags(tags, date(2024, 9, 1))
    assert {t["value"] for t in active} == {"руинировано", "признан_аварийным"}


def test_resolve_skips_invalid_tags():
    """Поломанные теги silently skipped (без всего набора)."""
    tags = [
        {"namespace": "legal_state", "value": "признан_аварийным"},  # OK
        {"namespace": "BAD", "value": "x"},                          # skip
        "not even a dict",                                            # skip
    ]
    active = resolve_active_tags(tags, date(2024, 9, 1))
    assert len(active) == 1
    assert active[0]["value"] == "признан_аварийным"


# ─── collect_tags_from_documents (ручной ingester) ──────────────────────────


def test_collect_tags_from_documents():
    documents = [
        {"doc_id": "cd_1", "kind": "court_decision",
         "doc_date": "2024-08-15",
         "effects": [{
             "op": "add",
             "target": "cadastre_objects[id=c1].state_tags",
             "payload": {"namespace": "legal_state",
                         "value": "признан_аварийным"},
         }]},
        {"doc_id": "ot_1", "kind": "other",
         "doc_date": "2024-07-01",
         "effects": [{
             "op": "add",
             "target": "cadastre_objects[id=c1].state_tags",
             "payload": {"namespace": "physical_state",
                         "value": "руинировано"},
         }]},
        # Не должен попасть: doc_date > target_date
        {"doc_id": "cd_2", "kind": "court_decision",
         "doc_date": "2026-01-01",
         "effects": [{
             "op": "add",
             "target": "cadastre_objects[id=c1].state_tags",
             "payload": {"namespace": "legal_state",
                         "value": "сертификат_отозван"},
         }]},
    ]
    tags_by_cad = collect_tags_from_documents(documents, date(2024, 12, 31))
    assert "c1" in tags_by_cad
    values = {t["value"] for t in tags_by_cad["c1"]}
    assert values == {"признан_аварийным", "руинировано"}
    # source_doc_id и since прокинуты
    aw = next(t for t in tags_by_cad["c1"] if t["value"] == "признан_аварийным")
    assert aw["source_doc_id"] == "cd_1"
    assert aw["since"] == "2024-08-15"


def test_collect_skips_non_state_tag_effects():
    """Effects на другие targets не подхватываются."""
    documents = [{
        "doc_id": "nr_1", "kind": "notarial_release", "doc_date": "2024-01-01",
        "effects": [{
            "op": "remove",
            "target": "cadastre_objects[id=c1].restrictions",
            "payload": {"type": "арест"},
        }],
    }]
    assert collect_tags_from_documents(documents, date(2025, 1, 1)) == {}
