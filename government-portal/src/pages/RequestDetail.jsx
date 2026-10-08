import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, Field, ReviewStatusBadge } from "../components/ui";
import { govRequestsApi } from "../services/govApi";
import { formatDue } from "../utils/sla";

const ROUTABLE = ["PENDING", "AUTO_ESCALATED"];

function ActionDialog({ title, explanation, reasonLabel, submitLabel, optional = false, onClose, onSubmit }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const valid = optional || reason.trim().length > 0;

  const submit = async (e) => {
    e.preventDefault();
    if (!valid) {
      setError("A reason is required.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(reason.trim());
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>{title}</h3>
        <p>{explanation}</p>
        <form onSubmit={submit}>
          <Field label={reasonLabel}>
            <textarea
              required={!optional}
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <Alert>{error}</Alert>
          <div className="btn-row">
            <button className="btn" type="submit" disabled={busy || !valid}>
              {busy ? "Submitting..." : submitLabel}
            </button>
            <button className="btn secondary" type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function RequestDetail() {
  const { ticket } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    govRequestsApi
      .detail(ticket)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [ticket]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;

  const gov = data.government;
  const routable = ROUTABLE.includes(gov.review_status);

  const afterAction = async (fn) => {
    await fn();
    setNotice("Routing decision recorded.");
    load();
  };

  return (
    <>
      <p>
        <Link to="/requests">← Review Queue</Link>
      </p>
      <h2>{data.title}</h2>
      <p>
        <span className="badge">{data.ticket}</span>{" "}
        <ReviewStatusBadge status={gov.review_status} />{" "}
        {gov.escalation_flag && <span className="badge warn">Needs Attention</span>}
      </p>
      {notice && <Alert kind="success">{notice}</Alert>}
      <div className="card">
        <dl className="kv">
          <dt>Category</dt><dd>{data.category}</dd>
          <dt>Location</dt><dd>{data.location}</dd>
          <dt>Affected group</dt><dd>{data.affected_group}</dd>
          <dt>Severity</dt><dd>{data.severity}</dd>
          <dt>Solution needed</dt><dd>{data.desired_solution_type}</dd>
          <dt>Skills</dt><dd>{data.skills || "—"}</dd>
          <dt>Submitted</dt><dd>{new Date(data.created_at).toLocaleString()}</dd>
          <dt>Problem status</dt><dd>{data.problem_status}</dd>
        </dl>
        <h3>Description</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{data.description}</p>
        {data.supporting_info && (
          <>
            <h3>Supporting Information</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{data.supporting_info}</p>
          </>
        )}
      </div>
      {data.ai_review && (
        <div className="card">
          <h3>AI Review</h3>
          <p>
            <span className="badge">{data.ai_review.decision ?? data.ai_review.status}</span>{" "}
            <span className="badge">review #{data.ai_review.review_number}</span>
          </p>
          <dl className="kv">
            <dt>Category</dt><dd>{data.ai_review.category ?? "—"}</dd>
            <dt>Affected group</dt><dd>{data.ai_review.affected_group ?? "—"}</dd>
            <dt>Geography</dt><dd>{data.ai_review.geo_context ?? "—"}</dd>
            <dt>Problem type</dt><dd>{data.ai_review.problem_type ?? "—"}</dd>
            <dt>Scope</dt><dd>{data.ai_review.scope ?? "—"}</dd>
            <dt>Similarity</dt><dd>{data.ai_review.duplicate_status ?? "—"}</dd>
          </dl>
          {data.ai_review.reason && <p>{data.ai_review.reason}</p>}
        </div>
      )}
      <div className="card">
        <h3>Routing State</h3>
        <dl className="kv">
          <dt>Review status</dt><dd>{gov.review_status}</dd>
          <dt>Pending since</dt><dd>{new Date(gov.pending_since).toLocaleString()}</dd>
          <dt>SLA due</dt>
          <dd>
            {new Date(gov.sla_due_at).toLocaleString()} ({formatDue(gov.sla_due_at)})
          </dd>
          {gov.decided_at && (
            <>
              <dt>Decided at</dt>
              <dd>{new Date(gov.decided_at).toLocaleString()}</dd>
            </>
          )}
        </dl>
        {gov.review_status === "AUTO_ESCALATED" && (
          <p>
            The 24-hour review window was exceeded. This request is escalated
            in the review queue; no department has accepted responsibility.
          </p>
        )}
        {gov.info_request && (
          <>
            <h3>Information Requested</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{gov.info_request}</p>
          </>
        )}
        {gov.user_response && (
          <>
            <h3>User Response</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{gov.user_response}</p>
          </>
        )}
      </div>
      {routable ? (
        <div className="card">
          <h3>Routing Actions</h3>
          <div className="btn-row">
            <button className="btn" onClick={() => setDialog("assign")}>
              Assign to Public
            </button>
            <button className="btn secondary" onClick={() => setDialog("issue")}>
              Government Issue
            </button>
            <button className="btn secondary" onClick={() => setDialog("info")}>
              Request More Information
            </button>
          </div>
        </div>
      ) : (
        <div className="card">
          <p className="muted">
            No routing actions are available in the current state
            ({gov.review_status}). Terminal and awaiting-user states cannot
            be re-routed from here.
          </p>
        </div>
      )}
      <div className="card">
        <h3>Action History (Audit Trail)</h3>
        {data.history.length === 0 && <p>No recorded actions yet.</p>}
        {data.history.map((h, i) => (
          <p key={`${h.created_at}-${i}`}>
            <strong>{h.action}</strong>{" "}
            <span className="badge">{h.previous_status ?? "—"} → {h.new_status}</span>{" "}
            <span className="muted">
              {h.actor.kind === "official"
                ? h.actor.employee_id ?? h.actor.full_name ?? "official"
                : "system"}{" "}
              · {new Date(h.created_at).toLocaleString()}
            </span>
            {h.reason && <><br />{h.reason}</>}
          </p>
        ))}
      </div>
      {dialog === "assign" && (
        <ActionDialog
          title="Assign to Public"
          explanation="This will make the problem eligible for the public problem-solving workflow (solutions, collaboration, projects)."
          reasonLabel="Note for the audit record (optional)"
          submitLabel="Assign to Public"
          optional
          onClose={() => setDialog(null)}
          onSubmit={(reason) =>
            afterAction(() =>
              govRequestsApi.assignPublic(ticket, reason || undefined)
            )
          }
        />
      )}
      {dialog === "issue" && (
        <ActionDialog
          title="Government Issue"
          explanation="The problem stays out of the public workflow and is handled as a government-side issue."
          reasonLabel="Reason (required)"
          submitLabel="Mark Government Issue"
          onClose={() => setDialog(null)}
          onSubmit={(reason) => afterAction(() => govRequestsApi.markIssue(ticket, reason))}
        />
      )}
      {dialog === "info" && (
        <ActionDialog
          title="Request More Information"
          explanation="The submitting user will see this request on their own dashboard and can respond; the ticket stays the same."
          reasonLabel="What information is required? (required)"
          submitLabel="Send Request"
          onClose={() => setDialog(null)}
          onSubmit={(reason) => afterAction(() => govRequestsApi.requestInfo(ticket, reason))}
        />
      )}
    </>
  );
}
