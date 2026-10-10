import { useEffect, useState } from "react";
import { Alert } from "../components/ui";
import { govAnalyticsApi } from "../services/govApi";

function toCsv(items) {
  const headers = ["ticket", "action", "previous_status", "new_status", "actor_type", "reason", "created_at"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [headers.join(","), ...items.map((r) => headers.map((h) => esc(r[h])).join(","))].join("\n");
}

export function AuditLog() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ official: "", action: "", ticket: "", date_from: "", date_to: "" });

  const load = () => {
    govAnalyticsApi.audit({ ...filters, page: 1, limit: 100 }).then((d) => {
      setItems(d.items ?? []);
      setTotal(d.total ?? 0);
      setError("");
    }).catch((e) => setError(e.message));
  };

  useEffect(() => {
    govAnalyticsApi.audit({ page: 1, limit: 100 }).then((d) => {
      setItems(d.items ?? []);
      setTotal(d.total ?? 0);
    }).catch((e) => setError(e.message));
  }, []);

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  const exportCsv = () => {
    const blob = new Blob([toCsv(items)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-history.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <h2>Audit History</h2>
      <form className="card" onSubmit={(e) => { e.preventDefault(); load(); }}>
        <div className="btn-row">
          <label>Official <input value={filters.official} onChange={set("official")} placeholder="Employee ID" /></label>
          <label>Action <input value={filters.action} onChange={set("action")} placeholder="Action" /></label>
          <label>Complaint <input value={filters.ticket} onChange={set("ticket")} placeholder="Ticket" /></label>
          <label>From <input type="date" value={filters.date_from} onChange={set("date_from")} /></label>
          <label>To <input type="date" value={filters.date_to} onChange={set("date_to")} /></label>
          <button className="btn secondary" type="submit">Search</button>
          <button className="btn secondary" type="button" onClick={exportCsv}>Export CSV</button>
        </div>
      </form>
      {error && <Alert>{error}</Alert>}
      <p className="muted">Showing {items.length} of {total}.</p>
      {items.map((r, i) => (
        <div className="card" key={`${r.created_at}-${i}`}>
          <p>
            <strong>{r.action}</strong>{" "}
            <span className="badge">{r.previous_status || "—"} → {r.new_status}</span>{" "}
            <span className="badge">{r.ticket}</span>
          </p>
          <p className="muted">
            {r.actor_type || "system"} · {new Date(r.created_at).toLocaleString()}
          </p>
          {r.reason && <p>{r.reason}</p>}
        </div>
      ))}
      {items.length === 0 && !error && <p>No audit records match.</p>}
    </>
  );
}
