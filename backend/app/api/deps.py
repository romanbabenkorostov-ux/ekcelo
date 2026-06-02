"""FastAPI dependency-injection точки.

Re-export DI-helpers из `lot_orchestrator_web.store`. В шаблоне
fastapi/full-stack-fastapi-template принято `app/api/deps.py`.
"""
from __future__ import annotations

from lot_orchestrator_web.store import get_store, reset_store_for_tests


__all__ = ["get_store", "reset_store_for_tests"]
