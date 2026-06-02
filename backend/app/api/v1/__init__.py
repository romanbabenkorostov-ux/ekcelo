"""API v1 — текущая версия. Routes уже зарегистрированы в `lot_orchestrator_web.main:app`.

В шаблоне fastapi/full-stack-fastapi-template обычно живут как
`app/api/v1/{endpoint}.py` с APIRouter каждый. У нас все 6 endpoints
зарегистрированы внутри `_register_routes(app)` в `main.py`. Этот файл
держим как точку расширения для разделения на router'ы при будущем cycle.
"""
