"""Orchestrator — 4-фазный state machine.

Re-export `lot_orchestrator.state_machine.{run_pipeline, OrchestrationResult, Phase}`.
"""
from __future__ import annotations

from lot_orchestrator.state_machine import (
    OrchestrationResult,
    Phase,
    run_pipeline,
)


__all__ = ["OrchestrationResult", "Phase", "run_pipeline"]
