import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, Field } from "../components/ui";
import { useAuth } from "../context/useAuth";
import { collabApi } from "../services/api";

const ROLES = ["STUDENT_CONTRIBUTOR", "UNIVERSITY_REPRESENTATIVE", "ORGANIZATION_REPRESENTATIVE", "RESEARCH_CONTRIBUTOR", "TECHNICAL_CONTRIBUTOR", "SOLUTION_CONTRIBUTOR", "COLLABORATION"];

export function MyCollaborations() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ problem_ticket: "", solution_ticket: "", title: "", description: "" });
  const [info, setInfo] = useState("");

  const load = () => collabApi.mine()
    .then((d) => { setItems(d.items); setTotal(d.total); })
    .catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      const body = { ...form };
      if (!body.solution_ticket) delete body.solution_ticket;
      const res = await collabApi.create(body);
      setInfo(`Collaboration created: ${res.title}`);
      setForm({ problem_ticket: "", solution_ticket: "", title: "", description: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <h2>My Collaborations</h2>
      <Alert>{error}</Alert>
      <Alert kind="success">{info}</Alert>
      <div className="form-card" style={{ maxWidth: 680, margin: "0 0 1rem" }}>
        <h3>Start a Collaboration</h3>
        <p>Only a problem owner or one of its solution contributors can start a collaboration around that problem.</p>
        <form onSubmit={create}>
          <Field label="Problem Ticket"><input required value={form.problem_ticket} onChange={(e) => setForm({ ...form, problem_ticket: e.target.value })} placeholder="JS-PS-YYYY-XXXXXX" /></Field>
          <Field label="Solution Ticket (optional)"><input value={form.solution_ticket} onChange={(e) => setForm({ ...form, solution_ticket: e.target.value })} placeholder="JS-SOL-YYYY-XXXXXX" /></Field>
          <Field label="Title"><input required minLength={5} maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Description"><textarea required minLength={20} rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <button className="btn" type="submit">Create</button>
        </form>
      </div>
      {items.map((c) => (
        <div className="card" key={c.id} style={{ marginBottom: "0.8rem" }}>
          <p><span className="badge ok">{c.status.replace(/_/g, " ")}</span> <span className="badge">{c.role.replace(/_/g, " ")}</span> <span className="badge">{c.membership}</span></p>
          <h3 style={{ margin: "0.3rem 0" }}><Link to={`/collaborations/${c.id}`}>{c.title}</Link></h3>
          {c.problem_ticket && <p>Problem <Link to={`/problems/${c.problem_ticket}`}>{c.problem_ticket}</Link></p>}
        </div>
      ))}
      <p>Total: {total}</p>
    </div>
  );
}

export function CollaborationDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [role, setRole] = useState("STUDENT_CONTRIBUTOR");
  const [proj, setProj] = useState({ title: "", description: "" });

  const load = useCallback(() => collabApi.get(id).then(setData).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, okMsg) => {
    setError("");
    try {
      await fn();
      load();
    } catch (e) {
      setError(e.message);
    }
    void okMsg;
  };

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  const collabProblemUrl = "/problems/" + data.problem_ticket;
  const collabSolutionUrl = data.solution_ticket ? "/solutions/" + data.solution_ticket : null;
  return (
    <div>
      <h2>{data.title}</h2>
      <p><span className="badge ok">{data.status.replace(/_/g, " ")}</span></p>
      {data.is_manager && (
        <div className="btn-row" style={{ marginBottom: "1rem" }}>
          {data.status === "ACTIVE" && (
            <button className="btn secondary" onClick={() => act(() => collabApi.setStatus(id, "PAUSED"))}>Pause Collaboration</button>
          )}
          {data.status === "PAUSED" && (
            <button className="btn secondary" onClick={() => act(() => collabApi.setStatus(id, "ACTIVE"))}>Resume Collaboration</button>
          )}
          {(data.status === "ACTIVE" || data.status === "PAUSED" || data.status === "COMPLETED") && (
            <button className="btn secondary" onClick={() => { if (window.confirm("Close this collaboration? History is preserved.")) act(() => collabApi.setStatus(id, "CLOSED")); }}>Close Collaboration</button>
          )}
        </div>
      )}
      <div className="card">
        <p style={{ whiteSpace: "pre-wrap" }}>{data.description}</p>
        <p>Problem <Link to={collabProblemUrl}>{data.problem_ticket}</Link></p>
        {collabSolutionUrl && (<p>Solution <Link to={collabSolutionUrl}>{data.solution_ticket}</Link></p>)}
        {data.project_id
          ? <p>Project: <Link to={`/projects/${data.project_id}`}>Open project</Link> <span className="badge">{data.project_status}</span></p>
          : data.is_manager && (
            <form onSubmit={(e) => { e.preventDefault(); act(() => collabApi.createProject(id, proj)); }}>
              <Field label="New Project Title"><input required minLength={5} value={proj.title} onChange={(e) => setProj({ ...proj, title: e.target.value })} /></Field>
              <Field label="Project Description"><textarea required minLength={20} rows={2} value={proj.description} onChange={(e) => setProj({ ...proj, description: e.target.value })} /></Field>
              <button className="btn secondary" type="submit">Start Project</button>
            </form>
          )}
      </div>
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Members</h3>
        {data.members.map((m) => (
          <p key={m.id}>
            {m.account_type} · {m.role.replace(/_/g, " ")} · <span className="badge">{m.status}</span>
            {m.is_self && " (you)"}{" "}
            {data.is_manager && m.status === "PENDING" && (
              <span>
                <button className="btn secondary" onClick={() => act(() => collabApi.moderate(id, m.id, "ACTIVE"))}>Accept</button>{" "}
                <button className="btn secondary" onClick={() => act(() => collabApi.moderate(id, m.id, "REMOVED"))}>Reject</button>
              </span>
            )}
            {data.is_manager && m.status === "ACTIVE" && !m.is_self && (
              <span> <button className="btn secondary" onClick={() => act(() => collabApi.moderate(id, m.id, "REMOVED"))}>Remove</button></span>
            )}
          </p>
        ))}
        <Field label="Request to join (role)">
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
          </select>
        </Field>
        <div className="btn-row">
          <button className="btn secondary" onClick={() => act(() => collabApi.join(id, role))}>Request to Join</button>
          <button className="btn secondary" onClick={() => act(() => collabApi.leave(id))}>Leave</button>
        </div>
      </div>
    </div>
  );
}

