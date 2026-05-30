"""FastAPI app — orchestrator web-UI (cycle 5).

API (orchestrator_spec.md §5):
    POST /lots/{lot_id}/run               — стартует прогон, 202 {run_id}
    GET  /lots/{lot_id}/status/{run_id}   — статус (JSON)
    GET  /lots/{lot_id}/needs-input       — HTML-форма для target_scenario
    POST /lots/{lot_id}/provide-input     — приём form-data, перезапуск
    GET  /lots/{lot_id}/artifacts         — список артефактов (JSON)

Запуск:
    uvicorn lot_orchestrator_web.main:app --reload
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from lot_orchestrator.config import Settings
from lot_orchestrator_web.persistence import SQLitePersistence
from lot_orchestrator_web.runner import (
    build_llm_client,
    execute_run,
    patch_target_scenario,
)
from lot_orchestrator_web.store import Run, RunStore, configure_store, get_store


_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=_HERE / "templates")


def create_app(
    *,
    settings: Settings | None = None,
    mock_llm_text: str | None = None,
    persistence_db: Path | None = None,
) -> FastAPI:
    """Factory чтобы тесты могли передать свой Settings / mock_llm_text / persistence."""
    app = FastAPI(
        title="Ekcelo Orchestrator",
        description="Memorandum pipeline web-UI (FastAPI cycle 5/8).",
        version="0.2.0",
    )
    app.state.settings = settings or Settings.from_env()
    app.state.mock_llm_text = mock_llm_text
    if persistence_db is not None:
        configure_store(SQLitePersistence(persistence_db))
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    _register_routes(app)
    return app


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    workspace_path: str = Field(..., description="Абсолютный путь к рабочей папке лота.")
    mock_llm_text: str | None = Field(
        default=None,
        description="Если задано — LLM не вызывается, используется MockClient.",
    )


class RunCreated(BaseModel):
    run_id: str
    lot_id: str


class StatusResponse(BaseModel):
    run_id: str
    lot_id: str
    status: str
    phase: str
    warnings: list[str] = []
    errors: list[str] = []


class ArtifactsResponse(BaseModel):
    lot_id: str
    memorandum: str | None = None
    final_report: str | None = None
    investment_slides: str | None = None
    market_template: str | None = None
    run_log: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

def _register_routes(app: FastAPI) -> None:

    @app.post(
        "/lots/{lot_id}/run",
        response_model=RunCreated,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_run(
        lot_id: str,
        body: RunRequest,
        bg: BackgroundTasks,
        store: Annotated[RunStore, Depends(get_store)],
    ) -> RunCreated:
        workspace = Path(body.workspace_path)
        if not workspace.exists():
            raise HTTPException(
                status_code=400,
                detail=f"workspace_path не найден: {workspace}",
            )
        mock_text = body.mock_llm_text if body.mock_llm_text is not None else app.state.mock_llm_text
        try:
            llm = build_llm_client(app.state.settings, mock_text=mock_text)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        run = store.create(lot_id, workspace)
        bg.add_task(execute_run, run, app.state.settings, store, llm=llm)
        return RunCreated(run_id=run.run_id, lot_id=lot_id)

    @app.get("/lots/{lot_id}/status/{run_id}", response_model=StatusResponse)
    async def get_status(
        lot_id: str,
        run_id: str,
        store: Annotated[RunStore, Depends(get_store)],
    ) -> StatusResponse:
        run = store.get(run_id)
        if run is None or run.lot_id != lot_id:
            raise HTTPException(status_code=404, detail=f"run {run_id} не найден")
        return _build_status(run, store)

    @app.get("/lots/{lot_id}/needs-input", response_class=HTMLResponse)
    async def needs_input(
        request: Request,
        lot_id: str,
        store: Annotated[RunStore, Depends(get_store)],
    ) -> HTMLResponse:
        run = store.latest_for_lot(lot_id)
        target = None
        if run is not None and run.result is not None and run.result.asset_data is not None:
            target = run.result.asset_data.target_scenario
        return templates.TemplateResponse(
            request,
            "needs_input.html",
            {
                "lot_id": lot_id,
                "run": run,
                "target": target,
            },
        )

    @app.post("/lots/{lot_id}/provide-input")
    async def provide_input(
        lot_id: str,
        bg: BackgroundTasks,
        store: Annotated[RunStore, Depends(get_store)],
        workspace_path: Annotated[str, Form()],
        was: Annotated[str, Form()],
        trigger: Annotated[str, Form()],
        to_plan: Annotated[str, Form()],
    ) -> JSONResponse:
        workspace = Path(workspace_path)
        if not workspace.exists():
            raise HTTPException(status_code=400, detail=f"workspace_path не найден: {workspace}")
        updated = patch_target_scenario(
            workspace, lot_id, was=was, trigger=trigger, to_plan=to_plan
        )
        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"enrich_{lot_id}.json не найден в Memorandum/_data/",
            )
        try:
            llm = build_llm_client(app.state.settings, mock_text=app.state.mock_llm_text)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run = store.create(lot_id, workspace)
        bg.add_task(execute_run, run, app.state.settings, store, llm=llm)
        return JSONResponse(
            status_code=202,
            content={"run_id": run.run_id, "lot_id": lot_id, "updated_ssot": True},
        )

    @app.get("/lots/{lot_id}/artifacts", response_model=ArtifactsResponse)
    async def get_artifacts(
        lot_id: str,
        store: Annotated[RunStore, Depends(get_store)],
    ) -> ArtifactsResponse:
        run = store.latest_for_lot(lot_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail=f"для лота {lot_id} нет завершённых прогонов",
            )
        # Cycle 8: артефакты подбираются GLOB'ом из workspace_path/Memorandum/.
        # Это переживает рестарт даже если result потерян.
        return _build_artifacts(lot_id, run.workspace_path)

    @app.get("/lots/{lot_id}/stream/{run_id}")
    async def stream_status(
        lot_id: str,
        run_id: str,
        store: Annotated[RunStore, Depends(get_store)],
    ) -> StreamingResponse:
        """Server-Sent Events для статуса прогона (cycle 8).

        Эмитит `event: phase\\ndata: <json>\\n\\n` при смене phase.
        Закрывается при status='complete' или после 5 минут.
        """
        return StreamingResponse(
            _sse_phase_changes(store, lot_id, run_id),
            media_type="text/event-stream",
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", {})


def _build_status(run: Run, store: RunStore) -> StatusResponse:
    return StatusResponse(
        run_id=run.run_id,
        lot_id=run.lot_id,
        status=run.status,
        phase=run.phase,
        warnings=run.warnings,
        errors=run.errors,
    )


def _build_artifacts(lot_id: str, workspace_path: Path) -> ArtifactsResponse:
    """GLOB-подбор артефактов из `workspace_path/Memorandum/`.

    Работает даже после рестарта (когда in-memory result потерян).
    """
    memo = workspace_path / "Memorandum"
    if not memo.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Memorandum/ не найден в {workspace_path}",
        )
    return ArtifactsResponse(
        lot_id=lot_id,
        memorandum=str(memo),
        final_report=_str_if_exists(memo / "final_report.md"),
        investment_slides=_str_if_exists(memo / "investment_slides.md"),
        market_template=_str_if_exists(memo / "market_template.md"),
        run_log=_str_if_exists(memo / "_data" / "_run_log.jsonl"),
    )


def _str_if_exists(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path) if path.exists() else None


async def _sse_phase_changes(
    store: RunStore, lot_id: str, run_id: str,
    *,
    poll_interval_s: float = 0.2,
    timeout_s: float = 300.0,
):
    """Polling-based SSE: эмитит при каждом изменении phase.

    Не использует cross-thread asyncio.Queue — execute_run работает в потоке,
    polling гарантирует читаемость без race condition.
    """
    import asyncio
    import json as _json

    last_phase: str | None = None
    elapsed = 0.0
    while elapsed < timeout_s:
        run = store.get(run_id)
        if run is None or run.lot_id != lot_id:
            yield _sse_event("error", {"detail": f"run {run_id} не найден"})
            return
        if run.phase != last_phase:
            yield _sse_event("phase", {
                "run_id": run_id,
                "status": run.status,
                "phase": run.phase,
                "warnings": run.warnings,
                "errors": run.errors,
            })
            last_phase = run.phase
        if run.status == "complete":
            yield _sse_event("done", {"run_id": run_id, "phase": run.phase})
            return
        await asyncio.sleep(poll_interval_s)
        elapsed += poll_interval_s
    yield _sse_event("timeout", {"run_id": run_id, "elapsed_s": elapsed})


def _sse_event(event_name: str, data: dict) -> str:
    import json as _json
    return f"event: {event_name}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


app = create_app()
