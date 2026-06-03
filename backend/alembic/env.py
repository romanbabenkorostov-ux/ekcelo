"""Alembic env.py — stub.

В этом репо Alembic НЕ активен. См. `obsidian/Decisions/ADR-003-temporal-v2-ownership.md`
тема 4 (DB-миграция deferred до adoption SQLModel/Alembic).

Этот файл — placeholder для шаблон-совместимости layout'а под
fastapi/full-stack-fastapi-template. При активации (если пользователь
одобрит миграцию) — здесь будет канонический `run_migrations_offline()` /
`run_migrations_online()`. Сейчас pass — `alembic upgrade head` дать
ничего не сможет (нет target_metadata).
"""
from __future__ import annotations

# При активации:
# from logging.config import fileConfig
# from alembic import context
# from sqlmodel import SQLModel
# from backend.app.models import schemas
# config = context.config
# fileConfig(config.config_file_name)
# target_metadata = SQLModel.metadata
# ... run_migrations_online() ...

# Текущий статус — stub, для линтеров чтобы файл импортировался.
target_metadata = None
