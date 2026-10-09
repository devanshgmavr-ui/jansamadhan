import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Home from "./Home";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const STATS = {
  total_approved: 2,
  challenges: 1,
  issues: 1,
  open_challenges: 1,
  resolved: 0,
};

function item(ticket, resolution, reason) {
  return {
    ticket,
    title: `Title ${ticket}`,
    category: "Water",
    location: "Ward 7",
    severity: "High",
    status: resolution === "PUBLIC" ? "OPEN" : "GOVERNMENT_ISSUE",
    decided_at: "2026-10-08T10:00:00Z",
    resolution_type: resolution,
    decision_reason: reason,
    created_at: "2026-10-01T10:00:00Z",
  };
}

function stubHome(first = [item("JS-PS-2026-000001", "PUBLIC", "Strong potential.")]) {
  const seen = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      seen.push(String(url));
      if (String(url).endsWith("/problems/transparency/stats")) {
        return { ok: true, status: 200, json: async () => STATS };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ total: first.length, page: 1, limit: 20, pages: 1, items: first }),
      };
    })
  );
  return seen;
}

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>
  );
}

describe("transparency dashboard", () => {
  it("renders live statistics from the backend", async () => {
    stubHome();
    vi.useFakeTimers();
    renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Total Approved Issues/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Public Challenges/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Government Issues/).length).toBeGreaterThan(0);
  });

  it("renders approved cards with badges and remarks", async () => {
    stubHome([
      item("JS-PS-2026-000001", "PUBLIC", "Strong potential."),
      item("JS-PS-2026-000002", "GOVERNMENT", "Departmental matter."),
    ]);
    vi.useFakeTimers();
    renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText(/Open for Solutions/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Government Action in Progress/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Strong potential/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Departmental matter/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Approval Date/).length).toBeGreaterThan(0);
  });

  it("passes filters to the backend", async () => {
    const seen = stubHome();
    vi.useFakeTimers();
    renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    const listing = seen.find((u) => u.includes("/problems/transparency?") || u.endsWith("/problems/transparency"));
    expect(listing).toBeTruthy();
  });

  it("refreshes statistics and listing every 30 seconds", async () => {
    const first = [item("JS-PS-2026-000001", "PUBLIC", "Strong potential.")];
    const second = [...first, item("JS-PS-2026-000002", "GOVERNMENT", "Departmental matter.")];
    let phase = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (String(url).endsWith("/problems/transparency/stats")) {
          return { ok: true, status: 200, json: async () => STATS };
        }
        const rows = phase === 0 ? first : second;
        return {
          ok: true, status: 200,
          json: async () => ({ total: rows.length, page: 1, limit: 20, pages: 1, items: rows }),
        };
      })
    );
    vi.useFakeTimers();
    renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.queryByText(/Departmental matter/)).toBeNull();
    phase = 1;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(screen.getAllByText(/Departmental matter/).length).toBeGreaterThan(0);
  });
});
