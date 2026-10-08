"""In-memory login throttling (single-process).

Repeated failed password logins from the same client IP are temporarily
blocked. Success resets the counter. Thresholds are module constants so tests
can exercise expiry without waiting; production values are deliberately
lenient to avoid locking out legitimate users over a few mistakes.
"""

import time

MAX_FAILURES = 5
WINDOW_SECONDS = 10 * 60
BLOCK_SECONDS = 15 * 60

# key -> {"count": int, "window_start": float, "blocked_until": float}
_attempts: dict[str, dict] = {}


def _now() -> float:
    return time.time()


def is_blocked(key: str) -> bool:
    entry = _attempts.get(key)
    if not entry:
        return False
    if entry["blocked_until"] > _now():
        return True
    if _now() - entry["window_start"] >= WINDOW_SECONDS:
        _attempts.pop(key, None)
        return False
    return False


def record_failure(key: str) -> bool:
    """Record a failed login. Returns True if the key is now blocked."""
    now = _now()
    entry = _attempts.get(key)
    if entry is None or now - entry["window_start"] >= WINDOW_SECONDS:
        entry = {"count": 0, "window_start": now, "blocked_until": 0.0}
    entry["count"] += 1
    if entry["count"] >= MAX_FAILURES:
        entry["blocked_until"] = now + BLOCK_SECONDS
    _attempts[key] = entry
    return entry["blocked_until"] > now


def record_success(key: str) -> None:
    _attempts.pop(key, None)


def reset_login_attempts() -> None:
    """Test hook: clear all counters."""
    _attempts.clear()
