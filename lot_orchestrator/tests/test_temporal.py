"""Темпоральный resolver: newer > registered > document_date."""
from __future__ import annotations

from datetime import date

from lot_orchestrator.schemas import Fact, Provenance
from lot_orchestrator.temporal import detect_conflicts


def _fact(path: str, value, doc_id: str, d: date, level: int) -> Fact:
    return Fact(
        fact_path=path,
        value=value,
        provenance=Provenance(document_id=doc_id, as_of_date=d, evidence_level=level),
    )


def test_no_conflict_when_single_value():
    facts = [
        _fact("x", 100.0, "d1", date(2026, 1, 1), 1),
        _fact("x", 100.0, "d2", date(2026, 2, 1), 1),
    ]
    assert detect_conflicts(facts) == []


def test_newer_wins():
    facts = [
        _fact("x", 100.0, "d1", date(2026, 1, 1), 1),
        _fact("x", 200.0, "d2", date(2026, 5, 1), 1),
    ]
    conflicts = detect_conflicts(facts)
    assert len(conflicts) == 1
    assert conflicts[0].resolution == "newer_wins"
    assert conflicts[0].winning_fact_index == 1


def test_registered_wins_on_date_tie():
    facts = [
        _fact("x", 100.0, "d1", date(2026, 5, 1), 2),  # document_date
        _fact("x", 200.0, "d2", date(2026, 5, 1), 1),  # registered_date
    ]
    conflicts = detect_conflicts(facts)
    assert conflicts[0].resolution == "registered_wins"
    assert conflicts[0].winning_fact_index == 1


def test_unresolved_when_two_registered_on_same_date():
    facts = [
        _fact("x", 100.0, "d1", date(2026, 5, 1), 1),
        _fact("x", 200.0, "d2", date(2026, 5, 1), 1),
    ]
    conflicts = detect_conflicts(facts)
    assert conflicts[0].resolution == "unresolved"
    assert conflicts[0].winning_fact_index is None


def test_independent_paths_are_independent():
    facts = [
        _fact("x", 1, "d1", date(2026, 1, 1), 1),
        _fact("x", 2, "d2", date(2026, 2, 1), 1),
        _fact("y", 3, "d3", date(2026, 1, 1), 1),
    ]
    conflicts = detect_conflicts(facts)
    assert len(conflicts) == 1
    assert conflicts[0].fact_path == "x"
