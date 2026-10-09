import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { GovernmentReviewCard } from "./GovernmentReviewCard";
import { ProblemStatusBadge } from "./ui";

afterEach(cleanup);

function renderCard(problem) {
  return render(
    <MemoryRouter>
      <GovernmentReviewCard problem={problem} />
    </MemoryRouter>
  );
}

const base = {
  ticket: "JS-PS-2026-000001",
  title: "Water shortage",
  status: "GOV_REVIEW_PENDING",
  government_review: {
    review_status: "PENDING",
    info_request: null,
    pending_since: "2026-10-06T10:00:00Z",
    sla_due_at: "2026-10-07T10:00:00Z",
    expired: false,
    escalation_flag: false,
  },
};

describe("ProblemStatusBadge", () => {
  it("renders government routing labels with text, not color alone", () => {
    const { container } = render(<ProblemStatusBadge status="GOV_REVIEW_PENDING" />);
    expect(container.textContent).toBe("Government Review");
    expect(container.querySelector("span").className).toMatch(/badge/);
  });

  it("renders every routing state distinctly", () => {
    for (const [status, label] of [
      ["MORE_INFORMATION_REQUIRED", "More Information Required"],
      ["GOVERNMENT_ISSUE", "Government Action in Progress"],
      ["AUTO_ESCALATED", "Review Escalated"],
      ["OPEN", "Open for Solutions"],
    ]) {
      const { unmount } = render(<ProblemStatusBadge status={status} />);
      expect(screen.getByText(label)).toBeTruthy();
      unmount();
    }
  });
});

describe("GovernmentReviewCard", () => {
  it("explains pending review without promising publication", () => {
    renderCard(base);
    expect(screen.getByText("Government Review")).toBeTruthy();
    expect(
      screen.getByText(/awaiting routing review/, { exact: false })
    ).toBeTruthy();
  });

  it("shows the information request with a provide-information action", () => {
    renderCard({
      ...base,
      status: "MORE_INFORMATION_REQUIRED",
      government_review: {
        ...base.government_review,
        review_status: "MORE_INFORMATION_REQUIRED",
        info_request: "Share the exact ward and household count.",
      },
    });
    expect(screen.getByText("More Information Required")).toBeTruthy();
    expect(
      screen.getByText("Share the exact ward and household count.")
    ).toBeTruthy();
    const link = screen.getByText("Provide Information");
    expect(link.getAttribute("href")).toBe("/problems/JS-PS-2026-000001/edit");
    // Ticket stability: the same ticket is referenced, never a new one.
    expect(screen.getByText("JS-PS-2026-000001")).toBeTruthy();
  });

  it("presents government issues without departments or portals", () => {
    renderCard({ ...base, status: "GOVERNMENT_ISSUE", government_review: null });
    expect(screen.getByText("Government Action in Progress")).toBeTruthy();
  });

  it("presents escalation without claiming acceptance", () => {
    const { container } = renderCard({
      ...base,
      status: "AUTO_ESCALATED",
      government_review: { ...base.government_review, expired: true, escalation_flag: true },
    });
    expect(screen.getByText("Government Review Escalated")).toBeTruthy();
    expect(container.textContent).not.toMatch(/accept|department/i);
  });

  it("renders nothing for public or pre-routing states", () => {
    for (const status of ["OPEN", "UNDER_REVIEW", "REJECTED", "COLLABORATION"]) {
      const { container, unmount } = renderCard({ ...base, status });
      expect(container.textContent).toBe("");
      unmount();
    }
  });

  it("exposes no internal identifiers", () => {
    const { container } = renderCard(base);
    expect(container.textContent).not.toMatch(/official|actor|jti|portal/i);
  });
});
