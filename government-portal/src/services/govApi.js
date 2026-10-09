// Government API client. Separate session from the public website:
// sessionStorage under its own key, government endpoints only, and a 401
// clears the session (expired or revoked) so the portal returns to login.
//
// The backend target comes from the environment with a local fallback.
// VITE_* values are public by design: never put secrets here.
const BASE =
  import.meta.env.VITE_API_URL ??
  "http://127.0.0.1:8000/api/v1";

const SESSION_KEY = "gov_portal_session";

export function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export function saveSession(session) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
}

export function getToken() {
  return loadSession()?.access_token ?? null;
}

function formatDetail(detail, status) {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        const where = Array.isArray(d.loc)
          ? d.loc.filter((x) => x !== "body").join(".")
          : "";
        const msg = typeof d.msg === "string" ? d.msg : "invalid value";
        return where ? `${where}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (parts.length) return parts.slice(0, 3).join("; ");
  }
  if (status === 401) return "Session expired. Please sign in again.";
  if (status === 403) return "Access denied.";
  if (status === 404) return "Request not found.";
  if (status === 429) return "Too many attempts. Please try again later.";
  if (status >= 500) return "Server error. Please try again later.";
  return `Request failed (${status})`;
}

async function raw(path, { method = "GET", body, token } = {}) {
  const res = await fetch(`${BASE}/government${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data;
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(formatDetail(data.detail, res.status));
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export async function govApi(path, opts = {}) {
  const token = getToken();
  try {
    return await raw(path, { ...opts, token });
  } catch (err) {
    if (err.status === 401) clearSession();
    throw err;
  }
}

export const govAuthApi = {
  login: (body) => raw("/auth/login", { method: "POST", body }),
  logout: () =>
    govApi("/auth/logout", { method: "POST" }).catch(() => ({})),
  me: () => govApi("/auth/me"),
};

export const govRequestsApi = {
  dashboard: () => govApi("/dashboard"),
  queue: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    qs.set("page", String(params.page ?? 1));
    qs.set("page_size", String(params.page_size ?? 20));
    return govApi(`/requests?${qs.toString()}`);
  },
  sweep: () => govApi("/requests/sweep-escalations", { method: "POST" }),
  detail: (ticket) => govApi(`/requests/${ticket}`),
  history: (ticket) => govApi(`/requests/${ticket}/history`),
  assignPublic: (ticket, reason) =>
    govApi(`/requests/${ticket}/assign-public`, {
      method: "POST",
      body: { reason: reason || null },
    }),
  markIssue: (ticket, reason) =>
    govApi(`/requests/${ticket}/mark-government-issue`, {
      method: "POST",
      body: { reason },
    }),
  requestInfo: (ticket, reason) =>
    govApi(`/requests/${ticket}/request-information`, {
      method: "POST",
      body: { reason },
    }),
  requestSolutions: (ticket) => govApi(`/requests/${ticket}/solutions`),
  reviewSolution: (ticket, decision, reason) =>
    govApi(`/solutions/${ticket}/review`, {
      method: "POST",
      body: { decision, reason: reason || null },
    }),
  selectSolution: (ticket) =>
    govApi(`/solutions/${ticket}/select`, { method: "POST" }),
  listImplementation: (ticket) => govApi(`/requests/${ticket}/implementation`),
  async createImplementation(ticket, { stage, title, description, files }) {
    const token = getToken();
    const form = new FormData();
    form.append("stage", stage);
    form.append("title", title);
    if (description) form.append("description", description);
    (files || []).forEach((f) => form.append("files", f));
    const res = await fetch(`${BASE}/government/requests/${ticket}/implementation`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    let data;
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    if (!res.ok) {
      const err = new Error(formatDetail(data.detail, res.status));
      err.status = res.status;
      throw err;
    }
    return data;
  },
};
