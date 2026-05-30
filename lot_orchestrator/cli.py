"""CLI entrypoint: `python -m lot_orchestrator.cli`.

Usage:
    python -m lot_orchestrator.cli \\
        --workspace D:/ОБЪЕКТЫ/pirushin \\
        --lot pirushin_001 \\
        [--mock-llm "MOCK_TEXT" | --dry-run]

Без `--mock-llm` и `--dry-run` требует env `ANTHROPIC_API_KEY`.

Exit codes:
    0 — DONE
    2 — AWAITING_USER_INPUT (нет SSOT / неполный target_scenario)
    3 — ERROR (validation / отсутствие обязательного входа)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lot_orchestrator.config import Settings
from lot_orchestrator.llm_client import AnthropicClient, MockClient
from lot_orchestrator.state_machine import OrchestrationResult, Phase, run_pipeline


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = Settings.from_env()

    if args.dry_run:
        llm = MockClient(text="[dry-run] LLM не вызывался.\n")
    elif args.mock_llm is not None:
        llm = MockClient(text=args.mock_llm)
    else:
        if not settings.anthropic_api_key:
            print("error: ANTHROPIC_API_KEY не задан. Используйте --dry-run или --mock-llm.",
                  file=sys.stderr)
            return 3
        llm = AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout_s=settings.llm_timeout_s,
            retries=settings.llm_retries,
        )

    result = run_pipeline(
        workspace_path=Path(args.workspace),
        lot_id=args.lot,
        llm=llm,
        settings=settings,
    )
    _report(result)
    return _exit_code(result.phase)


def _report(result: OrchestrationResult) -> None:
    print(f"phase: {result.phase.value}")
    print(f"lot_id: {result.lot_id}")
    if result.workspace:
        print(f"memorandum: {result.workspace.memorandum}")
    if result.routing:
        print(f"final_report: {result.routing.final_report_path}")
        print(f"investment_slides: {result.routing.investment_slides_path}")
    if result.market_template_path:
        print(f"market_template: {result.market_template_path}")
    for w in result.warnings:
        print(f"WARN: {w}", file=sys.stderr)
    for e in result.errors:
        print(f"ERROR: {e}", file=sys.stderr)


def _exit_code(phase: Phase) -> int:
    return {
        Phase.DONE: 0,
        Phase.AWAITING_USER_INPUT: 2,
        Phase.ERROR: 3,
    }.get(phase, 1)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m lot_orchestrator.cli",
        description="Orchestrator MVP: 4-phase memorandum pipeline.",
    )
    p.add_argument("--workspace", required=True, help="Путь к рабочей папке лота.")
    p.add_argument("--lot", required=True, help="lot_id (regex [A-Za-z0-9_:-]+).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--mock-llm", help="Использовать MockClient с заданным текстом (для smoke).")
    g.add_argument("--dry-run", action="store_true",
                   help="Не вызывать LLM, отметить mock-вызов и выйти после Phase 4.")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
