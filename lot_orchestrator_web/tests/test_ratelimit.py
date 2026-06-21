"""Cycle 16 — RateLimiter core (in-memory) + env parsing."""
from __future__ import annotations

import pytest

from lot_orchestrator_web.ratelimit import RateLimitConfig, RateLimiter


class _Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float) -> None:
        self.t += dt


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def limiter(clock: _Clock) -> RateLimiter:
    cfg = RateLimitConfig(enabled=True, fails_limit=3, window_s=60, block_s=120)
    return RateLimiter(cfg, clock=clock)


# ─────────────────────────────────────────────────────────────────────────────
#  Config from env
# ─────────────────────────────────────────────────────────────────────────────

def test_config_defaults(monkeypatch):
    for k in ("EKCELO_RATELIMIT_ENABLED", "EKCELO_RATELIMIT_FAILS",
              "EKCELO_RATELIMIT_WINDOW_S", "EKCELO_RATELIMIT_BLOCK_S"):
        monkeypatch.delenv(k, raising=False)
    c = RateLimitConfig.from_env()
    assert c.enabled is True
    assert c.fails_limit == 5
    assert c.window_s == 300
    assert c.block_s == 900


def test_config_disabled_via_env(monkeypatch):
    monkeypatch.setenv("EKCELO_RATELIMIT_ENABLED", "false")
    c = RateLimitConfig.from_env()
    assert c.enabled is False


def test_config_custom_values(monkeypatch):
    monkeypatch.setenv("EKCELO_RATELIMIT_FAILS", "10")
    monkeypatch.setenv("EKCELO_RATELIMIT_WINDOW_S", "60")
    monkeypatch.setenv("EKCELO_RATELIMIT_BLOCK_S", "30")
    c = RateLimitConfig.from_env()
    assert c.fails_limit == 10
    assert c.window_s == 60
    assert c.block_s == 30


def test_config_invalid_int_falls_back(monkeypatch):
    monkeypatch.setenv("EKCELO_RATELIMIT_FAILS", "not-a-number")
    c = RateLimitConfig.from_env()
    assert c.fails_limit == 5


# ─────────────────────────────────────────────────────────────────────────────
#  is_blocked / record_failure / reset
# ─────────────────────────────────────────────────────────────────────────────

def test_initially_not_blocked(limiter):
    assert limiter.is_blocked("k1") == (False, 0)


def test_fails_below_limit_no_block(limiter):
    for _ in range(2):  # limit=3, ниже
        limiter.record_failure("k1")
    assert limiter.is_blocked("k1") == (False, 0)


def test_fail_at_limit_blocks(limiter):
    for _ in range(3):  # limit=3, как раз
        limiter.record_failure("k1")
    blocked, retry = limiter.is_blocked("k1")
    assert blocked is True
    assert 0 < retry <= 120  # block_s


def test_block_expires_after_block_s(limiter, clock):
    for _ in range(3):
        limiter.record_failure("k1")
    assert limiter.is_blocked("k1")[0] is True
    clock.tick(120.1)
    assert limiter.is_blocked("k1") == (False, 0)


def test_window_expires_resets_counter(limiter, clock):
    limiter.record_failure("k1")
    limiter.record_failure("k1")
    clock.tick(61.0)  # вышли из окна
    limiter.record_failure("k1")  # новое окно, fails=1
    assert limiter.is_blocked("k1") == (False, 0)
    rec = limiter.snapshot("k1")
    assert rec.fails == 1


def test_reset_clears_failures(limiter):
    for _ in range(2):
        limiter.record_failure("k1")
    limiter.reset("k1")
    assert limiter.snapshot("k1") is None
    # после reset можно снова до limit-1 без блока
    for _ in range(2):
        limiter.record_failure("k1")
    assert limiter.is_blocked("k1") == (False, 0)


def test_keys_are_isolated(limiter):
    for _ in range(3):
        limiter.record_failure("k1")
    assert limiter.is_blocked("k1")[0] is True
    assert limiter.is_blocked("k2") == (False, 0)


def test_record_failure_returns_blocked_status(limiter):
    blocked, retry = limiter.record_failure("k1")
    assert blocked is False
    blocked, retry = limiter.record_failure("k1")
    assert blocked is False
    blocked, retry = limiter.record_failure("k1")  # 3-й = блок
    assert blocked is True
    assert retry > 0


def test_disabled_limiter_is_noop():
    cfg = RateLimitConfig(enabled=False, fails_limit=1, window_s=60, block_s=60)
    lim = RateLimiter(cfg)
    for _ in range(10):
        lim.record_failure("k")
    assert lim.is_blocked("k") == (False, 0)
