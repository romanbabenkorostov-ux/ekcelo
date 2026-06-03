"""FastAPI app entrypoint (template-aligned).

Re-export `lot_orchestrator_web.main:app` для совместимости с шаблоном
`fastapi/full-stack-fastapi-template`, где принято `backend/app/main.py`.

Использование:
    uvicorn backend.app.main:app --reload
    # эквивалентно:
    uvicorn lot_orchestrator_web.main:app --reload

Console script `ekcelo-orchestrate-web` (после merge PR #92) использует
`lot_orchestrator_web.main:app` напрямую.
"""
from __future__ import annotations

from lot_orchestrator_web.main import app, create_app


__all__ = ["app", "create_app"]
