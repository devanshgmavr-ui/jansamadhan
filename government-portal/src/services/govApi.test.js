import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearSession,
  getToken,
  govAuthApi,
  govRequestsApi,
  saveSession,
} from "./govApi";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function mockFetch(handler) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, opts) => handler(String(url), opts ?? {}))
  );
}

function ok(body) {
  return { ok: true, status: 200, json: async () => body };
}

function err(status, detail) {
  return { ok: false, status, json: async () => ({ detail }) };
}

describe("session handling", () => {
  it("stores and clears the government session", () => {
    expect(getToken()).toBeNull();
    saveSession({ access_token: "tok", token_type: "bearer" });
    expect(getToken()).toBe("tok");
    clearSession();
    expect(getToken()).toBeNull();
  });
});

describe("endpoint isolation", () => {
  it("calls only /government/* endpoints, never public auth", async () => {
    const seen = [];
    mockFetch(async (url, opts) => {
      seen.push(`${opts.method ?? "GET"} ${url}`);
      if (url.endsWith("/government/auth/login")) return ok({ access_token: "t", token_type: "bearer" });
      return ok({});
    });
    saveSession({ access_token: "t", token_type: "bearer" });
    await govAuthApi.login({ employee_id: "GOV-0001", password: "x" });
    await govAuthApi.me();
    await govRequestsApi.dashboard();
    await govRequestsApi.queue({ status: "PENDING", page: 1, page_size: 10 });
    await govRequestsApi.detail("JS-PS-2026-000001");
    await govRequestsApi.history("JS-PS-2026-000001");
    await govRequestsApi.assignPublic("JS-PS-2026-000001");
    await govRequestsApi.markIssue("JS-PS-2026-000001", "reason");
    await govRequestsApi.requestInfo("JS-PS-2026-000001", "reason");
    await govRequestsApi.sweep();
    expect(seen.length).toBeGreaterThan(0);
    for (const call of seen) {
      expect(call).toMatch(/\/government\//);
      expect(call).not.toMatch(/\/api\/v1\/auth\//);
    }
  });

  it("clears the session on 401", async () => {
    mockFetch(async () => err(401, "Session expired."));
    saveSession({ access_token: "stale", token_type: "bearer" });
    await expect(govRequestsApi.dashboard()).rejects.toThrow(/Session expired/);
    expect(getToken()).toBeNull();
  });

  it("formats errors safely without internals", async () => {
    // String details come from backend-authored safe messages and pass
    // through; structured validation errors are truncated to 3 items.
    mockFetch(async () => err(500, "Something failed."));
    saveSession({ access_token: "t", token_type: "bearer" });
    await expect(govRequestsApi.dashboard()).rejects.toThrow("Something failed.");

    mockFetch(async () => ({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          { loc: ["body", "reason"], msg: "required" },
          { loc: ["body", "x"], msg: "bad" },
          { loc: ["body", "y"], msg: "bad" },
          { loc: ["body", "z"], msg: "hidden" },
        ],
      }),
    }));
    await expect(govRequestsApi.dashboard()).rejects.toThrow(
      "reason: required; x: bad; y: bad"
    );
  });

  it("logs in with employee_id, never email or OTP fields", async () => {
    let seenBody = null;
    mockFetch(async (url, opts) => {
      if (url.endsWith("/government/auth/login")) {
        seenBody = JSON.parse(opts.body);
        return ok({ access_token: "t", token_type: "bearer" });
      }
      return ok({});
    });
    await govAuthApi.login({ employee_id: "GOV-0001", password: "x" });
    expect(seenBody).toEqual({ employee_id: "GOV-0001", password: "x" });
  });

  it("never calls an AI provider or any non-backend host", async () => {
    const seen = [];
    mockFetch(async (url) => {
      seen.push(String(url));
      if (String(url).endsWith("/government/auth/login")) {
        return ok({ access_token: "t", token_type: "bearer" });
      }
      return ok({});
    });
    saveSession({ access_token: "t", token_type: "bearer" });
    await govAuthApi.login({ employee_id: "GOV-0001", password: "x" });
    await govAuthApi.me();
    await govRequestsApi.dashboard();
    await govRequestsApi.queue({ status: "PENDING" });
    await govRequestsApi.detail("JS-PS-2026-000001");
    expect(seen.length).toBeGreaterThan(0);
    for (const url of seen) {
      expect(url).not.toMatch(/openrouter|openai|anthropic|gemini/i);
      expect(url).toMatch(/\/government\//);
    }
  });
});
