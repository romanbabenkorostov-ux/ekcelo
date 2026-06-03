"""CRUD по run-сущностям.

Re-export `lot_orchestrator_web.store.{Run, RunStore, get_store}` для
template-совместимости. В шаблоне fastapi/full-stack-fastapi-template
паттерн `app/crud/{entity}.py` с CRUDBase. У нас CRUD упрощённый
(in-memory dict + опц. SQLite snapshot), но семантика та же.
"""
from __future__ import annotations

from lot_orchestrator_web.store import (
    Run,
    RunStore,
    get_store,
    reset_store_for_tests,
)


__all__ = ["Run", "RunStore", "get_store", "reset_store_for_tests"]
