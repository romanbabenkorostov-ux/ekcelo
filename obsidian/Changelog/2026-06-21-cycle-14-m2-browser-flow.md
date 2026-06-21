# 2026-06-21 — Cycle 14 M2 OAuth browser code-flow (FE-0)

## Что сделал

OAuth2 Authorization Code flow для браузера — `/auth/login` + `/auth/callback`
+ session-cookie. Это FE-0 в плане frontend (prerequisite для `ekcelo-site`
login, выбран пользователем).

## Файлы
- ✨ `lot_orchestrator_web/oauth_browser.py` — OAuthBrowserConfig,
  register_auth_routes (/auth/login /callback /logout), urllib_token_exchanger.
- ✏️ `lot_orchestrator_web/oauth.py` — `SESSION_COOKIE`, `/auth/` в exempt,
  OAuthMiddleware читает токен из cookie ИЛИ Authorization header.
- ✏️ `lot_orchestrator_web/main.py` — register_auth_routes в create_app.
- ✨ `lot_orchestrator_web/tests/test_oauth_browser.py` — 15 тестов.
- ✨ `obsidian/Architecture/cycle-14-m2-browser-flow.md` — снимок.
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — cycle 14 M2 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live.
- ✏️ `docs/specs/SPEC_backend.md` — актуализирован.

## Тесты
- 15 новых M2. Полный suite: **495 passed, 1 skipped** (480 + 15). 0 регрессий.

## Решения

- **Token exchange инъектируемый.** `code→token` через `TokenExchanger`
  callable. Production — urllib (stdlib, без httpx как JWKSProvider). Тесты —
  mock без реального IdP. Чисто тестируемо.
- **Cookie ИЛИ header в middleware.** OAuthMiddleware (M1) расширен: токен из
  `Authorization: Bearer` (API) ИЛИ cookie `ekcelo_token` (browser). Один
  verify-путь для обоих. SPA не хранит токен в JS (httponly), защита от XSS.
- **id_token предпочтительнее access_token.** id_token содержит identity-claims
  (sub, email); access_token — для API. Для session берём id_token, fallback
  на access. Оба валидируются M1 как JWT.
- **State CSRF-защита.** Случайный state в httponly-cookie при login,
  проверка на callback. Несовпадение → 400.
- **`/auth/*` exempt от middleware.** Иначе login-редирект сам требовал бы
  токен (chicken-egg). Login/callback всегда доступны.
- **M2 opt-in через EKCELO_OIDC_CLIENT_ID.** Без него `/auth/*` не
  регистрируются; M1 Bearer работает как раньше. Backward-compat.
- **Confidential client (client_secret), не PKCE.** Бэкенд хранит secret —
  confidential flow. Если SPA станет public client — добавим PKCE отдельно.

## Канал доставки
- Sandbox-proxy блокирует push — zip-handoff (после merge #119).

## Следующий шаг (план frontend)
- **FE-0 (этот sub-stage):** OAuth M2 ✅.
- **FE-1:** scaffold `ekcelo-site/` (монорепо) Vite + core/viewmodel +
  adapters/api + catalog/object UI + login через /auth/login.
- **FE-2:** граф нативно + порт kmz→ViewModel адаптера из viewer/.
- **FE-3:** карта (Google Earth/Leaflet) + единый рендер обоих адаптеров.
