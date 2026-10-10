import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Analytics } from "./Analytics";
import { AuditLog } from "./AuditLog";
import { NotFound } from "./NotFound";
import { Settings } from "./Settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function ok(body) {
  return { ok: true, status: 200, json: async () => body };
}

const OVERVIEW = {
  total_complaints: 5,
  pending_ai_review: 1,
  government_review_pending: 2,
  public_challenges: 1,
  government_issues: 1,
  solutions_submitted: 3,
  solutions_selected: 1,
  implementations_active: 1,
  completed_projects: 0,
  rejected_complaints: 1,
  average_resolution_seconds: 90000,
  monthly_trend: [{ month: "2026-09-01T00:00:00", count: 2 }],
  top_categories: [{ category: "Water", count: 3 }],
  top_locations: [{ location: "Ward 7", count: 2 }],
  solver_account_types: [{ account_type: "individual", count: 3 }],
  most_solved_categories: [],
};

describe("phase 4 portal pages", () => {
  it("analytics renders cards, trend, and distributions", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(OVERVIEW)));
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Administrator Analytics")).toBeTruthy();
    });
    expect(screen.getByText("Total Complaints")).toBeTruthy();
    expect(screen.getByText("Monthly Complaint Trend")).toBeTruthy();
    expect(screen.getByText("Top Categories")).toBeTruthy();
  });

  it("audit log searches and lists records", async () => {
    const seen = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        seen.push(String(url));
        return ok({ total: 1, page: 1, limit: 50, items: [{
          ticket: "JS-PS-2026-000001", action: "ASSIGNED_TO_PUBLIC",
          previous_status: "PENDING", new_status: "ASSIGNED_TO_PUBLIC",
          actor_type: "GOVERNMENT_OFFICIAL", reason: "Strong potential.",
          created_at: "2026-10-08T10:00:00Z",
        }] });
      })
    );
    render(
      <MemoryRouter>
        <AuditLog />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Audit History")).toBeTruthy();
    });
    expect(screen.getByText("ASSIGNED_TO_PUBLIC")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Action"), {
      target: { value: "ASSIGNED_TO_PUBLIC" },
    });
    fireEvent.click(screen.getByText("Search"));
    await waitFor(() => {
      expect(seen.some((u) => u.includes("action=ASSIGNED_TO_PUBLIC"))).toBe(true);
    });
  });

  it("settings lists tunables and saves", async () => {
    const puts = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, opts) => {
        if ((opts?.method ?? "GET") === "PUT") {
          puts.push(JSON.parse(opts.body));
          return ok({ key: "POLLING_INTERVAL_SECONDS", value: "45" });
        }
        return ok({ items: [{
          key: "POLLING_INTERVAL_SECONDS", value: "30", default: "30",
          purpose: "Frontend refresh interval hint", customized: false,
        }] });
      })
    );
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("System Settings")).toBeTruthy();
    });
    expect(screen.getByText("POLLING_INTERVAL_SECONDS")).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue("30"), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => {
      expect(puts).toEqual([{ value: "45" }]);
    });
  });

  it("not found page links home", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    expect(screen.getByText("Page not found")).toBeTruthy();
  });
});
