"""Rate limiting на auth-провалы (cycle 16).

Hardening против online credential-stuffing: после N неудачных auth-попыток
по ключу (IP, username) — блок на T секунд с `429 Too Many Requests` +
`Retry-After`.

Cycle 13 защитил от offline-brute-force через PBKDF2 600k. Cycle 16 закрывает
online: даже с медленным хешем, миллион попыток в минуту перегружает CPU и
даёт шанс на угадывание. Rate limit срезает атаку.

Конфиг через env:
- `EKCELO_RATELIMIT_ENABLED` (default `true`)
- `EKCELO_RATELIMIT_FAILS` (default 5)
- `EKCELO_RATELIMIT_WINDOW_S` (default 300 = 5 мин)
- `EKCELO_RATELIMIT_BLOCK_S` (default 900 = 15 мин)

Backend — in-memory (single-worker дефолт). Redis-backend оставлен крючком в
конструкторе для multi-worker деплоя (cycle 16+).

Интегрируется в `BasicAuthMiddleware` и `OAuthMiddleware` через `RateLimiter`,
который кладётся в `app.state.rate_limiter`.

См. также:
- `lot_orchestrator_web/auth.py` (Basic Auth, M4 расширение).
- `lot_orchestrator_web/oauth.py` (OAuth Bearer).
- `obsidian/Architecture/cycle-16-ratelimit.md`.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from threading import Lock


# ─────────────────────────────────────────────────────────────────────────────
#  Конфиг
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool = True
    fails_limit: int = 5     # сколько провалов в окне → блок
    window_s: int = 300       # окно подсчёта провалов (секунды)
    block_s: int = 900        # длительность блока (секунды)

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        return cls(
            enabled=_env_bool("EKCELO_RATELIMIT_ENABLED", default=True),
            fails_limit=_env_int("EKCELO_RATELIMIT_FAILS", default=5),
            window_s=_env_int("EKCELO_RATELIMIT_WINDOW_S", default=300),
            block_s=_env_int("EKCELO_RATELIMIT_BLOCK_S", default=900),
        )


def _env_bool(name: str, *, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int) -> int:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    try:
        return int(v)
    except ValueError:
        return default


# ─────────────────────────────────────────────────────────────────────────────
#  Core
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _Record:
    fails: int = 0
    first_fail_ts: float = 0.0
    blocked_until_ts: float = 0.0


class RateLimiter:
    """Thread-safe in-memory счётчик неудачных auth-попыток.

    Контракт:
    - `is_blocked(key)` → `(blocked: bool, retry_after_s: int)`.
    - `record_failure(key)` инкрементит счётчик. Если в окне накопилось
      >= `fails_limit` провалов — устанавливает блок на `block_s` секунд.
    - `reset(key)` сбрасывает счётчик (вызывается при успешной аутентификации).

    `clock` параметр для тестов (моноклон под `time.monotonic`).
    """

    def __init__(self, config: RateLimitConfig, *, clock=None) -> None:
        self._config = config
        self._records: dict[str, _Record] = {}
        self._clock = clock or time.monotonic
        self._lock = Lock()

    @property
    def config(self) -> RateLimitConfig:
        return self._config

    def is_blocked(self, key: str) -> tuple[bool, int]:
        """Возвращает (blocked, retry_after_s). retry_after=0 если не заблокирован."""
        if not self._config.enabled:
            return False, 0
        now = self._clock()
        with self._lock:
            rec = self._records.get(key)
            if rec is None or rec.blocked_until_ts <= now:
                return False, 0
            return True, max(1, int(rec.blocked_until_ts - now))

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Регистрирует неудачную попытку. Возвращает (blocked_now, retry_after_s)."""
        if not self._config.enabled:
            return False, 0
        now = self._clock()
        cfg = self._config
        with self._lock:
            rec = self._records.get(key)
            if rec is None or (now - rec.first_fail_ts) > cfg.window_s:
                # новое окно
                rec = _Record(fails=1, first_fail_ts=now)
            else:
                rec.fails += 1
            if rec.fails >= cfg.fails_limit:
                rec.blocked_until_ts = now + cfg.block_s
            self._records[key] = rec
            blocked = rec.blocked_until_ts > now
            retry = max(0, int(rec.blocked_until_ts - now)) if blocked else 0
            return blocked, retry

    def reset(self, key: str) -> None:
        """Сбрасывает счётчик (успешный логин)."""
        if not self._config.enabled:
            return
        with self._lock:
            self._records.pop(key, None)

    # Удобство для тестов
    def snapshot(self, key: str) -> _Record | None:
        with self._lock:
            return self._records.get(key)
