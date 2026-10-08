import { afterEach, describe, expect, it, vi } from "vitest";
import { problemsApi } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("public API boundary", () => {
  it("calls only the public backend, never government or AI endpoints", async () => {
    const seen = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        seen.push(String(url));
        return { ok: true, status: 200, json: async () => ({ items: [], total: 0 }) };
      })
    );
    await problemsApi.browse({ page: 1, limit: 5 }).catch(() => ({}));
    expect(seen.length).toBeGreaterThan(0);
    for (const url of seen) {
      expect(url).not.toMatch(/\/government\//);
      expect(url).not.toMatch(/openrouter|openai|anthropic|gemini/i);
    }
  });
});
