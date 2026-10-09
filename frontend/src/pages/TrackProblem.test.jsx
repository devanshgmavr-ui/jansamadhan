import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TrackProblem } from "./Problems";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function baseTrack(overrides = {}) {
  return {
    ticket: "JS-PS-2026-000001",
    title: "Water shortage",
    status: "GOV_REVIEW_PENDING",
    current_version: 1,
    submitted_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-02T10:00:00Z",
    stages: [
      { key: "submitted", label: "Submitted", state: "done" },
      { key: "ai_review", label: "AI Review", state: "done" },
      { key: "classified", label: "Classified", state: "done" },
      { key: "government_review", label: "Government Review", state: "current" },
      { key: "open", label: "Open for Solutions", state: "pending" },
    ],
    government_review: null,
    ...overrides,
  };
}

function stubTrackSequence(responses) {
  const calls = { n: 0, track: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      calls.n++;
      if (!String(url).includes("/track")) {
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      }
      const next = responses[Math.min(calls.track++, responses.length - 1)];
      if (next instanceof Error) throw next;
      return { ok: true, status: 200, json: async () => next };
    })
  );
  return calls;
}

function renderTrack() {
  return render(
    <MemoryRouter initialEntries={["/problems/JS-PS-2026-000001/track"]}>
      <Routes>
        <Route path="/problems/:ticket/track" element={<TrackProblem />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("TrackProblem government updates", () => {
  it("shows the official information request from the snapshot", async () => {
    stubTrackSequence([
      baseTrack({
        status: "MORE_INFORMATION_REQUIRED",
        government_review: {
          review_status: "MORE_INFORMATION_REQUIRED",
          info_request: "Which ward exactly?",
          pending_since: null,
          sla_due_at: null,
          expired: false,
          escalation_flag: false,
        },
      }),
    ]);
    // Fake timers BEFORE mount: the poll interval is created in the
    // mount effect and must be fake-controlled from the start.
    vi.useFakeTimers();
    renderTrack();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText(/More information requested/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Which ward exactly?/).length).toBeGreaterThan(0);
  });

  it("refreshes automatically when the backend status changes", async () => {
    const calls = stubTrackSequence([
      baseTrack(),
      baseTrack({
        status: "OPEN",
        updated_at: "2026-10-03T10:00:00Z",
        stages: [
          { key: "submitted", label: "Submitted", state: "done" },
          { key: "ai_review", label: "AI Review", state: "done" },
          { key: "classified", label: "Classified", state: "done" },
          { key: "government_review", label: "Government Review", state: "done" },
          { key: "open", label: "Open for Solutions", state: "current" },
        ],
      }),
    ]);
    vi.useFakeTimers();
    renderTrack();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText(/Government Review/).length).toBeGreaterThan(0);
    expect(calls.track).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
      await vi.advanceTimersByTimeAsync(100);
    });
    // Poll fired and the fresh payload rendered without a page reload.
    expect(screen.getAllByText(/Open for Solutions/).length).toBeGreaterThan(0);
    expect(calls.track).toBe(2);
  });

  it("keeps the last good snapshot when a refresh fails", async () => {
    stubTrackSequence([baseTrack(), new Error("network down")]);
    vi.useFakeTimers();
    renderTrack();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText(/Government Review/).length).toBeGreaterThan(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
      await vi.advanceTimersByTimeAsync(30000);
    });
    // Still the real backend state, never a fabricated one.
    expect(screen.getAllByText(/Government Review/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/network down/)).toBeNull();
  });

  it("shows Public Challenge resolution with the official remark", async () => {
    stubTrackSequence([
      baseTrack({
        status: "OPEN",
        government_review: {
          review_status: "ASSIGNED_TO_PUBLIC",
          info_request: null,
          pending_since: null,
          sla_due_at: null,
          expired: false,
          escalation_flag: false,
          resolution_type: "PUBLIC",
          decision_reason: "Strong community potential.",
        },
      }),
    ]);
    vi.useFakeTimers();
    renderTrack();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText(/Resolution Type/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Public Challenge/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Strong community potential/).length).toBeGreaterThan(0);
  });

  it("shows Government Issue resolution with the official remark", async () => {
    stubTrackSequence([
      baseTrack({
        status: "GOVERNMENT_ISSUE",
        government_review: {
          review_status: "GOVERNMENT_ISSUE",
          info_request: null,
          pending_since: null,
          sla_due_at: null,
          expired: false,
          escalation_flag: false,
          resolution_type: "GOVERNMENT",
          decision_reason: "Requires departmental handling.",
        },
      }),
    ]);
    vi.useFakeTimers();
    renderTrack();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getAllByText(/Resolution Type/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Government Issue/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Requires departmental handling/).length).toBeGreaterThan(0);
  });
});



