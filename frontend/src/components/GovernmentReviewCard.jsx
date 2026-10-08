import { Link } from "react-router-dom";

// Owner-facing routing-state card (G4). Renders only from the owner-scoped
// problem payload (status + government_review block). Shows safe,
// user-relevant information only: never official identities, departments,
// portal URLs, or internal audit data. Copy rules: AI approval is never
// presented as publication; escalation never claims acceptance.
export function GovernmentReviewCard({ problem }) {
  const status = problem?.status;
  const gov = problem?.government_review ?? null;
  if (
    status !== "GOV_REVIEW_PENDING" &&
    status !== "MORE_INFORMATION_REQUIRED" &&
    status !== "GOVERNMENT_ISSUE" &&
    status !== "AUTO_ESCALATED"
  ) {
    return null;
  }
  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      {status === "GOV_REVIEW_PENDING" && (
        <>
          <h3>Government Review</h3>
          <p>
            Your problem has passed AI review and is currently awaiting
            routing review. It will become publicly available only after it
            is assigned to the public.
          </p>
          {gov?.pending_since && (
            <p>
              Awaiting review since{" "}
              {new Date(gov.pending_since).toLocaleString()}.
              {gov.expired
                ? " The review window has passed; the request is awaiting queue processing."
                : " Reviews are normally routed within 24 hours."}
            </p>
          )}
        </>
      )}
      {status === "MORE_INFORMATION_REQUIRED" && (
        <>
          <h3>More Information Required</h3>
          <p>
            Additional information has been requested before the problem can
            continue through review. Your problem remains private.
          </p>
          {gov?.info_request && (
            <div className="alert info">
              <strong>What was requested:</strong>
              <p style={{ whiteSpace: "pre-wrap" }}>{gov.info_request}</p>
            </div>
          )}
          <Link className="btn" to={`/problems/${problem.ticket}/edit`}>
            Provide Information
          </Link>
          <p>
            Updating creates a new version for re-review. Your ticket{" "}
            <strong>{problem.ticket}</strong> stays the same.
          </p>
        </>
      )}
      {status === "GOVERNMENT_ISSUE" && (
        <>
          <h3>Government Issue</h3>
          <p>
            Your problem has been identified as a government issue and is
            currently being handled through the government review process.
          </p>
        </>
      )}
      {status === "AUTO_ESCALATED" && (
        <>
          <h3>Government Review Escalated</h3>
          <p>
            The 24-hour review window was exceeded. The request has been
            escalated in the review queue.
          </p>
        </>
      )}
    </div>
  );
}
