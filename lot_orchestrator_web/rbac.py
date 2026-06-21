"""RBAC (cycle 15, M1) — реализация `contracts/roles/ROLES_SPEC.md` (C6).

Per-lot/object/bundle разграничение доступа поверх `Subject` (cycle 14).
M1: in-memory ядро (Principal, Grant, GrantStore, can). M2: SQLite persistence
+ миграция. M3: FastAPI `Depends(require(...))` + `POST/DELETE /grants`.

Архитектура:

    JWT claims (cycle 14 OAuth) ─┐
                                  ├─► Principal(sub, roles)
    Basic Auth static map ────────┘
                                  │
                                  ▼
                         can(principal, action, resource, store) → bool
                                  ▲
    ┌─ GrantStore ─────────────────┘
    │ in-memory (M1, для тестов/dev)
    │ SQLite access_grants (M2)
    └──────────────────────────────

Семантика (по C6):
- **superadmin** в `principal.roles` → True всегда (минует проверки).
- **assessor**: view/edit/export/input/delegate — только при наличии гранта;
  может делегировать другому assessor.
- **client**: только view/export/share, edit/input запрещён без исключений.

См. также:
- `contracts/roles/ROLES_SPEC.md` (C6) — нормативный контракт ролей.
- `lot_orchestrator_web/oauth.py` (cycle 14) — источник Principal.
- `obsidian/Architecture/cycle-14-oauth.md` (предшественник).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Protocol


# ─────────────────────────────────────────────────────────────────────────────
#  Контрактные enums (C6)
# ─────────────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    SUPERADMIN = "superadmin"
    ASSESSOR = "assessor"
    CLIENT = "client"


class Action(str, Enum):
    INPUT = "input"      # прямой ввод данных
    EDIT = "edit"        # правка §6 ЭТП-профиля
    VIEW = "view"        # просмотр ViewModel
    EXPORT = "export"    # скачивание Bundle/части
    DELEGATE = "delegate"  # передача прав другому assessor
    SHARE = "share"      # share-token третьему лицу (client only)


class ResourceType(str, Enum):
    LOT = "lot"
    OBJECT = "object"
    BUNDLE = "bundle"


# ─────────────────────────────────────────────────────────────────────────────
#  Доменные модели
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Resource:
    """Ссылка на конкретный объект доступа."""
    type: ResourceType
    id: str


@dataclass(frozen=True)
class Principal:
    """Активный субъект — связка sub + множество ролей.

    Несколько ролей одновременно (например assessor + superadmin) — разрешено.
    Создаётся из oauth.Subject или статической карты для Basic Auth.
    """
    sub: str
    roles: frozenset[Role] = field(default_factory=frozenset)

    @classmethod
    def from_oauth_subject(cls, subject: Any) -> "Principal":
        """Адаптер: oauth.Subject → rbac.Principal.

        Игнорирует строки в `subject.roles`, которые не входят в `Role` enum,
        чтобы кастомные роли из JWT не валили процесс.
        """
        valid: set[Role] = set()
        for raw in getattr(subject, "roles", ()):
            try:
                valid.add(Role(raw))
            except ValueError:
                continue
        return cls(sub=str(getattr(subject, "sub", "")), roles=frozenset(valid))

    def has_any(self, *roles: Role) -> bool:
        return any(r in self.roles for r in roles)


@dataclass(frozen=True)
class Grant:
    """Scoped-грант. Создаётся `granted_by`-субъектом, может отзываться.

    `expires_at` — опц. TTL (для share-токенов). UTC.
    """
    subject_sub: str
    action: Action
    resource: Resource
    granted_by: str
    revocable: bool = True
    expires_at: datetime | None = None
    grant_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ─────────────────────────────────────────────────────────────────────────────
#  Grant storage protocol
# ─────────────────────────────────────────────────────────────────────────────

class GrantStore(Protocol):
    """Интерфейс хранилища грантов. M2 даст SQLite-реализацию."""

    def add(self, grant: Grant) -> str: ...
    def revoke(self, grant_id: str) -> bool: ...
    def find(
        self,
        subject_sub: str,
        action: Action,
        resource: Resource,
    ) -> Grant | None: ...
    def list_for_subject(self, subject_sub: str) -> list[Grant]: ...
    def get(self, grant_id: str) -> Grant | None: ...


class InMemoryGrantStore:
    """Простое dict-хранилище для тестов/dev. Не thread-safe (FastAPI single-worker)."""

    def __init__(self) -> None:
        self._by_id: dict[str, Grant] = {}

    def add(self, grant: Grant) -> str:
        self._by_id[grant.grant_id] = grant
        return grant.grant_id

    def revoke(self, grant_id: str) -> bool:
        g = self._by_id.get(grant_id)
        if g is None:
            return False
        if not g.revocable:
            return False
        del self._by_id[grant_id]
        return True

    def find(
        self,
        subject_sub: str,
        action: Action,
        resource: Resource,
    ) -> Grant | None:
        for g in self._by_id.values():
            if (g.subject_sub == subject_sub
                    and g.action == action
                    and g.resource == resource):
                return g
        return None

    def list_for_subject(self, subject_sub: str) -> list[Grant]:
        return [g for g in self._by_id.values() if g.subject_sub == subject_sub]

    def get(self, grant_id: str) -> Grant | None:
        return self._by_id.get(grant_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Авторизация
# ─────────────────────────────────────────────────────────────────────────────

# Жёсткие запреты по роли (C6: client read-only).
_CLIENT_DENIED: frozenset[Action] = frozenset({
    Action.INPUT, Action.EDIT, Action.DELEGATE,
})


class AuthorizationError(Exception):
    """Принципал не имеет права выполнить действие."""


def can(
    principal: Principal,
    action: Action,
    resource: Resource,
    store: GrantStore,
    *,
    now: datetime | None = None,
) -> bool:
    """Главная проверка: может ли `principal` выполнить `action` над `resource`.

    Алгоритм:
    1. superadmin → True (минует всё).
    2. client → запрещены input/edit/delegate (C6 read-only).
    3. assessor c view-grant — может export/view; для edit/input нужен явный
       грант этого action.
    4. Иначе ищем активный (не истёкший) грант (subject, action, resource).
    """
    if Role.SUPERADMIN in principal.roles:
        return True

    # client read-only enforcement
    if principal.has_any(Role.CLIENT) and not principal.has_any(Role.ASSESSOR):
        if action in _CLIENT_DENIED:
            return False

    grant = store.find(principal.sub, action, resource)
    if grant is None:
        return False
    if _is_expired(grant, now=now):
        return False
    return True


def require(
    principal: Principal,
    action: Action,
    resource: Resource,
    store: GrantStore,
    *,
    now: datetime | None = None,
) -> None:
    """Императивная версия `can` — кидает `AuthorizationError` при отказе.

    Используется в эндпоинтах через FastAPI `Depends(...)` в M3.
    """
    if not can(principal, action, resource, store, now=now):
        raise AuthorizationError(
            f"{principal.sub} cannot {action.value} {resource.type.value}/{resource.id}"
        )


def _is_expired(grant: Grant, *, now: datetime | None) -> bool:
    if grant.expires_at is None:
        return False
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    exp = grant.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return moment >= exp


# ─────────────────────────────────────────────────────────────────────────────
#  Делегирование и шеринг (high-level helpers)
# ─────────────────────────────────────────────────────────────────────────────

def delegate(
    *,
    grantor: Principal,
    grantee_sub: str,
    action: Action,
    resource: Resource,
    store: GrantStore,
    expires_at: datetime | None = None,
) -> str:
    """Assessor → assessor: scoped-делегирование.

    Условия (C6):
    - grantor должен иметь роль assessor (или superadmin).
    - grantor сам должен мочь выполнить `action` над `resource`.
    - Невыполнимо для client (он использует `share`).

    Returns: grant_id.
    Raises: AuthorizationError.
    """
    if not grantor.has_any(Role.SUPERADMIN, Role.ASSESSOR):
        raise AuthorizationError(
            f"{grantor.sub}: только assessor/superadmin может делегировать"
        )
    if not can(grantor, action, resource, store):
        raise AuthorizationError(
            f"{grantor.sub} не может делегировать то, чего сам не может"
        )
    return store.add(Grant(
        subject_sub=grantee_sub,
        action=action,
        resource=resource,
        granted_by=grantor.sub,
        expires_at=expires_at,
    ))


def share(
    *,
    sharer: Principal,
    recipient_sub: str,
    resource: Resource,
    store: GrantStore,
    expires_at: datetime | None = None,
) -> str:
    """Client → третье лицо: VIEW-only share-токен.

    Условия (C6):
    - sharer должен иметь роль client (или superadmin).
    - sharer должен мочь видеть `resource`.
    - Грант фиксированный: `action=view`. Невозможно расшарить edit/input.

    Returns: grant_id.
    """
    if not sharer.has_any(Role.SUPERADMIN, Role.CLIENT):
        raise AuthorizationError(
            f"{sharer.sub}: только client/superadmin может шерить"
        )
    if not can(sharer, Action.VIEW, resource, store):
        raise AuthorizationError(
            f"{sharer.sub} не может расшарить то, чего сам не видит"
        )
    return store.add(Grant(
        subject_sub=recipient_sub,
        action=Action.VIEW,
        resource=resource,
        granted_by=sharer.sub,
        expires_at=expires_at,
    ))
