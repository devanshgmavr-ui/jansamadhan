# SLA sweep scheduling (G6)

The 24-hour government-review SLA is enforced by the idempotent service
operation `government_review_service.sweep_expired()`, exposed over HTTP as
`POST /api/v1/government/requests/sweep-escalations` and as the standalone
runner `backend/scripts/sla_sweep.py`.

## Runner

From `backend/` (uses the same `.env`/environment configuration as the API;
no new settings):

    venv/Scripts/python.exe scripts/sla_sweep.py [--limit 100]

On Linux/macOS: `venv/bin/python scripts/sla_sweep.py [--limit 100]`

Output is a single summary line (`sla-sweep at=<UTC> escalated=<n>`);
exit code is 0. No secrets are printed.

## Recommended schedules (every 5–15 minutes)

Cron (runs as the backend user, from `backend/`):

    */10 * * * * /srv/jansamadhan/backend/venv/bin/python /srv/jansamadhan/backend/scripts/sla_sweep.py >> /var/log/jansamadhan/sla-sweep.log 2>&1

systemd timer: a `jansamadhan-sla-sweep.service` (Type=oneshot, same
command) paired with a `jansamadhan-sla-sweep.timer` (`OnCalendar=*:0/10`).

Windows Task Scheduler: run the same command every 10 minutes.

## Safety rules

- Run exactly ONE scheduler for a database. Overlapping runs are harmless
  (row-level locking + PENDING re-check yield one transition and one audit
  row per review), but a single schedule keeps logs and load predictable.
- Cadence 5–15 minutes is sufficient: a review escalates within minutes of
  its `sla_due_at`, never with second-level precision claims.
- All timestamps are timezone-aware UTC; the scheduler provides no time.
- Never run the sweep against a database you do not intend to modify;
  the runner uses the configured `DATABASE_URL` (staging vs production).

---

# Supabase Storage for attachments (Stage-11 storage)

## Required environment variables (backend/.env)

    STORAGE_PROVIDER=supabase
    SUPABASE_URL=https://<project-ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=<service-role key, server-side only>
    SUPABASE_ATTACHMENTS_BUCKET=attachments

`STORAGE_PROVIDER=local` (default) keeps files under
`backend/uploads/problem_attachments` and `backend/uploads/solution_pdfs`.
The service-role key is only ever used by the backend over HTTPS; it is
never sent to frontends, never logged, and never appears in responses.

## Bucket

- Name: `attachments`
- Privacy: **private** (no public access).
- The backend never creates buckets automatically. Create it manually once:
  Supabase Dashboard -> Storage -> New bucket -> name `attachments`,
  Private bucket ON -> Save.

## How uploads work

1. Existing validation runs first (extension, 10 MB problem / 15 MB
   solution-PDF limits, PDF/image magic bytes).
2. Backend uploads the bytes to
   `problem-attachments/{problem_ticket}/{uuid}.{ext}` (solutions:
   `solution-pdfs/{solution_ticket}/{uuid}.{ext}`) with the service key.
   Original filenames are never used.
3. Only then is the database row committed (stored name, original display
   name, mime type, size). No local paths, no signed URLs are stored.
4. If the commit fails, the uploaded object is deleted immediately, so no
   orphans remain. If the upload fails, the database is untouched.

## How downloads work

`GET /api/v1/problems/{ticket}/attachments/{id}/download` (and the
solution download endpoint) are unchanged. The backend mints a signed URL
valid for ~5 minutes, fetches the bytes server-side, and streams them back
with the original filename. Frontends never contact Supabase directly.

## How migration works (manual, never automatic)

`scripts/migrate_attachments_to_supabase.py` uploads every local file to
its Supabase object path without touching database rows (stored names are
provider-independent) and never deletes local files:

    venv/Scripts/python.exe scripts/migrate_attachments_to_supabase.py
    venv/Scripts/python.exe scripts/migrate_attachments_to_supabase.py --apply

Run it AFTER creating the bucket and BEFORE switching
`STORAGE_PROVIDER` to `supabase`.
