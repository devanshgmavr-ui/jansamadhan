"""Notification retry runner: re-drive PENDING orphans and FAILED intents.

Single-shot, idempotent entry point for external schedulers (cron, systemd
timers, platform jobs such as Render Cron Jobs). It performs no scheduling
itself: invoke it periodically; each run re-attempts bounded retries
(MAX_ATTEMPTS in the service layer, no infinite loops) and is safe to
repeat or overlap (row-level locking in deliver_intent plus the exactly-once
audit_id anchor guarantee no duplicate sends and no audit changes).

Usage (from backend/):
    venv/Scripts/python.exe scripts/notification_retry.py [--limit N]

Exit code 0 with a one-line summary on stdout. Only counts are printed:
no recipients, subjects, bodies, tokens, or keys. Exit code 2 when the
database itself is unreachable.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from app.db.database import SessionLocal  # noqa: E402
from app.services import notification_service  # noqa: E402


def main(limit: int) -> int:
    try:
        db = SessionLocal()
    except Exception:
        logging.exception("notification-retry: database unreachable")
        return 2
    try:
        result = notification_service.retry_failed(db, limit=limit)
    except Exception:
        logging.exception("notification-retry: run failed")
        return 2
    finally:
        db.close()
    now = datetime.now(timezone.utc).isoformat()
    print(
        f"notification-retry at={now} attempted={result['attempted']} "
        f"sent={result['sent']} failed={result['failed']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    raise SystemExit(main(max(args.limit, 1)))
