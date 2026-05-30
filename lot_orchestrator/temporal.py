"""Темпоральный resolver конфликтов (orchestrator_spec.md §4 Фаза 1.9, §6 Conflict).

Правило: `newer_wins` (свежее `as_of_date`) → при равенстве `registered_wins`
(`evidence_level=1` побеждает `evidence_level=2`).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from lot_orchestrator.schemas import Conflict, Fact


def detect_conflicts(facts: list[Fact]) -> list[Conflict]:
    """Группирует facts по `fact_path`; для групп с ≥2 разными `value` создаёт Conflict с resolution."""
    by_path: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        by_path[f.fact_path].append(f)

    conflicts: list[Conflict] = []
    for path, group in by_path.items():
        if len(group) < 2:
            continue
        values = {_value_key(f.value) for f in group}
        if len(values) < 2:
            continue
        idx, resolution = _resolve(group)
        conflicts.append(Conflict(
            fact_path=path,
            competing_facts=group,
            resolution=resolution,
            winning_fact_index=idx,
        ))
    return conflicts


def _resolve(facts: list[Fact]) -> tuple[int | None, Literal["newer_wins", "registered_wins", "unresolved"]]:
    max_date = max(f.provenance.as_of_date for f in facts)
    newest = [(i, f) for i, f in enumerate(facts) if f.provenance.as_of_date == max_date]
    if len(newest) == 1:
        return newest[0][0], "newer_wins"

    # Tie на дате — registered (level=1) выигрывает над document (level=2).
    registered = [(i, f) for i, f in newest if f.provenance.evidence_level == 1]
    if len(registered) == 1:
        return registered[0][0], "registered_wins"

    return None, "unresolved"


def _value_key(value) -> str:
    """Стабильное представление значения для сравнения (handles dict/list/scalar)."""
    import json
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)
