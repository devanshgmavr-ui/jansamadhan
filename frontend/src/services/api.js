// Central API client. Attaches the access token, refreshes it once on 401,
// and clears the session when refresh fails.

// Backend target comes from the environment so separate deployments
// (local, staging, production) can point at their own API. The fallback
// preserves plain local development. VITE_* values are public by design:
// never put secrets (JWT keys, DB passwords, provider API keys) here.
const BASE =
  import.meta.env.VITE_API_URL ??
  "http://127.0.0.1:8000/api/v1";

function loadTokens() {
  try {
    return JSON.parse(localStorage.getItem("js_tokens") || "null");
  } catch {
    return null;
  }
}

export function saveTokens(tokens) {
  localStorage.setItem("js_tokens", JSON.stringify(tokens));
}

export function clearTokens() {
  localStorage.removeItem("js_tokens");
}

export function getTokens() {
  return loadTokens();
}

async function raw(path, { method = "GET", body, token } = {}) {
  const res = await fetch(BASE + path, {
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

function formatDetail(detail, status) {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      const where = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
      const msg = typeof d.msg === "string" ? d.msg : "invalid value";
      return where ? `${where}: ${msg}` : msg;
    }).filter(Boolean);
    if (parts.length) return parts.slice(0, 3).join("; ");
  }
  if (status === 401) return "Authentication failed. Please sign in again.";
  if (status === 403) return "You are not allowed to perform this action.";
  if (status === 429) return "Too many attempts. Please try again later.";
  if (status === 404) return "Not found.";
  if (status >= 500) return "Server error. Please try again later.";
  return `Request failed (${status})`;
}

async function refreshTokens() {
  const tokens = loadTokens();
  if (!tokens?.refresh_token) throw new Error("No session.");
  const next = await raw("/auth/refresh", {
    method: "POST",
    body: { refresh_token: tokens.refresh_token },
  });
  saveTokens(next);
  return next;
}

export async function api(path, opts = {}, retry = true) {
  const tokens = loadTokens();
  try {
    return await raw(path, { ...opts, token: tokens?.access_token });
  } catch (err) {
    if (err.status === 401 && retry && tokens?.refresh_token) {
      try {
        const next = await refreshTokens();
        return await raw(path, { ...opts, token: next.access_token }, false);
      } catch {
        clearTokens();
        throw new Error("Session expired. Please sign in again.");
      }
    }
    throw err;
  }
}

