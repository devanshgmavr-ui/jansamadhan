import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "../components/ui";
import { problemsApi } from "../services/api";
import { statusLabel } from "../services/problemStatus";

const REFRESH_MS = 30000;

function resolutionBadge(item) {
  if (item.resolution_type === "PUBLIC") return "Open for Solutions";
  if (item.resolution_type === "GOVERNMENT") return "Government Action in Progress";
  return statusLabel(item.status);
}

export default function Home() {
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const loadedRef = useRef(false);
  const [filters, setFilters] = useState({
    resolution: "",
    category: "",
    severity: "",
    location: "",
    status: "",
    q: "",
  });

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      problemsApi.transparencyStats().then((s) => {
        if (!cancelled) setStats(s);
      }).catch(() => {});
      problemsApi.transparency({ ...filters, limit: 20 }).then((page) => {
        if (!cancelled) {
          loadedRef.current = true;
          setItems(page.items ?? []);
          setTotal(page.total ?? 0);
          setError("");
        }
      }).catch((e) => {
        if (!cancelled && !loadedRef.current) setError(e.message);
      });
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.resolution, filters.category, filters.severity, filters.location, filters.status, filters.q]);

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <>
      <section className="hero">
        <h1>Every Problem Deserves a Solution.</h1>
        <p>
          JanSamadhan connects people, students, universities and organizations
          to identify real-world societal problems and work together toward
          meaningful solutions.
        </p>
        <div className="btn-row">
          <Link className="btn" to="/problems">
            View Problems
          </Link>
          <Link className="btn secondary" to="/how-it-works">
            How It Works
          </Link>
        </div>
      </section>

      <section>
        <h2>Approved Issues</h2>
        {stats && (
          <div className="grid-3">
            <div className="card"><h3>{stats.total_approved}</h3><p>Total Approved Issues</p></div>
            <div className="card"><h3>{stats.challenges}</h3><p>Public Challenges</p></div>
            <div className="card"><h3>{stats.issues}</h3><p>Government Issues</p></div>
            <div className="card"><h3>{stats.open_challenges}</h3><p>Open Challenges</p></div>
            <div className="card"><h3>{stats.resolved}</h3><p>Resolved Issues</p></div>
          </div>
        )}
        <form className="card" onSubmit={(e) => e.preventDefault()}>
          <div className="btn-row">
            <label>Resolution{" "}
              <select value={filters.resolution} onChange={set("resolution")}>
                <option value="">All</option>
                <option value="PUBLIC">Public Challenge</option>
                <option value="GOVERNMENT">Government Issue</option>
              </select>
            </label>
            <label>Category{" "}
              <input value={filters.category} onChange={set("category")} placeholder="Category" />
            </label>
            <label>Priority{" "}
              <input value={filters.severity} onChange={set("severity")} placeholder="Priority" />
            </label>
            <label>Location{" "}
              <input value={filters.location} onChange={set("location")} placeholder="Location" />
            </label>
            <label>Status{" "}
              <input value={filters.status} onChange={set("status")} placeholder="Status" />
            </label>
            <label>Search{" "}
              <input value={filters.q} onChange={set("q")} placeholder="Search" />
            </label>
          </div>
        </form>
        {error && <Alert>{error}</Alert>}
        {items.length === 0 && !error && <p>No approved issues yet.</p>}
        <div className="grid-3">
          {items.map((item) => (
            <div className="card" key={item.ticket}>
              <p>
                <span className="badge">{item.ticket}</span>{" "}
                <span className="badge">{resolutionBadge(item)}</span>
              </p>
              <h3>{item.title}</h3>
              <dl className="kv">
                <dt>Category</dt><dd>{item.category}</dd>
                <dt>Location</dt><dd>{item.location}</dd>
                <dt>Priority</dt><dd>{item.severity}</dd>
                <dt>Status</dt><dd>{statusLabel(item.status)}</dd>
                {item.decided_at && (
                  <><dt>Approval Date</dt><dd>{new Date(item.decided_at).toLocaleDateString()}</dd></>
                )}
              </dl>
              {item.decision_reason && <p>{item.decision_reason}</p>}
            </div>
          ))}
        </div>
        {total > items.length && <p className="muted">Showing {items.length} of {total}.</p>}
      </section>

      <section className="grid-3">
        <div className="card">
          <h3>Raise Problems</h3>
          <p>Submit societal problems with a permanent tracking ticket.</p>
        </div>
        <div className="card">
          <h3>Propose Solutions</h3>
          <p>Share detailed solution proposals linked to real problems.</p>
        </div>
        <div className="card">
          <h3>Collaborate</h3>
          <p>Work with students, universities and organizations on impact.</p>
        </div>
      </section>
    </>
  );
}
