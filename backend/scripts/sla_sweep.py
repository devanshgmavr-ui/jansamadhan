"""SLA sweep runner (G6): escalate expired PENDING government reviews.

Single-shot, idempotent entry point for external schedulers (cron, systemd
timers, platform jobs). It performs no scheduling itself: invoke it every
5-15 minutes; each run escalates only reviews past their 24h window and is
safe to repeat or overlap (row-level locking + state re-check in the
service layer guarantees exactly one transition per review).

Usage (from backend/):
    venv/Scripts/python.exe scripts/sla_sweep.py [--limit N]

Exit code 0 with a one-line summary on stdout. No secrets are printed.
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
from app.services import government_review_service  # noqa: E402


def main(limit: int) -> int:
    db = SessionLocal()
    try:
        escalated = government_review_service.sweep_expired(db, limit=limit)
    finally:
        db.close()
    now = datetime.now(timezone.utc).isoformat()
    print(
        f"sla-sweep at={now} escalated={len(escalated)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    raise SystemExit(main(max(args.limit, 1)))
