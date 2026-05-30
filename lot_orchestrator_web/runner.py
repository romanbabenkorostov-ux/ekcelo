"""Async-обёртка над `lot_orchestrator.state_machine.run_pipeline` (cycle 5)."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from lot_orchestrator.config import Settings
from lot_orchestrator.llm_client import AnthropicClient, LLMClient, MockClient
from lot_orchestrator.state_machine import run_pipeline
from lot_orchestrator_web.store import Run, RunStore

logger = logging.getLogger(__name__)


def build_llm_client(settings: Settings, *, mock_text: str | None = None) -> LLMClient:
    if mock_text is not None:
        return MockClient(text=mock_text)
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY не задан; используйте mock_text для smoke")
    return AnthropicClient(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        timeout_s=settings.llm_timeout_s,
        retries=settings.llm_retries,
    )


async def execute_run(
    run: Run,
    settings: Settings,
    store: RunStore,
    *,
    llm: LLMClient,
) -> None:
    """Запускается через FastAPI BackgroundTask. Обновляет Run в store."""
    store.update(run.run_id, status="running")
    try:
        result = await asyncio.to_thread(
            run_pipeline,
            workspace_path=run.workspace_path,
            lot_id=run.lot_id,
            llm=llm,
            settings=settings,
        )
        store.update(run.run_id, status="complete", result=result)
    except Exception as exc:
        logger.exception("run %s failed", run.run_id)
        store.update(run.run_id, status="complete", error=f"{type(exc).__name__}: {exc}")


def patch_target_scenario(
    workspace_path: Path, lot_id: str, *, was: str, trigger: str, to_plan: str
) -> bool:
    """Обновляет `target_scenario` в `Memorandum/_data/enrich_<lot_id>.json` идемпотентно.

    Возвращает True если файл существует и был обновлён.
    """
    enrich_path = workspace_path / "Memorandum" / "_data" / f"enrich_{lot_id}.json"
    if not enrich_path.exists():
        return False
    payload = json.loads(enrich_path.read_text(encoding="utf-8"))
    payload["target_scenario"] = {"was": was, "trigger": trigger, "to_plan": to_plan}
    enrich_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True
