"""Оркестрация 4 фаз (orchestrator_spec.md §4)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from lot_orchestrator.config import Settings
from lot_orchestrator.inputs_finder import find_canonical_or_recursive
from lot_orchestrator.llm_client import LLMClient
from lot_orchestrator.prompts import build_prompts
from lot_orchestrator.response_handler import extract_and_write_market_template
from lot_orchestrator.router import RoutingResult, route_outputs
from lot_orchestrator.schemas import AssetData
from lot_orchestrator.temporal import detect_conflicts
from lot_orchestrator.workspace import WorkspaceLayout, init_workspace


class Phase(str, Enum):
    VALIDATING = "validating"
    AWAITING_USER_INPUT = "awaiting_user_input"
    CONTEXT_INJECTION = "context_injection"
    LLM_RUNNING = "llm_running"
    ROUTING = "routing"
    DONE = "done"
    ERROR = "error"


@dataclass
class OrchestrationResult:
    phase: Phase
    lot_id: str
    workspace: WorkspaceLayout | None = None
    asset_data: AssetData | None = None
    routing: RoutingResult | None = None
    market_template_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    log_path: Path | None = None


def run_pipeline(
    *,
    workspace_path: Path,
    lot_id: str,
    llm: LLMClient,
    settings: Settings,
) -> OrchestrationResult:
    """Прогон всех 4 фаз. На AWAITING_USER_INPUT — ранний возврат с состоянием."""
    result = OrchestrationResult(phase=Phase.VALIDATING, lot_id=lot_id)
    try:
        layout = init_workspace(
            workspace_path,
            fuzzy_threshold=settings.fuzzy_match_threshold,
            auto_yes=settings.auto_yes,
        )
        result.workspace = layout
        result.log_path = layout.data / "_run_log.jsonl"

        # Phase 1: validation.
        asset_data = _load_or_complain(layout, lot_id, result)
        if asset_data is None:
            return result
        result.asset_data = asset_data

        if not asset_data.target_scenario.is_complete():
            result.phase = Phase.AWAITING_USER_INPUT
            result.warnings.append("target_scenario неполный: was/trigger/to_plan обязательны")
            _log(result, "phase", phase=result.phase.value, reason="target_scenario incomplete")
            return result

        # Конфликты обновляются автоматически при каждом прогоне.
        asset_data.conflicts = detect_conflicts(asset_data.facts_index)

        market_analysis = _read_required(
            layout, "market_analysis.txt", r"^market_analysis.*\.txt$", result
        )
        if market_analysis is None:
            return result

        # graph.html — опционально.
        graph_found = find_canonical_or_recursive(
            layout.root, layout.graph_canonical.relative_to(layout.root), r"^graph\.html$"
        )
        graph_status = graph_found is not None
        if graph_found and graph_found.source == "recursive":
            try:
                layout.graph_canonical.write_bytes(graph_found.path.read_bytes())
            except OSError as exc:
                result.warnings.append(f"копирование graph.html: {exc}")

        # market_template.md — опционально, если есть, передаётся LLM как контекст.
        mt_found = find_canonical_or_recursive(
            layout.root, layout.market_template_canonical.relative_to(layout.root),
            r"^market_template.*\.md$",
        )
        existing_market_template = mt_found.path.read_text(encoding="utf-8") if mt_found else ""

        # Phase 2: context injection.
        result.phase = Phase.CONTEXT_INJECTION
        enrich_text = asset_data.model_dump_json(indent=2)
        bundle = build_prompts(
            settings.prompts_path,
            enrich_json_text=enrich_text,
            market_analysis=market_analysis,
            existing_market_template=existing_market_template,
            graph_status=graph_status,
        )
        _log(
            result,
            "context",
            phase=result.phase.value,
            system_sha256=_sha(bundle.system),
            user_sha256=_sha(bundle.user),
            user_len=len(bundle.user),
            system_len=len(bundle.system),
        )

        # Phase 3: LLM call.
        result.phase = Phase.LLM_RUNNING
        response = llm.send(bundle.system, bundle.user)
        _log(
            result,
            "llm",
            phase=result.phase.value,
            model=response.model,
            response_len=len(response.text),
            usage=response.usage,
        )

        extraction = extract_and_write_market_template(
            response.text, layout.market_template_canonical
        )
        if extraction.template_written:
            result.market_template_path = extraction.template_path
        elif extraction.warning:
            result.warnings.append(extraction.warning)

        # Phase 4: routing.
        result.phase = Phase.ROUTING
        routing = route_outputs(extraction.cleaned_response, layout.memorandum)
        result.routing = routing
        if routing.warning:
            result.warnings.append(routing.warning)
        _log(
            result,
            "routing",
            phase=result.phase.value,
            final_report=str(routing.final_report_path.name),
            investment_slides=str(routing.investment_slides_path.name),
        )

        result.phase = Phase.DONE
        return result
    except FileNotFoundError as exc:
        result.errors.append(str(exc))
        result.phase = Phase.ERROR
        return result


def _load_or_complain(
    layout: WorkspaceLayout, lot_id: str, result: OrchestrationResult
) -> AssetData | None:
    enrich_path = layout.enrich_path(lot_id)
    if not enrich_path.exists():
        result.phase = Phase.AWAITING_USER_INPUT
        result.warnings.append(
            f"enrich_{lot_id}.json не найден в {layout.data}. "
            "Запустите Этап 1 (intake) для генерации SSOT."
        )
        return None
    try:
        raw = json.loads(enrich_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.errors.append(f"enrich JSON parse: {exc}")
        result.phase = Phase.ERROR
        return None
    try:
        return AssetData.model_validate(raw)
    except ValidationError as exc:
        result.errors.append(f"enrich JSON validation: {exc}")
        result.phase = Phase.ERROR
        return None


def _read_required(
    layout: WorkspaceLayout, canonical_name: str, pattern: str, result: OrchestrationResult
) -> str | None:
    found = find_canonical_or_recursive(
        layout.root, Path("Memorandum") / "incoming" / canonical_name, pattern
    )
    if found is None:
        result.errors.append(
            f"обязательный вход '{canonical_name}' не найден ни в "
            f"Memorandum/incoming/, ни рекурсивно по '{pattern}'"
        )
        result.phase = Phase.ERROR
        return None
    return found.path.read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _log(result: OrchestrationResult, event: str, **fields: Any) -> None:
    if result.log_path is None:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    try:
        with result.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
