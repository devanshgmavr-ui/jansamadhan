import { describe, expect, it } from "vitest";
import {
  canSubmitSolutions,
  isPublicStatus,
  stageNote,
  statusDescription,
  statusLabel,
  statusTone,
} from "./problemStatus";

// Backend enum names are authoritative: every known Problem.status must map.
describe("status mapping", () => {
  it("labels the government routing states in user language", () => {
    expect(statusLabel("GOV_REVIEW_PENDING")).toBe("Government Review");
    expect(statusLabel("MORE_INFORMATION_REQUIRED")).toBe("More Information Required");
    expect(statusLabel("GOVERNMENT_ISSUE")).toBe("Government Action in Progress");
    expect(statusLabel("AUTO_ESCALATED")).toBe("Review Escalated");
    expect(statusLabel("OPEN")).toBe("Open for Solutions");
  });

  it("labels the pre-routing and legacy states", () => {
    expect(statusLabel("UNDER_REVIEW")).toBe("Under AI Review");
    expect(statusLabel("REVISION_REQUIRED")).toBe("Needs Information");
    expect(statusLabel("REJECTED")).toBe("Not Accepted");
    expect(statusLabel("COLLABORATION")).toBe("In Collaboration");
    expect(statusLabel("IN_DEVELOPMENT")).toBe("In Development");
    expect(statusLabel("PILOT")).toBe("Pilot");
    expect(statusLabel("IMPLEMENTED")).toBe("Implemented");
  });

  it("falls back gracefully for unknown statuses", () => {
    expect(statusLabel("SOMETHING_NEW")).toBe("SOMETHING NEW");
    expect(statusTone("SOMETHING_NEW")).toBe("");
  });

  it("never presents AI approval as publication", () => {
    expect(statusDescription("GOV_REVIEW_PENDING")).toMatch(/awaiting government routing review/);
    expect(statusDescription("GOV_REVIEW_PENDING")).not.toMatch(/now public|now open|already public/i);
  });

  it("escalation copy never claims acceptance", () => {
    const text = statusDescription("AUTO_ESCALATED");
    expect(text).toMatch(/escalated/);
    expect(text).not.toMatch(/accept|department|assur/i);
  });

  it("government issue copy names no department or official", () => {
    const text = statusDescription("GOVERNMENT_ISSUE");
    expect(text).not.toMatch(/department|official|ministry|portal/i);
  });

  it("marks only public lifecycle states discoverable", () => {
    for (const s of ["OPEN", "COLLABORATION", "IN_DEVELOPMENT", "PILOT", "IMPLEMENTED"]) {
      expect(isPublicStatus(s)).toBe(true);
    }
    for (const s of [
      "UNDER_REVIEW",
      "REVISION_REQUIRED",
      "REJECTED",
      "GOV_REVIEW_PENDING",
      "MORE_INFORMATION_REQUIRED",
      "GOVERNMENT_ISSUE",
      "AUTO_ESCALATED",
      "CLOSED",
    ]) {
      expect(isPublicStatus(s)).toBe(false);
    }
  });

  it("opens solutions only for public lifecycle states", () => {
    for (const s of ["OPEN", "COLLABORATION", "IN_DEVELOPMENT", "PILOT", "IMPLEMENTED"]) {
      expect(canSubmitSolutions(s)).toBe(true);
    }
    for (const s of [
      "GOV_REVIEW_PENDING",
      "MORE_INFORMATION_REQUIRED",
      "GOVERNMENT_ISSUE",
      "AUTO_ESCALATED",
      "UNDER_REVIEW",
    ]) {
      expect(canSubmitSolutions(s)).toBe(false);
    }
  });

  it("documents every backend track stage", () => {
    for (const key of [
      "submitted",
      "ai_review",
      "classified",
      "government_review",
      "open",
      "collaboration",
      "development",
      "pilot",
      "implemented",
    ]) {
      expect(stageNote(key).length).toBeGreaterThan(0);
    }
    expect(stageNote("government_review")).toMatch(/routing/i);
  });
});
