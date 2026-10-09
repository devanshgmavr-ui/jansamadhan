// Central problem-status definition (G4). Backend enum names are
// authoritative; every label, explanation, and visibility rule derives from
// this single map so pages never duplicate status logic.
//
// Wording rules: AI approval is never presented as public publication; the
// escalated state never claims a department accepted the problem; no
// official names, departments, or portal URLs are ever referenced.

export const STATUS_META = {
  UNDER_REVIEW: {
    label: "Under AI Review",
    tone: "warn",
    description:
      "Your problem has been submitted and is going through the initial AI review.",
    publicVisible: false,
    solutionsOpen: false,
  },
  REVISION_REQUIRED: {
    label: "Needs Information",
    tone: "warn",
    description:
      "The review needs more detail before your problem can continue. Update and resubmit — your ticket stays the same.",
    publicVisible: false,
    solutionsOpen: false,
  },
  APPROVED: {
    label: "AI Approved",
    tone: "",
    description:
      "A previous review approved this submission. Current submissions continue to government routing review.",
    publicVisible: false,
    solutionsOpen: false,
  },
  REJECTED: {
    label: "Not Accepted",
    tone: "warn",
    description:
      "This submission was not accepted as a societal problem for collaborative solving.",
    publicVisible: false,
    solutionsOpen: false,
  },
  GOV_REVIEW_PENDING: {
    label: "Government Review",
    tone: "",
    description:
      "Your problem has passed the initial AI review and is now awaiting government routing review. It will become publicly available only after it is assigned to the public.",
    publicVisible: false,
    solutionsOpen: false,
  },
  MORE_INFORMATION_REQUIRED: {
    label: "More Information Required",
    tone: "warn",
    description:
      "Additional information has been requested before the problem can continue through review. Your problem remains private.",
    publicVisible: false,
    solutionsOpen: false,
  },
  GOVERNMENT_ISSUE: {
    label: "Government Action in Progress",
    tone: "",
    description:
      "Your problem has been identified as a government issue and is being handled through the government review process.",
    publicVisible: false,
    solutionsOpen: false,
  },
  AUTO_ESCALATED: {
    label: "Review Escalated",
    tone: "warn",
    description:
      "The 24-hour review window was exceeded. The request has been escalated in the review queue.",
    publicVisible: false,
    solutionsOpen: false,
  },
  OPEN: {
    label: "Open for Solutions",
    tone: "ok",
    description:
      "The problem has been assigned to the public and is now open for solutions.",
    publicVisible: true,
    solutionsOpen: true,
  },
  COLLABORATION: {
    label: "In Collaboration",
    tone: "ok",
    description: "Teams are collaborating on this problem.",
    publicVisible: true,
    solutionsOpen: true,
  },
  IN_DEVELOPMENT: {
    label: "In Development",
    tone: "ok",
    description: "A solution is under development.",
    publicVisible: true,
    solutionsOpen: true,
  },
  PILOT: {
    label: "Pilot",
    tone: "ok",
    description: "A solution is being piloted.",
    publicVisible: true,
    solutionsOpen: true,
  },
  IMPLEMENTED: {
    label: "Implemented",
    tone: "ok",
    description: "A solution has been implemented.",
    publicVisible: true,
    solutionsOpen: true,
  },
  CLOSED: {
    label: "Closed",
    tone: "",
    description: "This problem is closed.",
    publicVisible: false,
    solutionsOpen: false,
  },
};

const FALLBACK = {
  label: null, // resolved per status at call time
  tone: "",
  description: "",
  publicVisible: false,
  solutionsOpen: false,
};

export function statusMeta(status) {
  const known = STATUS_META[status];
  if (known) return known;
  return { ...FALLBACK, label: String(status ?? "").replace(/_/g, " ") || "Unknown" };
}

export function statusLabel(status) {
  return statusMeta(status).label;
}

export function statusTone(status) {
  return statusMeta(status).tone;
}

export function statusDescription(status) {
  return statusMeta(status).description;
}

/** Backend statuses whose problems strangers may discover. Mirrors the
 *  backend PUBLIC_STATUSES set; the backend remains the enforcing authority. */
export function isPublicStatus(status) {
  return statusMeta(status).publicVisible;
}

/** Whether the Solutions entry point makes sense for a problem in this
 *  status. The backend still enforces eligibility server-side. */
export function canSubmitSolutions(status) {
  return statusMeta(status).solutionsOpen;
}

/** Short timeline notes for track stages served by the backend. */
export const STAGE_NOTES = {
  submitted: "Your problem was received and given a permanent ticket.",
  ai_review: "Automated review checks relevance, completeness, and duplication.",
  classified: "The problem was classified by domain, geography, and affected group.",
  government_review:
    "AI-approved problems wait here for routing. Only assignment to the public makes a problem visible to everyone.",
  open: "Assigned to the public: anyone eligible can now submit solutions.",
  collaboration: "Contributors are forming teams around solutions.",
  development: "A solution is being built.",
  pilot: "A solution is being tried out in the field.",
  implemented: "A solution has been implemented and recorded.",
};

export function stageNote(key) {
  return STAGE_NOTES[key] ?? "";
}
