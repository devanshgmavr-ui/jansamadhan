import { useEffect, useState } from "react";
import { Alert } from "../components/ui";
import { govAnalyticsApi } from "../services/govApi";

function Bar({ label, value, max }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <p>
      <strong>{label}</strong> {value}
      <span style={{ display: "block", background: "#eee", borderRadius: 4 }}>
        <span style={{ display: "block", width: `${width}%`, height: 10, background: "#2a6cb6", borderRadius: 4 }} />
      </span>
    </p>
  );
}

function Line({ points }) {
  if (!points || points.length === 0) return <p>No trend data yet.</p>;
  const max = Math.max(...points.map((p) => p.count), 1);
  const step = 100 / Math.max(points.length - 1, 1);
  const path = points
    .map((p, i) => `${(i * step).toFixed(1)},${(60 - (p.count / max) * 55).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 65" style={{ width: "100%", height: 140 }} role="img" aria-label="Monthly complaint trend">
      <polyline points={path} fill="none" stroke="#2a6cb6" strokeWidth="2" />
    </svg>
  );
}

function Pie({ slices }) {
  if (!slices || slices.length === 0) return <p>No data yet.</p>;
  const total = slices.reduce((a, s) => a + s.count, 0) || 1;
  const colors = ["#2a6cb6", "#4caf50", "#ff9800", "#9c27b0", "#607d8b", "#795548"];
  const parts = slices.reduce((acc, s, i) => {
    const start = acc.length === 0 ? 0 : acc[acc.length - 1].a1;
    const end = start + (s.count / total) * 360;
    return [...acc, { ...s, a0: start, a1: end, color: colors[i % colors.length] }];
  }, []);
  const arc = (a0, a1) => {
    const r = 40;
    const rad = (d) => ((d - 90) * Math.PI) / 180;
    const x0 = 50 + r * Math.cos(rad(a0));
    const y0 = 50 + r * Math.sin(rad(a0));
    const x1 = 50 + r * Math.cos(rad(a1));
    const y1 = 50 + r * Math.sin(rad(a1));
    return `M50,50 L${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 ${a1 - a0 > 180 ? 1 : 0},1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`;
  };
  return (
    <>
      <svg viewBox="0 0 100 100" style={{ width: 180, height: 180 }} role="img" aria-label="Category distribution">
        {parts.map((p) => (
          <path key={p.category} d={arc(p.a0, p.a1)} fill={p.color} />
        ))}
      </svg>
      <ul>
        {parts.map((p) => (
          <li key={p.category}>
            <span style={{ color: p.color }}>●</span> {p.category}: {p.count}
          </li>
        ))}
      </ul>
    </>
  );
}

export function Analytics() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    govAnalyticsApi.overview().then(setData).catch((e) => setError(e.message));
  }, []);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  const cards = [
    ["Total Complaints", data.total_complaints],
    ["Pending AI Review", data.pending_ai_review],
    ["Government Review Pending", data.government_review_pending],
    ["Public Challenges", data.public_challenges],
    ["Government Issues", data.government_issues],
    ["Solutions Submitted", data.solutions_submitted],
    ["Solutions Selected", data.solutions_selected],
    ["Implementations Active", data.implementations_active],
    ["Completed Projects", data.completed_projects],
    ["Rejected Complaints", data.rejected_complaints],
  ];
  return (
    <>
      <h2>Administrator Analytics</h2>
      <section className="grid-3">
        {cards.map(([label, value]) => (
          <div className="card" key={label}>
            <h3>{value}</h3>
            <p>{label}</p>
          </div>
        ))}
      </section>
      <div className="card">
        <h3>Average Resolution Time</h3>
        <p>
          {data.average_resolution_seconds == null
            ? "No decided reviews yet."
            : `${Math.round(data.average_resolution_seconds / 3600)} hours`}
        </p>
      </div>
      <div className="card">
        <h3>Monthly Complaint Trend</h3>
        <Line points={data.monthly_trend} />
      </div>
      <div className="card">
        <h3>Status Distribution</h3>
        <Bar label="Challenges" value={data.public_challenges} max={data.total_approved || data.total_complaints} />
        <Bar label="Government Issues" value={data.government_issues} max={data.total_approved || data.total_complaints} />
        <Bar label="Completed" value={data.completed_projects} max={data.total_approved || data.total_complaints} />
        <Bar label="Rejected" value={data.rejected_complaints} max={data.total_approved || data.total_complaints} />
      </div>
      <div className="card">
        <h3>Top Categories</h3>
        <Pie slices={data.top_categories} />
      </div>
      <div className="card">
        <h3>Top Locations</h3>
        <ul>
          {data.top_locations.map((l) => (
            <li key={l.location}>{l.location}: {l.count}</li>
          ))}
          {data.top_locations.length === 0 && <li>None yet.</li>}
        </ul>
      </div>
      <div className="card">
        <h3>Most Active Solver Types</h3>
        <ul>
          {data.solver_account_types.map((s) => (
            <li key={s.account_type}>{s.account_type}: {s.count} solutions</li>
          ))}
          {data.solver_account_types.length === 0 && <li>None yet.</li>}
        </ul>
      </div>
      <div className="card">
        <h3>Most Solved Categories</h3>
        <ul>
          {data.most_solved_categories.map((s) => (
            <li key={s.category}>{s.category}: {s.count}</li>
          ))}
          {data.most_solved_categories.length === 0 && <li>None yet.</li>}
        </ul>
      </div>
    </>
  );
}
