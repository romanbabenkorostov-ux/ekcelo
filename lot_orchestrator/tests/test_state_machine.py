"""state_machine: happy path + awaiting_user_input + missing market_analysis."""
from __future__ import annotations

import json

import pytest

from lot_orchestrator.config import Settings
from lot_orchestrator.llm_client import MockClient
from lot_orchestrator.state_machine import Phase, run_pipeline


def test_happy_path(populated_workspace):
    llm = MockClient(
        text=(
            "Финальный отчёт о лоте Пирушин-Центр.\n"
            "<SYSTEM_MARKET_TEMPLATE>\n## Локация\n- центр\n"
            "</SYSTEM_MARKET_TEMPLATE>\n"
            "<!-- MARP_START -->\n"
            "# Slide 1: лот\n"
        )
    )
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    result = run_pipeline(
        workspace_path=populated_workspace,
        lot_id="pirushin_001",
        llm=llm,
        settings=settings,
    )
    assert result.phase == Phase.DONE, result.errors + result.warnings
    assert result.routing is not None
    assert "Финальный отчёт" in result.routing.final_report_path.read_text(encoding="utf-8")
    assert "Slide 1" in result.routing.investment_slides_path.read_text(encoding="utf-8")
    assert result.market_template_path is not None
    assert result.market_template_path.read_text(encoding="utf-8").startswith("## Локация")
    assert result.log_path is not None and result.log_path.exists()
    lines = result.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3  # context + llm + routing


def test_awaiting_user_input_when_no_enrich(tmp_path):
    (tmp_path / "Memorandum" / "_data").mkdir(parents=True)
    (tmp_path / "Memorandum" / "incoming").mkdir(parents=True)
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    result = run_pipeline(
        workspace_path=tmp_path,
        lot_id="pirushin_001",
        llm=MockClient(),
        settings=settings,
    )
    assert result.phase == Phase.AWAITING_USER_INPUT
    assert any("enrich" in w for w in result.warnings)


def test_awaiting_user_input_when_target_scenario_incomplete(
    tmp_path, minimal_enrich_payload
):
    minimal_enrich_payload["target_scenario"] = {"was": "", "trigger": "", "to_plan": ""}
    workspace = tmp_path / "p"
    workspace.mkdir()
    data = workspace / "Memorandum" / "_data"
    incoming = workspace / "Memorandum" / "incoming"
    for d in (data, incoming):
        d.mkdir(parents=True)
    (data / "enrich_pirushin_001.json").write_text(
        json.dumps(minimal_enrich_payload, ensure_ascii=False), encoding="utf-8"
    )
    (incoming / "market_analysis.txt").write_text("x", encoding="utf-8")
    result = run_pipeline(
        workspace_path=workspace,
        lot_id="pirushin_001",
        llm=MockClient(),
        settings=Settings(anthropic_api_key="dummy", auto_yes=True),
    )
    assert result.phase == Phase.AWAITING_USER_INPUT
    assert any("target_scenario" in w for w in result.warnings)


def test_error_when_market_analysis_missing(tmp_path, minimal_enrich_payload):
    workspace = tmp_path / "p"
    workspace.mkdir()
    data = workspace / "Memorandum" / "_data"
    data.mkdir(parents=True)
    (workspace / "Memorandum" / "incoming").mkdir(parents=True)
    (data / "enrich_pirushin_001.json").write_text(
        json.dumps(minimal_enrich_payload, ensure_ascii=False), encoding="utf-8"
    )
    result = run_pipeline(
        workspace_path=workspace,
        lot_id="pirushin_001",
        llm=MockClient(),
        settings=Settings(anthropic_api_key="dummy", auto_yes=True),
    )
    assert result.phase == Phase.ERROR
    assert any("market_analysis" in e for e in result.errors)


def test_no_marp_marker_warns(populated_workspace):
    llm = MockClient(text="Только отчёт без слайдов.")
    settings = Settings(anthropic_api_key="dummy", auto_yes=True)
    result = run_pipeline(
        workspace_path=populated_workspace,
        lot_id="pirushin_001",
        llm=llm,
        settings=settings,
    )
    assert result.phase == Phase.DONE
    assert any("MARP_START" in w for w in result.warnings)
    assert result.routing.investment_slides_path.read_text(encoding="utf-8") == ""
