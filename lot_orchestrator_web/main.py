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
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
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
from lot_orchestrator_web.store import (
    Run,
    RunStore,
    configure_redis_store,
    configure_store,
    get_store,
)


_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=_HERE / "templates")


def create_app(
    *,
    settings: Settings | None = None,
    mock_llm_text: str | None = None,
    persistence_db: Path | None = None,
    ekcelo_db: Path | None = None,
    redis_client=None,
    auth_users: str | None = None,
) -> FastAPI:
    """Factory: Settings + persistence + опциональный Redis + опциональный Basic Auth.

    auth_users — формат `user1:pass1,user2:pass2`. Если None, читается из env
    `EKCELO_AUTH_USERS`; если и там пусто — auth не подключается.

    ekcelo_db — путь к ekcelo.sqlite (БД §1..§6) для ViewModel-эндпоинтов
    (`/catalog`, `/objects/{cad}`). Если None — читается из env `EKCELO_DB`;
    если и там пусто — эндпоинты отвечают 503.
    """
    import os
    from lot_orchestrator_web.auth import maybe_install_basic_auth

    app = FastAPI(
        title="Ekcelo Orchestrator",
        description="Memorandum pipeline web-UI (FastAPI cycle 5/8/9/11/12).",
        version="0.4.0",
    )
    app.state.settings = settings or Settings.from_env()
    app.state.mock_llm_text = mock_llm_text
    env_db = os.environ.get("EKCELO_DB")
    app.state.ekcelo_db = ekcelo_db or (Path(env_db) if env_db else None)
    persistence = SQLitePersistence(persistence_db) if persistence_db else None
    if redis_client is not None:
        configure_redis_store(redis_client, persistence=persistence)
    elif persistence is not None:
        configure_store(persistence)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    _register_routes(app)
    # Auth middleware последним — оборачивает все routes (включая `/`).
    maybe_install_basic_auth(app, raw_users_env=auth_users)
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

    @app.post("/bundles/import")
    async def import_bundle_endpoint(
        bundle_zip: Annotated[UploadFile, File(description="ZIP-архив Bundle (C3).")],
        target_db: Annotated[str, Form(description="Путь к ekcelo.sqlite на сервере.")],
        verify_hashes: Annotated[bool, Form()] = True,
        dry_run: Annotated[bool, Form()] = False,
    ) -> JSONResponse:
        """Идемпотентный импорт Bundle (C3) — multipart-upload zip.

        Реализует `contracts/api/openapi.yaml::/bundles/import`. Распаковывает
        zip во временный каталог, валидирует manifest по C3, выполняет
        идемпотентный upsert через `backend.app.services.bundle.import_bundle`.
        Повтор того же Bundle = no-op.
        """
        import tempfile
        import zipfile

        from backend.app.services.bundle import import_bundle as _import

        if not bundle_zip.filename or not bundle_zip.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Ожидается .zip-архив Bundle")

        with tempfile.TemporaryDirectory(prefix="ekcelo-bundle-") as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "bundle.zip"
            with zip_path.open("wb") as fh:
                fh.write(await bundle_zip.read())
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(tmp_path / "extracted")
            except zipfile.BadZipFile as exc:
                raise HTTPException(status_code=400,
                                    detail=f"Битый zip: {exc}") from exc
            bundle_root = _find_bundle_root(tmp_path / "extracted")
            if bundle_root is None:
                raise HTTPException(
                    status_code=400,
                    detail="В архиве не найден manifest.json",
                )
            try:
                report = _import(
                    bundle_root, Path(target_db),
                    verify_hashes=verify_hashes, dry_run=dry_run,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = {
            "is_noop": report.is_noop,
            "objects_inserted": report.objects_inserted,
            "objects_updated": report.objects_updated,
            "objects_skipped_identical": report.objects_skipped_identical,
            "entities_inserted": report.entities_inserted,
            "rights_inserted": report.rights_inserted,
            "etp_profiles_inserted": report.etp_profiles_inserted,
            "etp_profiles_skipped_authoritative":
                report.etp_profiles_skipped_authoritative,
            "files_verified": report.files_verified,
            "files_failed": report.files_failed,
            "warnings": report.warnings,
            "errors": report.errors,
        }
        if report.errors or report.files_failed:
            return JSONResponse(status_code=422, content=payload)
        return JSONResponse(status_code=200, content=payload)

    @app.get("/catalog")
    async def catalog_endpoint(
        q: str | None = None,
        kind: str | None = None,
    ) -> JSONResponse:
        """Список карточек объектов/лотов (`openapi.yaml::/catalog`).

        Источник — `EKCELO_DB` (или `ekcelo_db=` в `create_app`).
        """
        from backend.app.services.viewmodel import build_catalog

        db = _require_ekcelo_db(app)
        if kind not in (None, "object", "lot"):
            raise HTTPException(
                status_code=422,
                detail="kind должен быть 'object' либо 'lot'",
            )
        cards = build_catalog(db, q=q, kind=kind)  # type: ignore[arg-type]
        return JSONResponse(
            content=[c.model_dump(exclude_none=True) for c in cards]
        )

    @app.get("/objects/{cad}")
    async def object_viewmodel_endpoint(
        cad: str,
        as_of: str | None = None,
    ) -> JSONResponse:
        """ViewModel объекта (`openapi.yaml::/objects/{cad}`).

        4 канонические характеристики physical/ownership/geo/temporal.
        """
        from backend.app.services.viewmodel import (
            ObjectNotFound,
            build_object_viewmodel,
        )

        db = _require_ekcelo_db(app)
        try:
            vm = build_object_viewmodel(db, cad, as_of=as_of)
        except ObjectNotFound:
            raise HTTPException(
                status_code=404,
                detail=f"объект {cad} не найден",
            ) from None
        return JSONResponse(content=vm.model_dump(exclude_none=False))

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


def _require_ekcelo_db(app: FastAPI) -> Path:
    """Достать сконфигурированный ekcelo_db или 503 если не задан."""
    db = getattr(app.state, "ekcelo_db", None)
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="ekcelo_db не сконфигурирован (env EKCELO_DB пуст)",
        )
    if not Path(db).exists():
        raise HTTPException(
            status_code=503,
            detail=f"ekcelo_db не найден: {db}",
        )
    return Path(db)


