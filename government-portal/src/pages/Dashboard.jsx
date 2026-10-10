import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "../components/ui";
import { usePolling } from "../hooks/usePolling";
import { govAnalyticsApi, govRequestsApi } from "../services/govApi";

export function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [sweepMsg, setSweepMsg] = useState("");
  const [feed, setFeed] = useState([]);

  const refresh = (silent = false) => {
    if (!silent) {
      setLoading(true);
      setError("");
    }
    govRequestsApi
      .dashboard()
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        // Silent background refresh never wipes the last good state.
        if (!silent) setError(e.message);
        setLoading(false);
      });
  };

  // Conservative live refresh from server state (45s, visible tab only).
  usePolling(() => refresh(true));

  // Initial load runs once on mount with callbacks only (no synchronous
  // setState in the effect body); the Refresh button reuses refresh().
  useEffect(() => {
    let ignore = false;
    govRequestsApi
      .dashboard()      .then((d) => {
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
    govAnalyticsApi
      .feed(20)
      .then((f) => {
        if (!ignore) setFeed(f.items ?? []);
      })
      .catch(() => {});
    return () => {
      ignore = true;
    };
  }, []);

  const sweep = async () => {
    setSweepMsg("");
    try {
      const res = await govRequestsApi.sweep();
      setSweepMsg(
        `Checked ${res.evaluated} overdue ${res.evaluated === 1 ? "request" : "requests"}; escalated ${res.escalated}.`
      );
      refresh();
    } catch (e) {
      setSweepMsg(e.message);
    }
  };

  if (error) return <Alert>{error}</Alert>;
  return (
    <>
      <h2>Routing Dashboard</h2>
      <div className="btn-row" style={{ marginTop: 0, marginBottom: "1rem" }}>
        <button className="btn secondary" onClick={refresh} disabled={loading}>
          Refresh
        </button>
        <button className="btn secondary" onClick={sweep}>
          Run Escalation Check
        </button>
      </div>
      {sweepMsg && <Alert kind="info">{sweepMsg}</Alert>}
      {loading && <p>Loading...</p>}
      {data && (
        <section className="grid-3">
          <div className="card">
            <h3>Pending Review</h3>
            <p className="stat">{data.pending}</p>
            <p><Link to="/requests?status=PENDING">Open queue</Link></p>
          </div>
          <div className="card">
            <h3>Needs Attention</h3>
            <p className="stat">{data.attention}</p>
            <p><Link to="/requests?status=AUTO_ESCALATED">Open queue</Link></p>
          </div>
          <div className="card">
            <h3>More Information</h3>
            <p className="stat">{data.more_information_required}</p>
            <p><Link to="/requests?status=MORE_INFORMATION_REQUIRED">Open queue</Link></p>
          </div>
          <div className="card">
            <h3>Government Issues</h3>
            <p className="stat">{data.government_issue}</p>
            <p><Link to="/requests?status=GOVERNMENT_ISSUE">Open queue</Link></p>
          </div>
          <div className="card">
            <h3>Assigned to Public</h3>
            <p className="stat">{data.assigned_to_public}</p>
            <p><Link to="/requests?status=ASSIGNED_TO_PUBLIC">Open queue</Link></p>
          </div>
        </section>
      )}
      <p className="muted">
        Escalation runs on the backend 24-hour window; this button triggers a
        manual check. The portal performs no automatic escalation itself.
      </p>
      <div className="card">
        <h3>Recent Activity</h3>
        {feed.length === 0 && <p>No recent events.</p>}
        {feed.map((e, i) => (
          <p key={`${e.created_at}-${i}`}>
            <span className="badge">{e.kind.replace(/_/g, " ")}</span>{" "}
            <span className="badge">{e.ticket}</span>{" "}
            <span className="muted">· {new Date(e.created_at).toLocaleString()}</span>
          </p>
        ))}
      </div>
    </>
  );
}
