"""serve.py — foolproof launcher для backend.

Решает 3 проблемы, на которые наступают пользователи:

1. **`ModuleNotFoundError: No module named 'backend'`** при `uvicorn backend.app.main:app`.
   uvicorn запускается из своей `Scripts/`-папки venv и НЕ добавляет
   текущий каталог в `sys.path`. С `--reload` это ещё хуже: подпроцесс
   reloader тоже не наследует sys.path-модификации, сделанные родителем.

   Этот лаунчер выставляет `PYTHONPATH=<repo_root>` через env-переменную,
   которая корректно пробрасывается в reloader-подпроцесс.

2. **Venv из чужого проекта**. Пользователь активировал `.venv` из
   соседней папки — пакеты другие, импорт `lot_orchestrator_web` падает.
   Перед запуском напоминаем явно создать venv в корне клона.

3. **`uvicorn` не установлен**. Лаунчер ловит `ImportError` и пишет
   понятную инструкцию по установке.

Usage:
    python serve.py                       # порт 8000, reload включён
    python serve.py --port 9000           # кастомный порт
    python serve.py --no-reload           # без авто-рестарта
    python serve.py --host 0.0.0.0        # listen на всех интерфейсах

Эквивалент:
    uvicorn --app-dir . backend.app.main:app --reload
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _ensure_pythonpath()
    _warn_if_foreign_venv()

    try:
        import uvicorn
    except ImportError:
        print(_install_hint(), file=sys.stderr)
        return 3

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=[str(REPO_ROOT)] if not args.no_reload else None,
        log_level=args.log_level,
    )
    return 0


def _ensure_pythonpath() -> None:
    """Кладёт repo_root в PYTHONPATH (через env), чтобы reloader-подпроцесс видел `backend.*`."""
    existing = os.environ.get("PYTHONPATH", "")
    repo_str = str(REPO_ROOT)
    parts = existing.split(os.pathsep) if existing else []
    if repo_str not in parts:
        parts.insert(0, repo_str)
        os.environ["PYTHONPATH"] = os.pathsep.join(parts)
    # Дублируем в sys.path для текущего процесса (чтобы import работал
    # ещё до запуска uvicorn — например, для проверки импортов).
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def _warn_if_foreign_venv() -> None:
    """Если active venv лежит вне корня репо — предупреждаем."""
    venv = os.environ.get("VIRTUAL_ENV")
    if not venv:
        return
    try:
        venv_path = Path(venv).resolve()
    except OSError:
        return
    if REPO_ROOT in venv_path.parents or venv_path == REPO_ROOT:
        return
    print(
        f"WARNING: активный venv находится вне корня репо:\n"
        f"  venv:      {venv_path}\n"
        f"  repo_root: {REPO_ROOT}\n"
        f"Это может привести к ModuleNotFoundError для backend / lot_orchestrator*\n"
        f"Рекомендуется создать venv в корне клона:\n"
        f"  cd {REPO_ROOT}\n"
        f"  python -m venv .venv\n"
        f"  .venv\\Scripts\\Activate.ps1   # Windows\n"
        f"  source .venv/bin/activate     # Linux/macOS\n",
        file=sys.stderr,
    )


def _install_hint() -> str:
    return (
        "error: uvicorn не установлен в текущем окружении.\n\n"
        "Если venv ещё не создан:\n"
        f"  cd {REPO_ROOT}\n"
        "  python -m venv .venv\n"
        "  .\\.venv\\Scripts\\Activate.ps1   # Windows PowerShell\n"
        "  source .venv/bin/activate         # Linux/macOS\n\n"
        "Установка зависимостей backend:\n"
        "  pip install fastapi \"uvicorn[standard]\" jinja2 python-multipart "
        "httpx2 pydantic anthropic pyyaml pymorphy3 pymorphy3-dicts-ru\n\n"
        "Затем повторно: python serve.py"
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python serve.py",
        description="Foolproof launcher для backend (FastAPI / lot_orchestrator_web).",
    )
    p.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    p.add_argument("--port", type=int, default=8000, help="default: 8000")
    p.add_argument("--no-reload", action="store_true",
                   help="Отключить авто-рестарт при изменении файлов.")
    p.add_argument("--log-level", default="info",
                   choices=["critical", "error", "warning", "info", "debug", "trace"])
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
