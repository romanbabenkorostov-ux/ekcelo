# Cycle 14 M2 — OAuth2 browser code-flow

> Дополняет cycle 14 M1 (Bearer-валидация) browser-сценарием: `/auth/login`
> редирект на IdP + `/auth/callback` обмен code на токен + session-cookie.
> Prerequisite для `ekcelo-site` frontend login UI (FE-0 в плане фронта).

## Зачем

M1 валидирует входящий Bearer-токен (для API-клиентов/интеграций). M2 даёт
человеческий login: пользователь жмёт «Войти» → редирект на IdP (Keycloak/
Authentik/Google) → после авторизации возвращается с токеном в httponly-cookie.
SPA (`ekcelo-site`) использует этот flow вместо нативного Basic-диалога.

## Поток (OAuth2 Authorization Code)

```
Browser            ekcelo backend           IdP
  │  GET /auth/login    │                     │
  ├────────────────────►│                     │
  │  307 → authorize_url + state (cookie)     │
  │◄────────────────────┤                     │
  │  GET authorize?...&state                  │
  ├──────────────────────────────────────────►│
  │         (пользователь логинится в IdP)    │
  │  302 → /auth/callback?code&state          │
  │◄──────────────────────────────────────────┤
  │  GET /auth/callback?code&state            │
  ├────────────────────►│                     │
  │      verify state (CSRF) │ POST token_url(code) │
  │                     ├────────────────────►│
  │                     │  {id_token,access_token}  │
  │                     │◄────────────────────┤
  │  307 → / + Set-Cookie ekcelo_token        │
  │◄────────────────────┤                     │
  │  GET /objects/{cad} (cookie несёт JWT)    │
  ├────────────────────►│ OAuthMiddleware (M1)│
  │  200 ViewModel      │ verify cookie-JWT   │
  │◄────────────────────┤                     │
```

## Эндпоинты

| Метод | Путь | Поведение |
|---|---|---|
| GET | `/auth/login` | 307 → authorize_url с `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`. State в httponly-cookie (CSRF). |
| GET | `/auth/callback?code&state` | Проверка state, обмен code→token, Set-Cookie `ekcelo_token`, 307 → post_login_redirect. Ошибки: 400 (нет code/state mismatch), 502 (token exchange fail). |
| GET | `/auth/logout` | Очистка cookie. |

`/auth/*` в exempt-списке OAuthMiddleware (не требует токена сам по себе).

## Cookie-сессия

После callback токен (id_token предпочтительно, иначе access_token) кладётся
в httponly-cookie `ekcelo_token` (`oauth.SESSION_COOKIE`). M1 OAuthMiddleware
расширен: читает токен из `Authorization: Bearer` ИЛИ из cookie. Так browser
и API используют один verify-путь.

Cookie-флаги: `HttpOnly`, `Secure` (default true; `EKCELO_OIDC_COOKIE_SECURE=
false` для local http dev), `SameSite=Lax`, `Max-Age` (default 3600).

## Token exchange — инъектируемый

`code → token` вынесен в `TokenExchanger` callable:
- Production: `urllib_token_exchanger` (stdlib urllib, без httpx — как
  JWKSProvider).
- Тесты: mock-callable, без реального IdP.

## Конфиг (env)

| Переменная | Обязательно | Описание |
|---|---|---|
| `EKCELO_OIDC_CLIENT_ID` | да (включает M2) | client_id приложения в IdP |
| `EKCELO_OIDC_CLIENT_SECRET` | да | client secret |
| `EKCELO_OIDC_AUTHORIZE_URL` | да | authorize endpoint IdP |
| `EKCELO_OIDC_TOKEN_URL` | да | token endpoint IdP |
| `EKCELO_OIDC_REDIRECT_URI` | да | наш `/auth/callback` URL |
| `EKCELO_OIDC_SCOPES` | нет (`openid profile email`) | scopes |
| `EKCELO_OIDC_POST_LOGIN` | нет (`/`) | куда редиректить после login |
| `EKCELO_OIDC_COOKIE_SECURE` | нет (`true`) | Secure-флаг (false для local) |

Если `EKCELO_OIDC_CLIENT_ID` пуст — `/auth/*` не регистрируются (M2 выключен),
M1 Bearer работает как раньше.

## Файлы и тесты

| Файл | Назначение |
|---|---|
| `lot_orchestrator_web/oauth_browser.py` | OAuthBrowserConfig + register_auth_routes + token exchanger |
| `lot_orchestrator_web/oauth.py` | SESSION_COOKIE, `/auth/` exempt, cookie-токен в middleware |
| `lot_orchestrator_web/main.py` | register_auth_routes в create_app |
| `lot_orchestrator_web/tests/test_oauth_browser.py` | 15 тестов |

**Тесты M2:** 15. Полный suite: **495 passed, 1 skipped** (480 + 15).

Покрытие: login redirect + state cookie, callback exchange + cookie set,
400 (no code / state mismatch / no state cookie), 502 (exchange fail / empty
token), id_token > access_token preference, logout, config from_env
(none/partial/full), register returns false, end-to-end cookie→middleware→200.

## Что НЕ в M2

- **Refresh tokens** — обновление access по refresh без re-login. Отдельный
  sub-stage при необходимости (cookie max-age 1ч сейчас).
- **PKCE** (code_challenge) — для public clients. Текущий flow — confidential
  client (client_secret). PKCE добавляется если SPA станет public.
- **Logout у IdP** (end_session_endpoint) — сейчас только локальная очистка cookie.

## Связи

- Cycle 14 M1: `cycle-14-oauth.md` (Bearer verify, OIDCConfig).
- Frontend: `SPEC_frontend.md` — `ekcelo-site` login использует этот flow (FE-0/FE-1).
- Roadmap: `obsidian/Architecture/roadmap-2026-06.md` §Cycle 14.
