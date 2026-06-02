"""Settings — re-export `lot_orchestrator.config.Settings`.

В шаблоне fastapi/full-stack-fastapi-template `app/core/config.py`
содержит `pydantic_settings.BaseSettings`. У нас — обычный dataclass
с `.from_env()`. Семантика та же, поведение совместимо.
"""
from __future__ import annotations

from lot_orchestrator.config import Settings


__all__ = ["Settings"]
