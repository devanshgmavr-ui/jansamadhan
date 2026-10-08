# JanSamadhan Production Runbook (cutover + rollback)

## Architecture
- Public frontend (`frontend/`, Vite+React) + government portal
  (`government-portal/`, Vite+React, separate session) talk ONLY to the
  backend API. Neither frontend touches Supabase, OpenRouter, or Brevo.
- Backend (`backend/`, FastAPI `app.main:app`, Postgres/Supabase) owns
  auth, AI screening (public side only), government workflow, SLA,
  notifications, and Supabase Storage (private `attachments` bucket).

## Render service layout
- Web Service: Root Directory `backend`, Start Command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (Render supplies
  `$PORT`; never hardcode). Health check path `/health`.
- Static Site (public): Root Directory `frontend`, Build Command
  `npm run build`, Publish Directory `dist`, env `VITE_API_URL` only.
- Static Site (portal): Root Directory `government-portal`, Build Command
  `npm run build`, Publish Directory `dist`, env `VITE_API_URL` only.
- Both apps use BrowserRouter: add rewrite `/* -> /index.html` on each
  Static Site or deep-link refresh 404s.

## Scaling block (G8 P3)
- Target topology: SINGLE backend instance. Login throttling
  (`app/core/ratelimit.py`) and government logout revocation
  (`app/core/gov_revocation.py`) are process-local: lost on restart,
  invisible to other instances. Horizontal scaling is BLOCKED until
  shared state (Redis/DB denylist) is implemented. Never run two
  backends behind one domain today.

## Environment variables
- Full matrix: `backend/.env.production.example` (A–H sections).
  Backend secrets live in Render environment variables, never in cron
  config, never in frontend env.

## 0. Freeze & approval
- Freeze merges. Record backend/frontend/portal commit SHAs + Alembic head
  (current: `f7a8b9c0d1e2`). Get explicit human approval for cutover.

## 1. Backups (before anything irreversible)
- Supabase Dashboard -> Database -> Backups: confirm automated backups ON,
  note retention + latest restorable point.
- Storage: object versioning/pit-restore per Supabase plan; record bucket
  `attachments` (private) object count.
- Save backup identifiers in the release log.

## 2. Production secrets (secret manager, never chat/files)
- `JWT_SECRET_KEY` (fresh random, per-environment), `DATABASE_URL`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `BREVO_API_KEY`,
  `AI_API_KEY` (only if AI_PROVIDER=openrouter, else leave empty + mock).
- Frontends get ONLY `VITE_API_URL=https://<api-domain>/api/v1`.

## 3. Database
- Create production database + enable pgcrypto/uuid support as needed.
- From `backend/`: `python -m alembic upgrade head`
- Verify: `python -m alembic current` == `f7a8b9c0d1e2`; check
  `government_users.employee_id` unique, no `email` column.
- Rollback: NEVER auto-downgrade. Restore from the verified backup.

## 4. Storage
- Create PRIVATE bucket `attachments` (Dashboard -> Storage -> New bucket).
- If historical rows exist: `scripts/migrate_attachments_to_supabase.py`
  (dry-run, then `--apply` with approval). Verify counts + spot-check bytes.
- Set `STORAGE_PROVIDER=supabase`.

## 5. Backend deploy
- `pip install -r requirements.txt`; start ONE instance:
  `uvicorn app.main:app --host 0.0.0.0 --port 8000` (behind TLS proxy).
- `ENVIRONMENT=production`, `DEBUG=false`, tight `CORS_ORIGINS`
  (exact origins, never `*`), real `FRONTEND_URL`.
- Verify `GET /health` and `GET /health/db` == ok.

## 6. Schedulers (exactly ONE of each per database)
- SLA: `python scripts/sla_sweep.py [--limit 100]` every 10 min (cron/
  systemd/Timer per scripts/README.md). Overlapping runs are tolerated
  (row locks) but run one.
- Notification retry: `python scripts/notification_retry.py [--limit 100]`
  every 30 min. Safe to repeat/overlap (row locks + exactly-once intents;
  bounded MAX_ATTEMPTS=3, no duplicates). Before this runner existed,
  FAILED intents waited for manual re-drive via `deliver_intent`.
- Render Cron Jobs: one job per script, same repo code + same Render
  environment variables as the backend. Secrets come from the environment,
  never from cron configuration.

## 6b. Brevo / OpenRouter / provisioning activation
- Brevo (human): set prod `BREVO_API_KEY`, verified `BREVO_SENDER_EMAIL`,
  prod `FRONTEND_URL`; validate OTP + reset mail + 1 workflow mail.
  Government login stays Brevo-independent.
- OpenRouter (human): set prod `AI_API_KEY` + `AI_PROVIDER=openrouter`
  only with a real key; validate 1 live screening (no department claim,
  timeout/malformed handled). Otherwise stay on `mock` (B-3 BLOCKED).
- Officials: `python scripts/provision_government_user.py --employee-id
  <ID> [--full-name ...] [--designation ...]` (password via prompt/env,
  bcrypt-hashed, never logged). Name test accounts `TEST-*`; deactivate
  (`--inactive` + `--reset-password` rotation) before launch.

## 9b. Monitoring (wire before launch)
- Poll `GET /health` + `GET /health/db`; alert on non-ok.
- Alert on: 5xx rate, repeated 401 bursts, `notifications` FAILED growth,
  sla-sweep errors, AI provider failures, storage 502s, upload 413 spikes.
- Logs must never contain passwords/OTPs/JWTs/keys (verified by scan).

## 10b. Browser validation matrix (B-4, human/CI with browsers)
- Viewports 390 / 768 / 1440. Public: login, OTP, submit, AI verdict,
  attachment, tracking, gov states, solution, PDF, logout. Government:
  employee login, dashboard, detail, 3 routing actions, logout, deep-link
  refresh, session isolation.

## 11. Production approval gate
- Do NOT cut over until: full backend suite green, B-3 decided (real key
  or mock waiver), B-4 executed, backups verified, smoke tests green on
  staging, and explicit human approval recorded with SHAs + Alembic head.

## 7. Frontends
- `npm run build` with production `VITE_API_URL`; serve `dist/` as SPA
  with fallback-to-index (deep links must not 404).
- `api.<domain>` serves ONLY `/api/*` + `/health*`; never SPA routes.

## 8. DNS/TLS
- A records: public, government, api -> hosts; valid certs; HSTS on proxy.

## 9. Smoke tests (staging first, then prod)
Register/login -> submit -> AI verdict -> attachment up/download ->
gov employee login -> queue -> assign-public -> history -> logout ->
sweep -> notifications SENT. Monitor 5xx + FAILED notifications.

## 10. Rollback
- App: redeploy previous SHAs. DNS: revert records if changed.
- DB: restore backup (no downgrade). Storage: never delete objects on
  app rollback. Secrets: rotate if compromised.
