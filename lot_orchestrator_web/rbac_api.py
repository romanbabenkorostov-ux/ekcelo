"""RBAC FastAPI integration (cycle 15, M3).

Связывает rbac-ядро (M1) + SQLiteGrantStore (M2) с HTTP-слоем:
- `get_principal(request)` — извлекает `Principal` из `request.state.subject`
  (cycle 14 OAuth) ИЛИ anonymous-principal.
- `require_action(action, resource_type, id_param)` — фабрика FastAPI-
  dependency для защиты роутов. **Opt-in**: если `grant_store` не
  сконфигурирован — пропускает (backward-compat).
- `register_grant_routes(app)` — добавляет `POST /grants`,
  `DELETE /grants/{grant_id}`, `GET /grants/me`.

ВАЖНО: M3 НЕ навешивает enforcement на существующие роуты (`/catalog`,
`/objects/{cad}` и т.д.) — это M4 (потребует opt-in флага + миграции тестов).
M3 даёт инструменты + endpoints управления грантами. Существующие 425 тестов
не затрагиваются.

См. также:
- `lot_orchestrator_web/rbac.py` (M1 ядро).
- `lot_orchestrator_web/rbac_store.py` (M2 SQLite).
- `obsidian/Architecture/cycle-15-rbac.md` (M1+M2+M3 снимок).
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from lot_orchestrator_web.rbac import (
    Action,
    AuthorizationError,
    Grant,
    GrantStore,
    Principal,
    Resource,
    ResourceType,
    Role,
    can,
    delegate,
    share,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Principal extraction
# ─────────────────────────────────────────────────────────────────────────────

def get_principal(request: Request) -> Principal:
    """Извлекает Principal из `request.state.subject` (cycle 14 OAuth).

    Если subject отсутствует (no-auth / Basic Auth без roles-карты) — возвращает
    anonymous Principal (sub="", roles пусто). Downstream `require_action`
    решает что делать с anonymous (обычно — 403 при сконфигурированном store).
    """
    subject = getattr(request.state, "subject", None)
    if subject is None:
        return Principal(sub="", roles=frozenset())
    return Principal.from_oauth_subject(subject)


def _get_store(request: Request) -> GrantStore | None:
    return getattr(request.app.state, "grant_store", None)


# ─────────────────────────────────────────────────────────────────────────────
#  Dependency factory (для M4 wire-up)
# ─────────────────────────────────────────────────────────────────────────────

def require_action(
    action: Action,
    resource_type: ResourceType,
    id_param: str,
) -> Callable:
    """Фабрика FastAPI-dependency: проверяет право `action` над ресурсом.

    `id_param` — имя path-параметра, содержащего resource_id (например "cad",
    "lot_id", "bundle_id").

    Opt-in семантика:
    - Если `app.state.grant_store is None` → пропускает (enforcement выключен).
    - Иначе извлекает Principal, строит Resource из path-параметра, проверяет
      `can(...)`. Отказ → 403.

    Использование (M4):
        @app.get("/objects/{cad}",
                 dependencies=[Depends(require_action(Action.VIEW,
                                       ResourceType.OBJECT, "cad"))])
    """
    async def _dependency(request: Request) -> None:
        store = _get_store(request)
        if store is None:
            return  # enforcement не сконфигурирован — open (backward-compat)
        principal = get_principal(request)
        resource_id = request.path_params.get(id_param)
        if resource_id is None:
            raise HTTPException(
                status_code=500,
                detail=f"require_action: path-параметр '{id_param}' не найден",
            )
        resource = Resource(resource_type, str(resource_id))
        if not can(principal, action, resource, store):
            raise HTTPException(
                status_code=403,
                detail=f"{principal.sub or 'anonymous'} cannot "
                       f"{action.value} {resource_type.value}/{resource_id}",
            )

    return _dependency


# ─────────────────────────────────────────────────────────────────────────────
#  Cycle 15 M5 — фильтр каталога по VIEW-грантам
# ─────────────────────────────────────────────────────────────────────────────

_CARD_KIND_TO_RESOURCE: dict[str, ResourceType] = {
    "object": ResourceType.OBJECT,
    "lot": ResourceType.LOT,
}


def filter_catalog_by_grants(
    cards: Iterable[Any],
    principal: Principal,
    store: GrantStore,
) -> list[Any]:
    """Оставляет карточки, для которых у `principal` есть VIEW-грант.

    Карточка имеет атрибуты `kind` ("object" | "lot") и `id`. superadmin
    минует фильтр (см. `can`). Неизвестный `kind` → отбрасываем (явно безопаснее).
    """
    out: list[Any] = []
    for card in cards:
        rtype = _CARD_KIND_TO_RESOURCE.get(card.kind)
        if rtype is None:
            continue
        if can(principal, Action.VIEW, Resource(rtype, card.id), store):
            out.append(card)
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Grant management REST schemas
# ─────────────────────────────────────────────────────────────────────────────

class GrantCreateRequest(BaseModel):
    subject_sub: str = Field(..., description="Кому выдаётся грант.")
    action: Action
    resource_type: ResourceType
    resource_id: str
    expires_at: datetime | None = None


class GrantResponse(BaseModel):
    grant_id: str
    subject_sub: str
    action: str
    resource_type: str
    resource_id: str
    granted_by: str
    revocable: bool
    expires_at: datetime | None = None

    @classmethod
    def from_grant(cls, g: Grant) -> "GrantResponse":
        return cls(
            grant_id=g.grant_id,
            subject_sub=g.subject_sub,
            action=g.action.value,
            resource_type=g.resource.type.value,
            resource_id=g.resource.id,
            granted_by=g.granted_by,
            revocable=g.revocable,
            expires_at=g.expires_at,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────────────────────────────────────

def register_grant_routes(app: FastAPI) -> None:
    """Регистрирует REST-эндпоинты управления грантами.

    Все требуют сконфигурированного `grant_store` (иначе 503).
    """

    def _require_store(request: Request) -> GrantStore:
        store = _get_store(request)
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="grant_store не сконфигурирован (env EKCELO_ACCESS_DB пуст)",
            )
        return store

    @app.post("/grants", status_code=201)
    async def create_grant(
        body: GrantCreateRequest,
        request: Request,
    ) -> GrantResponse:
        """Выдать грант. Caller (Principal) должен иметь право выдавать.

        Семантика по C6:
        - assessor/superadmin → `delegate` (передача action-права).
        - client/superadmin + action=view → `share` (view-only третьему лицу).
        - Иначе 403.
        """
        store = _require_store(request)
        principal = get_principal(request)
        resource = Resource(body.resource_type, body.resource_id)

        try:
            if body.action == Action.VIEW and principal.has_any(
                Role.CLIENT
            ) and not principal.has_any(Role.ASSESSOR, Role.SUPERADMIN):
                # client расшаривает view
                grant_id = share(
                    sharer=principal, recipient_sub=body.subject_sub,
                    resource=resource, store=store,
                    expires_at=body.expires_at,
                )
            else:
                # assessor/superadmin делегируют action
                grant_id = delegate(
                    grantor=principal, grantee_sub=body.subject_sub,
                    action=body.action, resource=resource, store=store,
                    expires_at=body.expires_at,
                )
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        created = store.get(grant_id)
        assert created is not None
        return GrantResponse.from_grant(created)

    @app.delete("/grants/{grant_id}", status_code=204)
    async def revoke_grant(
        grant_id: str,
        request: Request,
    ) -> None:
        """Отозвать грант. Caller должен быть granted_by или superadmin."""
        store = _require_store(request)
        principal = get_principal(request)

        target = store.get(grant_id)
        if target is None:
            raise HTTPException(status_code=404, detail=f"грант {grant_id} не найден")

        if not (principal.has_any(Role.SUPERADMIN)
                or principal.sub == target.granted_by):
            raise HTTPException(
                status_code=403,
                detail="отзыв доступен только автору гранта или superadmin",
            )
        if not store.revoke(grant_id):
            raise HTTPException(
                status_code=409,
                detail="грант не может быть отозван (non-revocable)",
            )

    @app.get("/grants/me")
    async def my_grants(request: Request) -> list[GrantResponse]:
        """Список грантов текущего Principal."""
        store = _require_store(request)
        principal = get_principal(request)
        return [
            GrantResponse.from_grant(g)
            for g in store.list_for_subject(principal.sub)
        ]
