import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Requests } from "./Requests";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function item(ticket, review_status, extra = {}) {
  return {
    ticket,
    title: `Title ${ticket}`,
    category: "Water",
    location: "Ward 1",
    affected_group: "Families",
    problem_status: "GOV_REVIEW_PENDING",
    review_status,
    pending_since: "2026-10-06T10:00:00Z",
    sla_due_at: "2026-10-07T10:00:00Z",
    expired: false,
    escalation_flag: false,
    decided_at: null,
    created_at: "2026-10-06T09:00:00Z",
    ...extra,
  };
}

function mockQueue(pages) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => ({
      ok: true,
      status: 200,
      json: async () => pages(String(url)),
    }))
  );
}

describe("review queue", () => {
  it("renders queue rows with SLA information", async () => {
    mockQueue(() => ({
      total: 1,
      page: 1,
      page_size: 10,
      pages: 1,
      items: [item("JS-PS-2026-000007", "PENDING")],
    }));
    render(
      <MemoryRouter>
        <Requests />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("JS-PS-2026-000007")).toBeTruthy();
    });
    // "Pending" appears both as the row badge and as the filter option.
    expect(screen.getAllByText("Pending").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/SLA due/, { exact: false })).toBeTruthy();
  });

  it("flags overdue and escalated requests", async () => {
    mockQueue(() => ({
      total: 2,
      page: 1,
      page_size: 10,
      pages: 1,
      items: [
        item("T-OVERDUE", "PENDING", { expired: true }),
        item("T-ESC", "AUTO_ESCALATED", { escalation_flag: true }),
      ],
    }));
    render(
      <MemoryRouter>
        <Requests />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("Overdue")).toBeTruthy();
    });
    // "Needs Attention" appears both as the escalation flag and the filter.
    expect(screen.getAllByText("Needs Attention").length).toBeGreaterThanOrEqual(2);
  });

  it("filters by status through the API", async () => {
    const seen = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        seen.push(String(url));
        return { ok: true, status: 200, json: async () => ({ total: 0, page: 1, page_size: 10, pages: 0, items: [] }) };
      })
    );
    render(
      <MemoryRouter>
        <Requests />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("No government review requests found.")).toBeTruthy();
    });
    const select = document.querySelector("select");
    fireEvent.change(select, { target: { value: "GOVERNMENT_ISSUE" } });
    await waitFor(() => {
      expect(seen.some((u) => u.includes("status=GOVERNMENT_ISSUE"))).toBe(true);
    });
  });

  it("paginates through the API", async () => {
    const seen = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        seen.push(String(url));
        const page = new URL(url, "http://x").searchParams.get("page");
        return {
          ok: true,
          status: 200,
          json: async () => ({
            total: 3,
            page: Number(page),
            page_size: 2,
            pages: 2,
            items: [item(`T-P${page}-A`, "PENDING"), item(`T-P${page}-B`, "PENDING")],
          }),
        };
      })
    );
    render(
      <MemoryRouter>
        <Requests />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("T-P1-A")).toBeTruthy();
    });
    fireEvent.click(screen.getByText("Next"));
    await waitFor(() => {
      expect(screen.getByText("T-P2-A")).toBeTruthy();
    });
    expect(seen.some((u) => u.includes("page=2"))).toBe(true);
  });
});
