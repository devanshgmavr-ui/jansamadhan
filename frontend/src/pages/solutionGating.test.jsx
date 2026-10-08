import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "../context/useAuth";
import { BrowseProblems } from "./Problems";
import { ProblemSolutions } from "./Solutions";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function solutionListFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ items: [], total: 0 }),
    }))
  );
}

function renderSolutions(status, isOwner) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{
          user: { id: "u1", account_type: "individual" },
          initializing: false,
        }}
      >
        <ProblemSolutions
          problemTicket="JS-PS-2026-000001"
          isOwner={isOwner}
          problemStatus={status}
        />
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe("solution submission gating", () => {
  it("offers submission for OPEN problems to eligible users", async () => {
    solutionListFetch();
    renderSolutions("OPEN", false);
    await waitFor(() => {
      expect(screen.getByText("Submit Solution")).toBeTruthy();
    });
  });

  it("hides submission for government-review states with an explanation", async () => {
    for (const status of [
      "GOV_REVIEW_PENDING",
      "MORE_INFORMATION_REQUIRED",
      "GOVERNMENT_ISSUE",
      "AUTO_ESCALATED",
      "UNDER_REVIEW",
    ]) {
      solutionListFetch();
      const { unmount } = renderSolutions(status, false);
      await waitFor(() => {
        expect(
          screen.getByText(
            "Solution submission is available after the problem is assigned to the public."
          )
        ).toBeTruthy();
      });
      expect(screen.queryByText("Submit Solution")).toBeNull();
      unmount();
      vi.unstubAllGlobals();
    }
  });

  it("keeps the owner self-submission rule visible", async () => {
    solutionListFetch();
    renderSolutions("OPEN", true);
    await waitFor(() => {
      expect(screen.queryByText("Submit Solution")).toBeNull();
      expect(
        screen.getByText(/cannot submit one yourself/, { exact: false })
      ).toBeTruthy();
    });
  });
});

describe("public problems page", () => {
  it("never offers government-review statuses as filters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ total: 0, page: 1, limit: 10, pages: 0, items: [] }),
      }))
    );
    const { container } = render(
      <MemoryRouter>
        <BrowseProblems />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(container.textContent).toMatch(/No problems match/);
    });
    const options = [...container.querySelectorAll("select option")].map(
      (o) => o.getAttribute("value")
    );
    expect(options).toContain("OPEN");
    for (const hidden of [
      "GOV_REVIEW_PENDING",
      "MORE_INFORMATION_REQUIRED",
      "GOVERNMENT_ISSUE",
      "AUTO_ESCALATED",
    ]) {
      expect(options).not.toContain(hidden);
    }
  });
});
