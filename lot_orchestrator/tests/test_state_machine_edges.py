"""state_machine: error paths + graph.html recursive copy (coverage boost)."""
from __future__ import annotations

import json

from lot_orchestrator.config import Settings
from lot_orchestrator.llm_client import MockClient
from lot_orchestrator.state_machine import Phase, run_pipeline


def test_error_when_enrich_json_invalid(tmp_path):
    workspace = tmp_path / "p"
    workspace.mkdir()
    data = workspace / "Memorandum" / "_data"
    data.mkdir(parents=True)
    (workspace / "Memorandum" / "incoming").mkdir(parents=True)
    (data / "enrich_lot1.json").write_text("this is not json {{{",
                                            encoding="utf-8")
    result = run_pipeline(
        workspace_path=workspace,
        lot_id="lot1",
        llm=MockClient(),
        settings=Settings(anthropic_api_key="x", auto_yes=True),
    )
    assert result.phase == Phase.ERROR
    assert any("enrich JSON parse" in e for e in result.errors)


def test_error_when_enrich_fails_pydantic_validation(tmp_path):
    workspace = tmp_path / "p"
    workspace.mkdir()
    data = workspace / "Memorandum" / "_data"
    data.mkdir(parents=True)
    (workspace / "Memorandum" / "incoming").mkdir(parents=True)
    (data / "enrich_lot1.json").write_text(json.dumps({
        "schema_version": "1.0",
        "lot_id": "lot1",
        "generated_at": "not-a-date",  # ValidationError
    }), encoding="utf-8")
    result = run_pipeline(
        workspace_path=workspace,
        lot_id="lot1",
        llm=MockClient(),
        settings=Settings(anthropic_api_key="x", auto_yes=True),
    )
    assert result.phase == Phase.ERROR
    assert any("enrich JSON validation" in e for e in result.errors)


def test_graph_html_copied_from_recursive_location(tmp_path, minimal_enrich_payload):
    """`graph.html` глубоко в дереве копируется в canonical Memorandum/."""
    root = tmp_path / "project"
    root.mkdir()
    data = root / "Memorandum" / "_data"
    incoming = root / "Memorandum" / "incoming"
    deep = root / "deep" / "level"
    for d in (data, incoming, deep):
        d.mkdir(parents=True)
    (data / "enrich_pirushin_001.json").write_text(
        json.dumps(minimal_enrich_payload, ensure_ascii=False), encoding="utf-8"
    )
    (incoming / "market_analysis.txt").write_text("market", encoding="utf-8")
    (deep / "graph.html").write_bytes(b"<html>graph</html>")

    result = run_pipeline(
        workspace_path=root,
        lot_id="pirushin_001",
        llm=MockClient(text="report\n<!-- MARP_START -->\n# Slide"),
        settings=Settings(anthropic_api_key="x", auto_yes=True),
    )
    assert result.phase == Phase.DONE
    canonical_graph = root / "Memorandum" / "graph.html"
    assert canonical_graph.exists()
    assert canonical_graph.read_bytes() == b"<html>graph</html>"
