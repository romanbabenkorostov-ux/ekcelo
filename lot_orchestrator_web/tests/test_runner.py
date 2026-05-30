"""runner: build_llm_client + patch_target_scenario edge cases."""
from __future__ import annotations

import json

import pytest

from lot_orchestrator.config import Settings
from lot_orchestrator.llm_client import AnthropicClient, MockClient
from lot_orchestrator_web.runner import build_llm_client, patch_target_scenario


def test_build_llm_client_mock_path():
    settings = Settings()
    llm = build_llm_client(settings, mock_text="x")
    assert isinstance(llm, MockClient)
    assert llm.send("", "").text == "x"


def test_build_llm_client_raises_without_key_and_without_mock():
    settings = Settings(anthropic_api_key="")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_llm_client(settings, mock_text=None)


def test_build_llm_client_real_when_key_present():
    settings = Settings(anthropic_api_key="sk-test", anthropic_model="m1",
                       llm_timeout_s=30, llm_retries=2)
    llm = build_llm_client(settings, mock_text=None)
    assert isinstance(llm, AnthropicClient)


def test_patch_target_scenario_returns_false_when_enrich_missing(tmp_path):
    (tmp_path / "Memorandum" / "_data").mkdir(parents=True)
    updated = patch_target_scenario(
        tmp_path, "absent_lot",
        was="a", trigger="b", to_plan="c",
    )
    assert updated is False


def test_patch_target_scenario_rewrites_existing(tmp_path):
    data = tmp_path / "Memorandum" / "_data"
    data.mkdir(parents=True)
    enrich = data / "enrich_lot_1.json"
    enrich.write_text(json.dumps({
        "schema_version": "1.0",
        "lot_id": "lot_1",
        "target_scenario": {"was": "", "trigger": "", "to_plan": ""},
    }), encoding="utf-8")
    updated = patch_target_scenario(
        tmp_path, "lot_1",
        was="новое was", trigger="новый trigger", to_plan="новый to_plan",
    )
    assert updated is True
    payload = json.loads(enrich.read_text(encoding="utf-8"))
    assert payload["target_scenario"]["was"] == "новое was"
    assert payload["target_scenario"]["to_plan"] == "новый to_plan"
    # Schema_version и lot_id сохранены.
    assert payload["schema_version"] == "1.0"
    assert payload["lot_id"] == "lot_1"
