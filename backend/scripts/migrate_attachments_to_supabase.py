"""Migrate locally stored attachments to Supabase Storage (manual utility).

For every ProblemAttachment and Solution PDF whose file still exists under
backend/uploads/*, uploads the bytes to the exact Supabase object path and
leaves the database row untouched (stored_name is provider-independent, so
no column changes are needed). Local files are NEVER deleted by this script.

Usage (from backend/, after configuring Supabase env vars):
    venv/Scripts/python.exe scripts/migrate_attachments_to_supabase.py
    venv/Scripts/python.exe scripts/migrate_attachments_to_supabase.py --apply

Default is dry-run. Exit code 0 only when every local file was uploaded
(or already present).
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.problem import Problem, ProblemAttachment  # noqa: E402
from app.models.solution import Solution  # noqa: E402
from app.services import storage as storage_svc  # noqa: E402
from app.services.supabase_storage import (  # noqa: E402
    StorageError,
    SupabaseStorageProvider,
)


def _targets(db):
    items = []
    for attachment in db.query(ProblemAttachment).all():
        problem = db.get(Problem, attachment.problem_id)
        if problem is None:
            continue
        items.append((
            storage_svc.NAMESPACE_PROBLEM_ATTACHMENTS, problem.ticket,
            attachment.stored_name,
        ))
    for solution in db.query(Solution).all():
        if not solution.pdf_stored_name:
            continue
        items.append((
            storage_svc.NAMESPACE_SOLUTION_PDFS, solution.ticket,
            solution.pdf_stored_name,
        ))
    return items


def _local_file(namespace: str, stored_name: str) -> Path:
    backend_root = Path(__file__).resolve().parents[1]
    subdir = ("problem_attachments"
              if namespace == storage_svc.NAMESPACE_PROBLEM_ATTACHMENTS
              else "solution_pdfs")
    return backend_root / "uploads" / subdir / stored_name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload local attachments to Supabase Storage.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually upload. Without it, dry-run only.")
    args = parser.parse_args()

    provider = SupabaseStorageProvider(
        base_url=settings.SUPABASE_URL,
        service_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        bucket=settings.SUPABASE_ATTACHMENTS_BUCKET,
    )
    db = SessionLocal()
    try:
        items = _targets(db)
    finally:
        db.close()
    print(f"records: {len(items)} mode: "
          f"{'APPLY' if args.apply else 'DRY-RUN'}", flush=True)
    uploaded = present = skipped = failed = 0
    for namespace, ticket, stored_name in items:
        local = _local_file(namespace, stored_name)
        label = f"{namespace}/{ticket}/{stored_name}"
        if not local.is_file():
            print(f"SKIP (no local file) {label}", flush=True)
            skipped += 1
            continue
        if not args.apply:
            print(f"WOULD-UPLOAD {label} ({local.stat().st_size} bytes)",
                  flush=True)
            continue
        try:
            result = provider.upload_existing(
                namespace=namespace, ticket=ticket, stored_name=stored_name,
                content=local.read_bytes(),
            )
        except StorageError:
            print(f"FAILED {label}", flush=True)
            failed += 1
        else:
            print(f"{result.upper()} {label}", flush=True)
            if result == "uploaded":
                uploaded += 1
            else:
                present += 1
    print(f"uploaded={uploaded} present={present} skipped={skipped} "
          f"failed={failed}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
