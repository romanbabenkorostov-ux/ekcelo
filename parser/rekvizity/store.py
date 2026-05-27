# -*- coding: utf-8 -*-
"""Хранилище реквизитов: глобальный (~/.ekcelo/rekvizity/<ИНН>/) +
локальный snapshot (<project>/Surveycontract/rekvizity/<ИНН>_<datetime>.json).

Идемпотентность: повторный ingest того же файла с теми же значениями —
no-op (новый snapshot не создаётся, только `latest.json` остаётся
последним).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from . import canonical, merge as merge_mod


def global_root() -> Path:
    """Корень глобального store. По умолчанию `~/.ekcelo/rekvizity/`.
    Override через `EKCELO_REKVIZITY_ROOT`.
    """
    override = os.environ.get("EKCELO_REKVIZITY_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ekcelo" / "rekvizity"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_latest(inn: str) -> dict | None:
    """Возвращает последний canonical для ИНН из глобального store, или None."""
    p = global_root() / inn / "latest.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def save(
    fragment: dict, *, project: Path | None = None, force: bool = False
) -> dict:
    """Слить fragment в существующий canonical для inn и сохранить.

    Возвращает словарь:
      {
        "inn": str,
        "global_path": str,    # путь к новому snapshot'у
        "latest_path": str,    # путь к latest.json
        "local_path": str | None,  # snapshot в проекте (если project передан)
        "noop": bool,          # True если ничего не изменилось
        "errors": list[str],   # ошибки валидации (если есть)
      }
    """
    inn = fragment.get("inn")
    if not inn:
        return {"inn": None, "noop": True, "errors": ["fragment без inn"]}

    existing = load_latest(inn)
    if existing and not force and merge_mod.is_noop(existing, fragment):
        return {
            "inn": inn,
            "global_path": None,
            "latest_path": str(global_root() / inn / "latest.json"),
            "local_path": None,
            "noop": True,
            "errors": [],
        }

    merged = merge_mod.merge(existing or {}, fragment)
    errors = canonical.validate(merged)

    # Глобальный snapshot.
    g_dir = global_root() / inn
    g_dir.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    g_path = g_dir / f"{ts}.json"
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    g_path.write_text(payload, encoding="utf-8")
    latest = g_dir / "latest.json"
    latest.write_text(payload, encoding="utf-8")

    # Локальный snapshot (если есть project).
    local_path: Path | None = None
    if project is not None:
        local_dir = project / "Surveycontract" / "rekvizity"
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / f"{inn}_{ts}.json"
        local_path.write_text(payload, encoding="utf-8")

    return {
        "inn": inn,
        "global_path": str(g_path),
        "latest_path": str(latest),
        "local_path": str(local_path) if local_path else None,
        "noop": False,
        "errors": errors,
    }


def list_known(*, project: Path | None = None) -> list[str]:
    """Список ИНН из глобального store (+ при необходимости из локального проекта)."""
    seen: list[str] = []
    g_root = global_root()
    if g_root.is_dir():
        for entry in g_root.iterdir():
            if entry.is_dir() and (entry / "latest.json").exists():
                seen.append(entry.name)
    if project:
        local_dir = project / "Surveycontract" / "rekvizity"
        if local_dir.is_dir():
            for f in local_dir.glob("*.json"):
                inn = f.stem.split("_", 1)[0]
                if inn not in seen:
                    seen.append(inn)
    return seen
