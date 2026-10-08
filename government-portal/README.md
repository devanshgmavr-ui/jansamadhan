# JanSamadhan — Government Review Portal

Authorized government review interface for routing AI-approved societal
problems. This is a **separate application** from the public JanSamadhan
website: it shares the backend API and database, never public UI code.

JanSamadhan is an independent civic platform; this portal is an authorized
review interface, not a government-branded website. No emblems, ministry
logos, or official seals are used here.

## Develop

    npm install
    npm run dev        # http://localhost:5174

Point at a backend with `VITE_API_URL` (see `.env.example`).

## Test / lint / build

    npm test
    npm run lint
    npm run build

## Notes

- Government sessions use `sessionStorage` (per-tab). No refresh tokens:
  an expired session returns to `/login`.
- The backend is authoritative for routing state and the 24-hour SLA.
  "Run escalation check" triggers the server-side sweep; the portal never
  escalates on its own timers.
