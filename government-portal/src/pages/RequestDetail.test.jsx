import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RequestDetail } from "./RequestDetail";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function detailPayload(review_status, extraGov = {}, history = []) {
  return {
    ticket: "JS-PS-2026-000009",
    title: "Ward water shortage",
    description: "Borewells ran dry.",
    category: "Water",
    location: "Ward 9",
    affected_group: "Families",
    severity: "High",
    desired_solution_type: "New pipeline",
    skills: null,
    supporting_info: null,
    problem_status: "GOV_REVIEW_PENDING",
    current_version: 1,
    created_at: "2026-10-06T09:00:00Z",
    updated_at: "2026-10-06T10:00:00Z",
    versions: [],
    ai_review: {
      review_number: 1,
      version_number: 1,
      provider: "mock",
      model: "mock-rules-v1",
      status: "COMPLETED",
      decision: "APPROVED",
      reason: "Clear societal problem.",
      missing_info: [],
      category: "Water",
      affected_group: "Families",
      geo_context: "General",
      problem_type: "Water Access",
      scope: "Community",
      tech_areas: ["Web"],
      tags: ["water"],
      duplicate_status: "distinct",
      similar: [],
      created_at: "2026-10-06T10:00:00Z",
    },
    government: {
      review_status,
      pending_since: "2026-10-06T10:00:00Z",
      sla_due_at: "2026-10-07T10:00:00Z",
      expired: false,
      decided_at: null,
      decided_by: null,
      escalation_flag: false,
      info_request: null,
      user_response: null,
      ...extraGov,
    },
    history: [
      {
        action: "GOV_REVIEW_CREATED",
        previous_status: null,
        new_status: "PENDING",
        actor: { kind: "system" },
        reason: null,
        created_at: "2026-10-06T10:00:00Z",
      },
      ...history,
    ],
  };
}

function mockDetail(payload, onAction) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, opts) => {
      const u = String(url);
      const method = opts?.method ?? "GET";
      if (method === "POST" && u.includes("/assign-public")) {
        onAction?.("assign", JSON.parse(opts.body));
        return { ok: true, status: 200, json: async () => ({ ticket: "T", review_status: "ASSIGNED_TO_PUBLIC", problem_status: "OPEN", decided_at: null }) };
      }
      if (method === "POST" && u.includes("/mark-government-issue")) {
        onAction?.("issue", JSON.parse(opts.body));
        return { ok: true, status: 200, json: async () => ({ ticket: "T", review_status: "GOVERNMENT_ISSUE", problem_status: "GOVERNMENT_ISSUE", decided_at: null }) };
      }
      if (method === "POST" && u.includes("/request-information")) {
        onAction?.("info", JSON.parse(opts.body));
        return { ok: true, status: 200, json: async () => ({ ticket: "T", review_status: "MORE_INFORMATION_REQUIRED", problem_status: "MORE_INFORMATION_REQUIRED", decided_at: null }) };
      }
      return { ok: true, status: 200, json: async () => payload };
    })
  );
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/requests/JS-PS-2026-000009"]}>
      <Routes>
        <Route path="/requests/:ticket" element={<RequestDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("request detail", () => {
  it("renders problem, AI review, routing state, and history", async () => {
    mockDetail(detailPayload("PENDING"));
    const rendered = renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Ward water shortage")).toBeTruthy();
    });
    expect(screen.getByText("Borewells ran dry.")).toBeTruthy();
    expect(screen.getByText("Clear societal problem.")).toBeTruthy();
    expect(screen.getByText("GOV_REVIEW_CREATED")).toBeTruthy();
    expect(rendered.container.textContent).toMatch(/system/);
  });

  it("shows all three actions while pending", async () => {
    mockDetail(detailPayload("PENDING"));
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Assign to Public")).toBeTruthy();
    });
    expect(screen.getByText("Government Issue")).toBeTruthy();
    expect(screen.getByText("Request More Information")).toBeTruthy();
  });

  it("requires a reason for government issue", async () => {
    const calls = [];
    mockDetail(detailPayload("PENDING"), (a, b) => calls.push([a, b]));
    renderDetail();
    await waitFor(() => screen.getByText("Government Issue"));
    fireEvent.click(screen.getByText("Government Issue"));
    const submit = screen.getByText("Mark Government Issue");
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Reason \(required\)/), {
      target: { value: "Needs departmental handling." },
    });
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    await waitFor(() => {
      expect(screen.getByText("Routing decision recorded.")).toBeTruthy();
    });
    expect(calls).toEqual([["issue", { reason: "Needs departmental handling." }]]);
  });

  it("requires a reason for information requests", async () => {
    const calls = [];
    mockDetail(detailPayload("PENDING"), (a, b) => calls.push([a, b]));
    renderDetail();
    await waitFor(() => screen.getByText("Request More Information"));
    fireEvent.click(screen.getByText("Request More Information"));
    expect(screen.getByText("Send Request").disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/What information is required/, { exact: false }), {
      target: { value: "Share the exact ward." },
    });
    fireEvent.click(screen.getByText("Send Request"));
    await waitFor(() => {
      expect(screen.getByText("Routing decision recorded.")).toBeTruthy();
    });
    expect(calls).toEqual([["info", { reason: "Share the exact ward." }]]);
  });

  it("hides routing actions in terminal states", async () => {
    for (const terminal of ["GOVERNMENT_ISSUE", "ASSIGNED_TO_PUBLIC"]) {
      mockDetail(detailPayload(terminal));
      const { unmount } = renderDetail();
      await waitFor(() => {
        expect(screen.getByText(/No routing actions are available/)).toBeTruthy();
      });
      expect(screen.queryByText("Assign to Public")).toBeNull();
      unmount();
      vi.unstubAllGlobals();
    }
  });

  it("hides routing actions while awaiting the user", async () => {
    mockDetail(
      detailPayload("MORE_INFORMATION_REQUIRED", {
        info_request: "Share the exact ward.",
      })
    );
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Share the exact ward.")).toBeTruthy();
    });
    expect(screen.queryByText("Assign to Public")).toBeNull();
  });

  it("labels escalated state without claiming acceptance", async () => {
    mockDetail(
      detailPayload("AUTO_ESCALATED", {
        escalation_flag: true,
        expired: true,
      })
    );
    const { container } = renderDetail();
    await waitFor(() => {
      expect(screen.getByText(/review window was exceeded/)).toBeTruthy();
    });
    // The required denial names no accepting department or ministry.
    expect(screen.getByText(/no department has accepted responsibility/)).toBeTruthy();
    expect(container.textContent).not.toMatch(/ministry/i);
  });

  it("displays backend validation errors safely", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 422, json: async () => ({ detail: "Illegal government transition." }) }))
    );
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Illegal government transition.")).toBeTruthy();
    });
  });
});