export function ProjectDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [ms, setMs] = useState({ title: "", description: "", due_date: "" });
  const [upd, setUpd] = useState("");
  const [impact, setImpact] = useState({ affected_population: "", outcomes: "", evidence: "", notes: "" });

  const load = useCallback(() => collabApi.project(id).then((d) => {
    setData(d);
    if (d.impact) setImpact({ affected_population: d.impact.affected_population || "", outcomes: d.impact.outcomes || "", evidence: d.impact.evidence || "", notes: d.impact.notes || "" });
  }).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn) => {
    setError("");
    try {
      await fn();
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  const nextMap = { DEVELOPMENT: "PROTOTYPE", PROTOTYPE: "PILOT", PILOT: "IMPLEMENTATION", IMPLEMENTATION: "IMPACT_RECORDED", IMPACT_RECORDED: "CLOSED" };
  const problemUrl = "/problems/" + data.problem_ticket;
  const solutionUrl = data.solution_ticket ? "/solutions/" + data.solution_ticket : null;
  return (
    <div>
      <h2>{data.title}</h2>
      <p><span className="badge ok">{data.status.replace(/_/g, " ")}</span></p>
      <div className="card">
        <p style={{ whiteSpace: "pre-wrap" }}>{data.description}</p>
        <p>Problem <Link to={problemUrl}>{data.problem_ticket}</Link></p>
        {solutionUrl && (<p>Solution <Link to={solutionUrl}>{data.solution_ticket}</Link></p>)}
        {nextMap[data.status] && (
          <button className="btn" onClick={() => act(() => collabApi.setProjectStatus(id, nextMap[data.status]))}>
            Advance to {nextMap[data.status].replace(/_/g, " ")}
          </button>
        )}
      </div>
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Milestones</h3>
        {data.milestones.length === 0 && <p>No milestones yet.</p>}
        {data.milestones.map((m) => (
          <div key={m.id} style={{ borderTop: "1px solid var(--line)", paddingTop: "0.5rem", marginTop: "0.5rem" }}>
            <p><strong>{m.title}</strong> <span className="badge">{m.status}</span> {m.due_date && <span>due {m.due_date}</span>}</p>
            {m.description && <p>{m.description}</p>}
            {m.status !== "DONE" && <button className="btn secondary" onClick={() => act(() => collabApi.editMilestone(id, m.id, { status: "DONE" }))}>Mark Done</button>}{" "}
            <button className="btn secondary" onClick={() => { if (window.confirm(`Delete milestone "${m.title}"?`)) act(() => collabApi.removeMilestone(id, m.id)); }}>Delete</button>
          </div>
        ))}
        <Field label="New milestone title"><input value={ms.title} onChange={(e) => setMs({ ...ms, title: e.target.value })} /></Field>
        <Field label="Description"><input value={ms.description} onChange={(e) => setMs({ ...ms, description: e.target.value })} /></Field>
        <Field label="Due date (optional)"><input type="date" value={ms.due_date} onChange={(e) => setMs({ ...ms, due_date: e.target.value })} /></Field>
        <div className="btn-row"><button className="btn secondary" onClick={() => act(async () => {
          if (!ms.title) throw new Error("Milestone title is required.");
          await collabApi.addMilestone(id, { title: ms.title, description: ms.description || undefined, due_date: ms.due_date || undefined, owner_id: user.id });
          setMs({ title: "", description: "", due_date: "" });
        })}>Add Milestone (owner: you)</button></div>
      </div>
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Progress Updates</h3>
        {data.updates.length === 0 && <p>No updates yet.</p>}
        {data.updates.map((u) => <p key={u.id} style={{ whiteSpace: "pre-wrap" }}>{u.text} <span className="badge">{new Date(u.created_at).toLocaleDateString()}</span></p>)}
        <Field label="New update"><textarea rows={2} value={upd} onChange={(e) => setUpd(e.target.value)} /></Field>
        <button className="btn secondary" onClick={() => { act(() => collabApi.addUpdate(id, upd)).then(() => setUpd("")); }}>Post Update</button>
      </div>
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Impact</h3>
        <Field label="Affected population"><input value={impact.affected_population} onChange={(e) => setImpact({ ...impact, affected_population: e.target.value })} /></Field>
        <Field label="Measurable outcomes"><textarea rows={2} value={impact.outcomes} onChange={(e) => setImpact({ ...impact, outcomes: e.target.value })} /></Field>
        <Field label="Evidence"><textarea rows={2} value={impact.evidence} onChange={(e) => setImpact({ ...impact, evidence: e.target.value })} /></Field>
        <Field label="Notes"><textarea rows={2} value={impact.notes} onChange={(e) => setImpact({ ...impact, notes: e.target.value })} /></Field>
        <button className="btn secondary" onClick={() => act(() => collabApi.saveImpact(id, impact))}>Save Impact</button>
      </div>
    </div>
  );
}
