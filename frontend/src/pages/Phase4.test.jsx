import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../context/useAuth";
import { NotificationHistory } from "./Account";
import { NotFound } from "./NotFound";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("phase 4 public pages", () => {
  it("notification history lists own notifications", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ total: 1, items: [{
          ticket: "JS-PS-2026-000001",
          type: "GOV_REVIEW_PENDING",
          subject: "JanSamadhan JS-PS-2026-000001: awaiting government review",
          body: "Track it here.",
          status: "SENT",
          created_at: "2026-10-08T10:00:00Z",
        }] }),
      }))
    );
    render(
      <MemoryRouter>
        <AuthContext.Provider value={{ user: { id: "u1" }, initializing: false }}>
          <NotificationHistory />
        </AuthContext.Provider>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText(/Notification History \(1\)/)).toBeTruthy();
    });
    expect(screen.getByText(/awaiting government review/)).toBeTruthy();
  });

  it("not found page links home and tracking", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    expect(screen.getByText("Page not found")).toBeTruthy();
    expect(screen.getByText("Go to Homepage")).toBeTruthy();
  });
});