def _find_bundle_root(extracted: Path) -> Path | None:
    """Найти каталог с manifest.json в распакованном архиве.

    Поддерживает 2 формы: archive/manifest.json или archive/<single-subdir>/manifest.json.
    """
    if (extracted / "manifest.json").is_file():
        return extracted
    children = [p for p in extracted.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "manifest.json").is_file():
        return children[0]
    return None


def _str_if_exists(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path) if path.exists() else None


async def _sse_phase_changes(
    store, lot_id: str, run_id: str,
    *,
    poll_interval_s: float = 0.2,
    timeout_s: float = 300.0,
):
    """Cycle 11: pub/sub при RedisRunStore (instant), polling — fallback.

    Гибрид: если у store есть `subscribe_events` (RedisRunStore) — используем
    Redis pub/sub без задержки 200ms. Иначе — старый polling-режим.
    """
    if hasattr(store, "subscribe_events"):
        async for event in _sse_via_pubsub(store, lot_id, run_id, timeout_s=timeout_s):
            yield event
        return
    async for event in _sse_via_polling(
        store, lot_id, run_id,
        poll_interval_s=poll_interval_s, timeout_s=timeout_s,
    ):
        yield event


async def _sse_via_polling(
    store, lot_id: str, run_id: str,
    *,
    poll_interval_s: float = 0.2,
    timeout_s: float = 300.0,
):
    """Polling-based SSE (fallback при in-memory/SQLite-only store)."""
    import asyncio

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


async def _sse_via_pubsub(
    store, lot_id: str, run_id: str,
    *,
    timeout_s: float = 300.0,
    drain_interval_s: float = 0.05,
):
    """Cycle 11: Redis pub/sub SSE — мгновенные phase updates без 200ms polling.

    Подписываемся на `ekcelo:events:<run_id>`, парсим сообщения, эмитим SSE.
    На запуске эмитим текущее состояние (initial snapshot) — клиент сразу видит phase.
    """
    import asyncio
    import json as _json

    # Initial snapshot — клиент сразу получает текущий phase, не ждёт next event.
    run = store.get(run_id)
    if run is None or run.lot_id != lot_id:
        yield _sse_event("error", {"detail": f"run {run_id} не найден"})
        return
    yield _sse_event("phase", {
        "run_id": run_id,
        "status": run.status,
        "phase": run.phase,
        "warnings": run.warnings,
        "errors": run.errors,
    })
    if run.status == "complete":
        yield _sse_event("done", {"run_id": run_id, "phase": run.phase})
        return

    ps = store.subscribe_events(run_id)
    last_phase = run.phase
    elapsed = 0.0
    try:
        while elapsed < timeout_s:
            msg = await asyncio.to_thread(ps.get_message, ignore_subscribe_messages=True, timeout=drain_interval_s)
            elapsed += drain_interval_s
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            raw = msg["data"]
            if isinstance(raw, bytes):
                raw = raw.decode()
            try:
                payload = _json.loads(raw)
            except (TypeError, ValueError):
                continue
            if payload.get("phase") != last_phase:
                yield _sse_event("phase", payload)
                last_phase = payload["phase"]
            if payload.get("status") == "complete":
                yield _sse_event("done", {"run_id": run_id, "phase": payload["phase"]})
                return
        yield _sse_event("timeout", {"run_id": run_id, "elapsed_s": elapsed})
    finally:
        try:
            ps.close()
        except Exception:
            pass


def _sse_event(event_name: str, data: dict) -> str:
    import json as _json
    return f"event: {event_name}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


def _build_app_from_env() -> FastAPI:
    """Reads `EKCELO_PERSISTENCE_DB` / `EKCELO_REDIS_URL` env vars set by cli.py."""
    persistence_db_env = os.getenv("EKCELO_PERSISTENCE_DB")
    redis_url_env = os.getenv("EKCELO_REDIS_URL")
    redis_client = None
    if redis_url_env:
        from lot_orchestrator_web.redis_store import make_redis_client
        redis_client = make_redis_client(redis_url_env)
    return create_app(
        persistence_db=Path(persistence_db_env) if persistence_db_env else None,
        redis_client=redis_client,
    )


# `os` нужен здесь — добавим импорт в верх файла лениво (см. ниже).
import os  # noqa: E402

app = _build_app_from_env()
