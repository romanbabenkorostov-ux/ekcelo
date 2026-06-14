# Cycle 14 — OAuth2/OIDC (M1: Bearer-JWT verifier + strategy)

> Реализует частично `contracts/roles/ROLES_SPEC.md` (C6) — токен-аутентификация
> вместо/совместно с Basic Auth (cycle 12-13). M1 — серверная валидация
> входящего Bearer. M2 (будущий) — `/auth/login` redirect + `/auth/callback`
> browser code-flow. M3 (cycle 15) — RBAC поверх `Subject.roles`.

## Зачем

Basic Auth (cycle 13) хранит креды в env — годится для пары операторов за
reverse-proxy. Для multi-tenant с ролями (assessor/client) нужен внешний IdP
(Keycloak/Authentik/Google). Cycle 14 даёт:
- Bearer-JWT валидацию по issuer + audience + JWKS (RS256 стандарт).
- Стратегия выбора auth в `create_app`: OIDC > Basic > none.
- Чистый отступной путь — если PyJWT не установлен, всё работает на Basic Auth.

## Архитектура (M1)

```
┌─ Стратегия диспетчер ─────────────────────────────────────────────────────┐
│ maybe_install_auth(app) → "oidc" | "basic" | "none"                        │
│   1. OIDCConfig.from_env() ИЛИ явный config → OAuthMiddleware              │
│   2. EKCELO_AUTH_USERS  → BasicAuthMiddleware (cycle 12-13)                │
│   3. ничего              → no-auth (dev)                                   │
└────────┬──────────────────────────────────────────────────────────────────┘
         │
┌─ OAuthMiddleware (новое) ────────────────┐  ┌─ BasicAuthMiddleware (как было)
│ ASGI/Starlette BaseHTTPMiddleware         │  │ HTTP Basic Auth, PBKDF2 (cycle 13)
│ Exempt: "/", "/static/", "/docs",         │  │
│         "/openapi.json", "/redoc"          │  │
│ Bearer → verify_jwt → request.state.subject│  │
└────────┬─────────────────────────────────┘  └──
         │
┌─ verify_jwt(token, config, jwks) ─────────┐
│ 1. Header → alg, kid                      │
│ 2. JWK resolve по kid из JWKS             │
│ 3. PyJWT.decode (sig + aud + iss + exp)   │
│ 4. Subject(sub, roles, claims)            │
└───────────────────────────────────────────┘
```

## Конфиг (env)

| Переменная | Обязательно | Описание |
|---|---|---|
| `EKCELO_OIDC_ISSUER` | да (включает OIDC) | URL Identity Provider (`iss` claim) |
| `EKCELO_OIDC_AUDIENCE` | да | Ожидаемое `aud` (например `ekcelo-api`) |
| `EKCELO_OIDC_JWKS_URL` | да | URL `.well-known/jwks.json` IdP |
| `EKCELO_OIDC_ALGORITHMS` | нет (`RS256`) | Comma-separated алгоритмы |
| `EKCELO_OIDC_ROLES_CLAIM` | нет (`roles`) | Dotted-path к ролям (`realm_access.roles` для Keycloak) |

Если `EKCELO_OIDC_ISSUER` пуст — fallback на Basic (`EKCELO_AUTH_USERS`).

## Поведение

### Exempt-пути
`/`, `/static/*`, `/docs`, `/openapi.json`, `/redoc` — без auth.

### Защищённый запрос
- `Authorization: Bearer <jwt>` отсутствует → `401` + `WWW-Authenticate: Bearer realm="ekcelo"`.
- Невалидный JWT (подпись/expiry/audience/issuer/неизвестный kid/отсутствует sub) → `401`.
- Валидный JWT → `request.state.subject = Subject(sub, roles, claims)`.

### Subject
```python
@dataclass(frozen=True)
class Subject:
    sub: str                 # из claims["sub"]
    roles: tuple[str, ...]   # из claims по roles_claim path
    claims: dict[str, Any]   # полные claims для downstream
```

Используется в эндпоинтах: `request.state.subject` → можно строить RBAC
(cycle 15).

## Что НЕ в M1

Будет в **M2**:
- `/auth/login` redirect на IdP (OAuth2 code-flow).
- `/auth/callback` обмен code → токен, cookie сессия.
- Refresh tokens.

Будет в **cycle 15 (M3)**:
- RBAC поверх `Subject.roles` (`Depends(require("edit", lot_id))`).
- Хранилище access_grants в БД.

## Зависимости

- `PyJWT[crypto]>=2.8` — opt-in extra `[orchestrator-oauth]`.
- Без extras — `OAuthMiddleware` падает с ясной ошибкой при использовании;
  Basic Auth и no-auth работают как раньше (полный backward-compat).

## Файлы и тесты

| Файл | LOC | Назначение |
|---|---|---|
| `lot_orchestrator_web/oauth.py` | ~280 | OIDCConfig, JWKSProvider, verify_jwt, OAuthMiddleware, maybe_install_auth |
| `lot_orchestrator_web/tests/test_oauth.py` | ~250 | 19 service-тестов (verify_jwt + JWKS + config) |
| `lot_orchestrator_web/tests/test_oauth_middleware.py` | ~120 | 7 интеграционных тестов на FastAPI |
| `lot_orchestrator_web/tests/test_auth_strategy.py` | ~60 | 5 dispatcher-тестов |
| `lot_orchestrator_web/main.py` | +3 | `maybe_install_auth` вместо прямого Basic |
| `pyproject.toml` | +6 | extra `[orchestrator-oauth]` |

**Тесты:** 31 cycle 14 (19 + 7 + 5); полный suite **354 pass**
(323 после P0.1.3 + 31).

Покрытие:
- verify_jwt: happy (sub, roles, nested roles_claim), expired, wrong-audience,
  wrong-issuer, unknown kid, disallowed alg, missing sub, malformed JWT, HS256
  с/без secret.
- OIDCConfig.from_env: none без issuer, требует audience+jwks, parsing
  algorithms + roles_claim.
- JWKSProvider: dict, callable + cache, TTL expiry.
- Middleware: exempt root/static, 401 без Bearer, 401 на garbage/expired,
  200 на валидном, не-Bearer schemes отвергнуты.
- Dispatcher: none, basic, oidc explicit, oidc env, oidc beats basic.

## Связи

- C6: `contracts/roles/ROLES_SPEC.md` (что значат роли — реализуется в cycle 15).
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md` §Cycle 14.
- Предшественник: `lot_orchestrator_web/auth.py` (Basic Auth, остаётся).
- Triggers (по roadmap): >2 пользователей ИЛИ внешний доступ ИЛИ SSO.