export const problemsApi = {
  submit: (body) => api("/problems", { method: "POST", body }),
  get: (ticket) => api(`/problems/${ticket}`),
  update: (ticket, body) => api(`/problems/${ticket}`, { method: "PUT", body }),
  history: (ticket) => api(`/problems/${ticket}/history`),
  track: (ticket) => api(`/problems/${ticket}/track`),
  browse: (params) => {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => { if (v) qs.set(k, v); });
    const q = qs.toString();
    return raw(`/problems${q ? `?${q}` : ""}`);
  },
  publicGet: (ticket) => raw(`/problems/${ticket}/public`),
  transparencyDetail: (ticket) => raw(`/problems/transparency/${ticket}`),
  implementationAttachmentUrl: (ticket, updateId, attachmentId) =>
    `${BASE}/problems/transparency/${ticket}/updates/${updateId}/attachments/${attachmentId}/download`,
  transparency: (params) => {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => { if (v) qs.set(k, v); });
    const q = qs.toString();
    return raw(`/problems/transparency${q ? `?${q}` : ""}`);
  },
  transparencyStats: () => raw("/problems/transparency/stats"),
  reviews: (ticket) => api(`/problems/${ticket}/reviews`),
  requestReview: (ticket) => api(`/problems/${ticket}/review`, { method: "POST", body: {} }),
  mine: (skip = 0, limit = 20) => api(`/users/me/problems?skip=${skip}&limit=${limit}`),
  async upload(ticket, file) {
    const tokens = getTokens();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/problems/${ticket}/attachments`, {
      method: "POST",
      headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
    return data;
  },
  downloadUrl: (ticket, id) => `${BASE}/problems/${ticket}/attachments/${id}/download`,
  removeAttachment: (ticket, id) => api(`/problems/${ticket}/attachments/${id}`, { method: "DELETE" }),
};
export const authApi = {
  register: (body) => raw("/auth/register", { method: "POST", body }),
  verifyEmail: (body) => raw("/auth/verify-email", { method: "POST", body }),
  resendOtp: (body) => raw("/auth/resend-otp", { method: "POST", body }),
  login: (body) => raw("/auth/login", { method: "POST", body }),
  logout: (refresh_token, access_token) =>
    raw("/auth/logout", { method: "POST", body: { refresh_token }, token: access_token }),
  me: () => api("/auth/me"),
  forgot: (body) => raw("/auth/forgot-password", { method: "POST", body }),
  reset: (body) => raw("/auth/reset-password", { method: "POST", body }),
};

export async function authedFetch(path, { method = "GET", form } = {}) {
  const tokens = getTokens();
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const solutionsApi = {
  submit: (problemTicket, fields, file) => {
    const form = new FormData();
    Object.entries(fields).forEach(([k, v]) => { if (v) form.append(k, v); });
    form.append("file", file);
    return authedFetch(`/problems/${problemTicket}/solutions`, { method: "POST", form });
  },
  get: (ticket) => {
    const tokens = getTokens();
    return tokens?.access_token ? api(`/solutions/${ticket}`) : raw(`/solutions/${ticket}`);
  },
  update: (ticket, body) => api(`/solutions/${ticket}`, { method: "PUT", body }),
  setStatus: (ticket, status) => api(`/solutions/${ticket}/status`, { method: "PATCH", body: { status } }),
  track: (ticket) => {
    const tokens = getTokens();
    return tokens?.access_token ? api(`/solutions/${ticket}/track`) : raw(`/solutions/${ticket}/track`);
  },
  mine: (skip = 0, limit = 20) => api(`/users/me/solutions?skip=${skip}&limit=${limit}`),
  forProblem: (problemTicket, skip = 0, limit = 20) => {
    const tokens = getTokens();
    const path = `/problems/${problemTicket}/solutions?skip=${skip}&limit=${limit}`;
    return tokens?.access_token ? api(path) : raw(path);
  },
  browse: (skip = 0, limit = 20) => raw(`/solutions?skip=${skip}&limit=${limit}`),
  downloadUrl: (ticket) => `${BASE}/solutions/${ticket}/download`,
  solutionAttachments: (ticket) => {
    const tokens = getTokens();
    const path = `/solutions/${ticket}/attachments`;
    return tokens?.access_token ? api(path) : raw(path);
  },
  async uploadSolutionAttachment(ticket, file) {
    const tokens = getTokens();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/solutions/${ticket}/attachments`, {
      method: "POST",
      headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
    return data;
  },
  removeSolutionAttachment: (ticket, id) => api(`/solutions/${ticket}/attachments/${id}`, { method: "DELETE" }),
  solutionAttachmentUrl: (ticket, id) => `${BASE}/solutions/${ticket}/attachments/${id}/download`,
};

export const contribApi = {
  create: (body) => api("/contributions", { method: "POST", body }),
  get: (id) => api(`/contributions/${id}`),
  update: (id, body) => api(`/contributions/${id}`, { method: "PUT", body }),
  remove: (id) => api(`/contributions/${id}`, { method: "DELETE" }),
  setStatus: (id, status) => api(`/contributions/${id}/status`, { method: "PATCH", body: { status } }),
  mine: (skip = 0, limit = 20) => api(`/users/me/contributions?skip=${skip}&limit=${limit}`),
  forProblem: (ticket) => api(`/problems/${ticket}/contributions`),
  dashboard: () => api("/users/me/dashboard"),
};

export const collabApi = {
  create: (body) => api("/collaborations", { method: "POST", body }),
  get: (id) => api(`/collaborations/${id}`),
  join: (id, role) => api(`/collaborations/${id}/join`, { method: "POST", body: { role } }),
  moderate: (id, mid, status) => api(`/collaborations/${id}/members/${mid}`, { method: "PATCH", body: { status } }),
  leave: (id) => api(`/collaborations/${id}/leave`, { method: "POST", body: {} }),
  setStatus: (id, status) => api(`/collaborations/${id}/status`, { method: "PATCH", body: { status } }),
  mine: () => api("/users/me/collaborations"),
  createProject: (id, body) => api(`/collaborations/${id}/projects`, { method: "POST", body }),
  project: (id) => api(`/projects/${id}`),
  setProjectStatus: (id, status) => api(`/projects/${id}/status`, { method: "PATCH", body: { status } }),
  addMilestone: (id, body) => api(`/projects/${id}/milestones`, { method: "POST", body }),
  editMilestone: (id, mid, body) => api(`/projects/${id}/milestones/${mid}`, { method: "PATCH", body }),
  removeMilestone: (id, mid) => api(`/projects/${id}/milestones/${mid}`, { method: "DELETE" }),
  addUpdate: (id, text) => api(`/projects/${id}/updates`, { method: "POST", body: { text } }),
  saveImpact: (id, body) => api(`/projects/${id}/impact`, { method: "PUT", body }),
};
