"""Runtime settings with environment fallback (Phase 4, Part F).

DB rows win when present; otherwise the matching environment/config
value applies, so unset keys behave exactly as before. Small TTL cache
(30s) avoids a query per upload/review; updates invalidate it.
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system_settings import KNOWN_SETTINGS, SystemSetting

_TTL_SECONDS = 30
_cache: dict[str, tuple[float, str]] = {}


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(SystemSetting, key)
    return row.value if row is not None else None


def get_effective(db: Session | None, key: str, env_value: str,
                  default: str = "") -> str:
    """DB value if set, else the environment/config value, else default."""
    if db is not None:
        now = time.time()
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < _TTL_SECONDS:
            return hit[1]
        try:
            row = db.get(SystemSetting, key)
        except Exception:
            row = None
        if row is not None and (row.value or "").strip() != "":
            _cache[key] = (now, row.value)
            return row.value
        _cache[key] = (now, env_value if env_value else default)
    return env_value if env_value else default


def list_settings(db: Session) -> list[dict]:
    rows = {r.key: r.value for r in
            db.execute(select(SystemSetting)).scalars().all()}
    out = []
    for key, (default, purpose) in KNOWN_SETTINGS.items():
        out.append({"key": key, "value": rows.get(key, default),
                    "default": default, "purpose": purpose,
                    "customized": key in rows})
    return out


def set_setting(db: Session, key: str, value: str) -> dict:
    if key not in KNOWN_SETTINGS:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown setting. Allowed: {sorted(KNOWN_SETTINGS)}.",
        )
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value)
    else:
        row.value = value
    db.add(row)
    db.commit()
    db.refresh(row)
    _cache.pop(key, None)
    default, purpose = KNOWN_SETTINGS[key]
    return {"key": key, "value": row.value, "default": default,
            "purpose": purpose, "customized": True}


def invalidate() -> None:
    _cache.clear()
