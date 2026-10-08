"""Revoked government-token JTIs (G3, single-process).

The shared revoked_tokens table cannot hold government JTIs: its user_id is
a non-nullable foreign key to the public users table, and government
officials are deliberately not public users. Rather than a second database
table for G3, revocation reuses the project's existing in-memory pattern
(core.ratelimit): a process-local set of revoked JTIs containing no secrets
(JTIs are random identifiers) and no personal data.

Same limitation class as the login throttle: state is lost on restart and
not shared across workers. A persistent government denylist table is the
documented G6 step before multi-process production.
"""

_revoked_jtis: set[str] = set()


def revoke(jti: str) -> None:
    """Record a government access-token JTI as logged out. Idempotent."""
    if jti:
        _revoked_jtis.add(jti)


def is_revoked(jti: str | None) -> bool:
    return bool(jti) and jti in _revoked_jtis


def clear() -> None:
    """Test hook: empty the set (mirrors ratelimit.reset_login_attempts)."""
    _revoked_jtis.clear()
