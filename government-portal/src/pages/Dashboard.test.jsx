import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "./Dashboard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

const COUNTS = {
  pending: 3,
  attention: 7,
  government_issue: 2,
  assigned_to_public: 5,
  more_information_required: 4,
};

function mockDashboard(counts = COUNTS) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      if (String(url).includes("/government/dashboard")) {
        return { ok: true, status: 200, json: async () => counts };
      }
      return { ok: true, status: 200, json: async () => ({ evaluated: 0, escalated: 0, escalated_tickets: [] }) };
    })
  );
}

describe("dashboard", () => {
  it("renders server-provided counts without inventing data", async () => {
    mockDashboard();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Pending Review")).toBeTruthy();
    });
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.queryByText(/chart|analytics/i)).toBeNull();
  });

  it("runs the escalation check and refreshes", async () => {
    const calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, opts) => {
        calls.push(`${opts?.method ?? "GET"} ${url}`);
        if (String(url).includes("sweep-escalations")) {
          return { ok: true, status: 200, json: async () => ({ evaluated: 2, escalated: 1, escalated_tickets: ["T"] }) };
        }
        return { ok: true, status: 200, json: async () => COUNTS };
      })
    );
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );
    await waitFor(() => screen.getByText("Run Escalation Check"));
    fireEvent.click(screen.getByText("Run Escalation Check"));
    await waitFor(() => {
      expect(screen.getByText(/Checked 2 overdue requests; escalated 1/)).toBeTruthy();
    });
    expect(calls.some((c) => c.startsWith("POST") && c.includes("sweep-escalations"))).toBe(true);
  });

  it("shows backend errors safely", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({ detail: "db exploded" }) }))
    );
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("db exploded")).toBeTruthy();
    });
  });
});
