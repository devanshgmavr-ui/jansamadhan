import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../context/useAuth";
import { ProblemStatusBadge } from "../components/ui";
import { contribApi, problemsApi } from "../services/api";

function KV({ data }) {
  if (!data) return <p>No additional profile information.</p>;
  return (
    <dl className="kv">
      {Object.entries(data).map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k.replace(/_/g, " ")}</dt>
          <dd>{v || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    contribApi.dashboard().then(setData).catch((e) => setError(e.message));
  }, []);
  if (error) return <p>{error}</p>;
  if (!data) return <p>Loading dashboard...</p>;
  const c = data.counts;
  return (
    <>
      <h2>My Dashboard</h2>
      <p>Account type: <span className="badge">{user.account_type}</span></p>
      <section className="grid-3">
        <div className="card"><h3>Problems</h3><p style={{ fontSize: "1.6rem", margin: 0 }}>{c.problems}</p><p><Link to="/my-problems">My Problems</Link></p></div>
        <div className="card"><h3>Solutions</h3><p style={{ fontSize: "1.6rem", margin: 0 }}>{c.solutions}</p><p><Link to="/my-solutions">My Solutions</Link></p></div>
        <div className="card"><h3>Contributions</h3><p style={{ fontSize: "1.6rem", margin: 0 }}>{c.contributions}</p><p><Link to="/my-contributions">My Contributions</Link> ({c.contributions_accepted} accepted)</p></div>
      </section>
      <section className="grid-3">
        <div className="card">
          <h3>Recent Problems</h3>
          {data.recent_problems.length === 0 && <p>None yet.</p>}
          {data.recent_problems.map((p) => <p key={p.ticket}><Link to={`/problems/${p.ticket}`}>{p.title}</Link> <ProblemStatusBadge status={p.status} /></p>)}
        </div>
        <div className="card">
          <h3>Recent Solutions</h3>
          {data.recent_solutions.length === 0 && <p>None yet.</p>}
          {data.recent_solutions.map((s) => <p key={s.ticket}><Link to={`/solutions/${s.ticket}`}>{s.title}</Link> <span className="badge">{s.status.replace(/_/g, " ")}</span></p>)}
        </div>
        <div className="card">
          <h3>Recent Contributions</h3>
          {data.recent_contributions.length === 0 && <p>None yet.</p>}
          {data.recent_contributions.map((x) => <p key={x.id}>{x.type.replace(/_/g, " ")} <span className="badge">{x.status}</span></p>)}
        </div>
      </section>
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Collaborations</h3>
        {data.collaborations.length === 0 && <p>No team memberships yet.</p>}
        {data.collaborations.map((x) => <p key={x.id + x.role}><Link to={`/collaborations/${x.id}`}>{x.title}</Link> <span className="badge">{x.role.replace(/_/g, " ")}</span> <span className="badge">{x.membership}</span></p>)}
        <p><Link to="/my-collaborations">My Collaborations</Link></p>
      </div>
      {data.skills && <div className="card" style={{ marginTop: "1rem" }}><h3>My Skills</h3><p>{data.skills}</p></div>}
      {user.account_type === "student" && data.profile?.college && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3>My Institution</h3>
          <p>{data.profile.college}{data.profile.course ? ` — ${data.profile.course}` : ""}{data.profile.year ? ` (Year ${data.profile.year})` : ""}</p>
          <p><Link to="/my-contributions">My Contributions</Link> · <Link to="/my-solutions">My Solutions</Link></p>
        </div>
      )}
      {user.account_type === "university" && data.profile?.university_name && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3>Institution Profile</h3>
          <p><strong>{data.profile.university_name}</strong></p>
          <p>{[data.profile.institution_type, data.profile.location].filter(Boolean).join(" · ") || "—"}</p>
          {data.profile.website && <p><a href={data.profile.website} target="_blank" rel="noreferrer">{data.profile.website}</a></p>}
          <p><Link to="/my-problems">Problems Submitted</Link> · <Link to="/my-collaborations">Collaborations</Link></p>
        </div>
      )}
      {user.account_type === "organization" && data.profile?.organization_name && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3>Organization Profile</h3>
          <p><strong>{data.profile.organization_name}</strong></p>
          <p>{[data.profile.organization_type, data.profile.industry, data.profile.location].filter(Boolean).join(" · ") || "—"}</p>
          <p><Link to="/my-problems">Problems Submitted</Link> · <Link to="/my-solutions">Solutions Submitted</Link> · <Link to="/my-collaborations">Collaborations</Link></p>
        </div>
      )}
      {user.account_type === "individual" && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3>My Activity</h3>
          <p>Problems: {c.problems} · Solutions: {c.solutions} · Contributions: {c.contributions}</p>
          {data.profile?.interests && <p>Areas of interest: {data.profile.interests}</p>}
        </div>
      )}
      <NotificationHistory />
    </>
  );
}

export function NotificationHistory() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    problemsApi.myNotifications(50).then((d) => setItems(d.items ?? [])).catch(() => setItems([]));
  }, []);
  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <h3>Notification History ({items.length})</h3>
      {items.length === 0 && <p>No notifications yet.</p>}
      {items.map((n, i) => (
        <p key={`${n.created_at}-${i}`}>
          <strong>{n.subject}</strong>{" "}
          <span className="badge">{n.ticket}</span>{" "}
          <span className="badge">{n.status}</span>
          <br />
          <span className="muted">{new Date(n.created_at).toLocaleString()}</span>
        </p>
      ))}
    </div>
  );
}

export function Profile() {
  const { user } = useAuth();
  return (
    <>
      <h2>My Profile</h2>
      <div className="card">
        <dl className="kv">
          <div style={{ display: "contents" }}><dt>Account type</dt><dd>{user.account_type}</dd></div>
          <div style={{ display: "contents" }}><dt>Email</dt><dd>{user.email}</dd></div>
          <div style={{ display: "contents" }}><dt>Phone</dt><dd>{user.phone || "—"}</dd></div>
          <div style={{ display: "contents" }}><dt>First name</dt><dd>{user.first_name || "—"}</dd></div>
          <div style={{ display: "contents" }}><dt>Last name</dt><dd>{user.last_name || "—"}</dd></div>
        </dl>
        <h3>Profile Details</h3>
        <KV data={user.profile} />
      </div>
    </>
  );
}

export function Settings() {
  const { logout } = useAuth();
  return (
    <>
      <h2>Settings</h2>
      <div className="card">
        <p>Additional preferences arrive in a later stage.</p>
        <button className="btn secondary" onClick={logout}>Sign Out Everywhere (this device)</button>
      </div>
    </>
  );
}

export function ComingSoon({ title, stage }) {
  return (
    <>
      <h2>{title}</h2>
      <div className="card">
        <p>This section arrives in <strong>{stage}</strong>. Data will be loaded from the JanSamadhan database when that stage is complete.</p>
      </div>
    </>
  );
}
