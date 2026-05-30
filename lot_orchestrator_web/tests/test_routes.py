"""HTTP-уровень: 5 endpoints + index."""
from __future__ import annotations

import json
from pathlib import Path


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Ekcelo Orchestrator" in response.text


def test_run_404_when_workspace_missing(client, tmp_path):
    response = client.post(
        "/lots/x/run",
        json={"workspace_path": str(tmp_path / "absent")},
    )
    assert response.status_code == 400
    assert "не найден" in response.json()["detail"]


def test_full_flow_happy_path(client, populated_workspace):
    # Start.
    start = client.post(
        "/lots/pirushin_001/run",
        json={"workspace_path": str(populated_workspace)},
    )
    assert start.status_code == 202, start.text
    run_id = start.json()["run_id"]

    # Status — TestClient ждёт BackgroundTasks, так что прогон уже завершён.
    status = client.get(f"/lots/pirushin_001/status/{run_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["lot_id"] == "pirushin_001"
    assert body["status"] == "complete"
    assert body["phase"] == "done"

    # Artifacts.
    arts = client.get("/lots/pirushin_001/artifacts")
    assert arts.status_code == 200
    a = arts.json()
    assert a["lot_id"] == "pirushin_001"
    assert a["final_report"] is not None
    assert Path(a["final_report"]).exists()
    assert a["investment_slides"] is not None
    assert a["run_log"] is not None


def test_status_404_for_unknown_run(client):
    response = client.get("/lots/x/status/nonexistent")
    assert response.status_code == 404


def test_artifacts_404_for_lot_without_runs(client):
    response = client.get("/lots/never_ran/artifacts")
    assert response.status_code == 404


def test_needs_input_renders_form(client, populated_workspace):
    # Без runs — форма всё равно рендерится (пустые поля).
    r = client.get("/lots/pirushin_001/needs-input")
    assert r.status_code == 200
    assert "target_scenario" in r.text
    assert "workspace_path" in r.text


def test_provide_input_updates_ssot_and_starts_run(client, populated_workspace):
    response = client.post(
        "/lots/pirushin_001/provide-input",
        data={
            "workspace_path": str(populated_workspace),
            "was": "новое was",
            "trigger": "новый trigger",
            "to_plan": "новый to_plan",
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["updated_ssot"] is True
    assert "run_id" in body

    # SSOT должен содержать новые значения.
    enrich = populated_workspace / "Memorandum" / "_data" / "enrich_pirushin_001.json"
    payload = json.loads(enrich.read_text(encoding="utf-8"))
    assert payload["target_scenario"]["was"] == "новое was"
    assert payload["target_scenario"]["to_plan"] == "новый to_plan"


def test_provide_input_404_when_no_enrich(client, tmp_path):
    workspace = tmp_path / "empty"
    workspace.mkdir()
    (workspace / "Memorandum" / "_data").mkdir(parents=True)
    (workspace / "Memorandum" / "incoming").mkdir(parents=True)
    response = client.post(
        "/lots/x/provide-input",
        data={
            "workspace_path": str(workspace),
            "was": "a", "trigger": "b", "to_plan": "c",
        },
    )
    assert response.status_code == 404


def test_run_request_mock_llm_text_overrides_app_default(client, populated_workspace):
    """Можно подменить mock-текст per-request — пригодится для тонкого smoke."""
    start = client.post(
        "/lots/pirushin_001/run",
        json={
            "workspace_path": str(populated_workspace),
            "mock_llm_text": "Custom report.\n<!-- MARP_START -->\n# Custom slide",
        },
    )
    assert start.status_code == 202
    final_path = (
        populated_workspace / "Memorandum" / "final_report.md"
    )
    assert "Custom report" in final_path.read_text(encoding="utf-8")
