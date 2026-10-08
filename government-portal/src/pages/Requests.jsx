import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Field, ReviewStatusBadge } from "../components/ui";
import { usePolling } from "../hooks/usePolling";
import { govRequestsApi } from "../services/govApi";
import { formatDue } from "../utils/sla";

const FILTERS = [
  ["", "All"],
  ["PENDING", "Pending"],
  ["AUTO_ESCALATED", "Needs Attention"],
  ["MORE_INFORMATION_REQUIRED", "More Information Required"],
  ["GOVERNMENT_ISSUE", "Government Issue"],
  ["ASSIGNED_TO_PUBLIC", "Assigned to Public"],
];

export function Requests() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get("status") ?? "";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = (page, silent = false) => {
    if (!silent) {
      setLoading(true);
      setError("");
    }
    govRequestsApi
      .queue({ status: status || undefined, page, page_size: 10 })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (!silent) setError(e.message);
        setLoading(false);
      });
  };

  // Initial (and filter-change) load runs on status change with callbacks
  // only; buttons call load() directly as event handlers.
  useEffect(() => {
    let ignore = false;
    govRequestsApi
      .queue({ status: status || undefined, page: 1, page_size: 10 })
      .then((d) => {
        if (!ignore) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!ignore) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [status]);

  // Conservative live refresh of the current page (45s, visible tab only).
  usePolling(() => load(data?.page ?? 1, true));

  const gotoPage = (page) => load(page);

  return (
    <>
      <h2>Review Queue</h2>
      <div className="card">
        <Field label="Status">
          <select
            value={status}
            onChange={(e) => setSearchParams(e.target.value ? { status: e.target.value } : {})}
          >
            {FILTERS.map(([value, label]) => (
              <option key={value || "all"} value={value}>{label}</option>
            ))}
          </select>
        </Field>
        <div className="btn-row">
          <button className="btn secondary" onClick={() => load(data?.page ?? 1)}>
            Refresh
          </button>
        </div>
      </div>
      <Alert>{error}</Alert>
      {loading && <p>Loading...</p>}
      {data && data.total === 0 && !loading && (
        <div className="card"><p>No government review requests found.</p></div>
      )}
      {data &&
        data.items.map((r) => (
          <div className="card" key={r.ticket}>
            <p>
              <span className="badge">{r.ticket}</span>{" "}
              <ReviewStatusBadge status={r.review_status} />{" "}
              {r.escalation_flag && <span className="badge warn">Needs Attention</span>}{" "}
              {r.expired && r.review_status === "PENDING" && (
                <span className="badge warn">Overdue</span>
              )}
            </p>
            <h3 style={{ margin: "0.3rem 0" }}>
              <Link to={`/requests/${r.ticket}`}>{r.title}</Link>
            </h3>
            <p className="muted">
              {r.category} · {r.location} · {r.affected_group}
            </p>
            <p className="muted">
              SLA due {new Date(r.sla_due_at).toLocaleString()} ({formatDue(r.sla_due_at)})
            </p>
          </div>
        ))}
      {data && data.pages > 1 && (
        <div className="btn-row">
          <button
            className="btn secondary"
            disabled={data.page <= 1}
            onClick={() => gotoPage(data.page - 1)}
          >
            Previous
          </button>
          <span>Page {data.page} of {data.pages} ({data.total} total)</span>
          <button
            className="btn secondary"
            disabled={data.page >= data.pages}
            onClick={() => gotoPage(data.page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
