import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, Field } from "../components/ui";
import { useAuth } from "../context/useAuth";
import { canSubmitSolutions } from "../services/problemStatus";
import { solutionsApi } from "../services/api";

const PDF_GUIDE = [
  "Solution Title", "Problem Statement", "Proposed Solution",
  "How it addresses the problem", "Methodology / Approach",
  "Technology and Resources", "Implementation Plan", "Expected Impact",
  "Scalability", "Estimated Cost / Resources", "Team / Contributors",
  "Research / References",
];

export function SubmitSolution() {
  const { ticket } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({ title: "", short_description: "", skills: "", expected_impact: "", contributors: "", estimated_resources: "" });
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!file) { setError("A solution PDF is required."); return; }
    setBusy(true);
    try {
      const res = await solutionsApi.submit(ticket, form, file);
      navigate(`/solutions/${res.ticket}`, { state: { fresh: true } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card" style={{ maxWidth: 680 }}>
      <h2>Submit Solution</h2>
      <p>For problem <span className="badge">{ticket}</span> (locked — the solution stays linked to this ticket).</p>
      <Alert>{error}</Alert>
      <form onSubmit={submit}>
        <Field label="Solution Title"><input required minLength={5} maxLength={200} onChange={set("title")} /></Field>
        <Field label="Short Description"><textarea required minLength={20} rows={3} onChange={set("short_description")} /></Field>
        <Field label="Skills / Technologies"><input maxLength={500} onChange={set("skills")} /></Field>
        <Field label="Expected Impact"><textarea required minLength={10} rows={3} onChange={set("expected_impact")} /></Field>
        <Field label="Contributors / Team Members"><input maxLength={500} onChange={set("contributors")} /></Field>
        <Field label="Estimated Resources"><input maxLength={500} onChange={set("estimated_resources")} /></Field>
        <Field label="Solution PDF (required, max 15 MB)">
          <input required type="file" accept=".pdf,application/pdf" onChange={(e) => setFile(e.target.files[0])} />
        </Field>
        <div className="card" style={{ marginBottom: "0.9rem" }}>
          <h3>Expected PDF structure</h3>
          <ul>{PDF_GUIDE.map((g) => <li key={g}>{g}</li>)}</ul>
        </div>
        <button className="btn" disabled={busy} type="submit">{busy ? "Submitting..." : "Submit Solution"}</button>
      </form>
    </div>
  );
}

export function SolutionDetail() {
  const { ticket } = useParams();
  const [sol, setSol] = useState(null);
  const [error, setError] = useState("");
  // Navigation-provided flag is read once as initial state so no effect
  // needs to synchronize it into state after mount.
  const [fresh] = useState(() => Boolean(window.history.state?.usr?.fresh));
  useEffect(() => {
    solutionsApi.get(ticket).then(setSol).catch((e) => setError(e.message));
  }, [ticket]);

  if (error) return <Alert>{error}</Alert>;
  if (!sol) return <p>Loading...</p>;
  return (
    <>
      {fresh && <div className="alert success">Solution submitted successfully. Problem Ticket: <strong>{sol.problem_ticket}</strong> · Solution Ticket: <strong>{sol.ticket}</strong></div>}
      <h2>{sol.title}</h2>
      <p><span className="badge">{sol.ticket}</span> <span className="badge ok">{sol.status.replace(/_/g, " ")}</span></p>
      <div className="card">
        <dl className="kv">
          <div style={{ display: "contents" }}><dt>Problem</dt><dd><Link to={`/problems/${sol.problem_ticket}`}>{sol.problem_ticket}</Link></dd></div>
          <div style={{ display: "contents" }}><dt>Submitted by</dt><dd>{sol.submitter_account_type}</dd></div>
          <div style={{ display: "contents" }}><dt>Skills</dt><dd>{sol.skills || "—"}</dd></div>
          <div style={{ display: "contents" }}><dt>Contributors</dt><dd>{sol.contributors || "—"}</dd></div>
          <div style={{ display: "contents" }}><dt>Resources</dt><dd>{sol.estimated_resources || "—"}</dd></div>
          <div style={{ display: "contents" }}><dt>PDF</dt><dd><a href={solutionsApi.downloadUrl(sol.ticket)} target="_blank" rel="noreferrer">{sol.pdf_name}</a></dd></div>
        </dl>
        <h3>Short Description</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{sol.short_description}</p>
        <h3>Expected Impact</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{sol.expected_impact}</p>
      </div>
      <div className="btn-row">
        <Link className="btn secondary" to={`/solutions/${sol.ticket}/track`}>Track Solution</Link>
        {sol.mine && <Link className="btn secondary" to={`/solutions/${sol.ticket}/edit`}>Edit Solution</Link>}
      </div>
    </>
  );
}

export function EditSolution() {
  const { ticket } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    solutionsApi.get(ticket).then((s) => {
      if (!s.mine) {
        setError("Only the solution owner can edit this solution.");
        return;
      }
      setForm({
        title: s.title,
        short_description: s.short_description,
        skills: s.skills || "",
        expected_impact: s.expected_impact,
        contributors: s.contributors || "",
        estimated_resources: s.estimated_resources || "",
      });
    }).catch((e) => setError(e.message));
  }, [ticket]);
  if (error) return <Alert>{error}</Alert>;
  if (!form) return <p>Loading...</p>;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const body = {};
      Object.entries(form).forEach(([k, v]) => { if (v) body[k] = v; });
      await solutionsApi.update(ticket, body);
      navigate(`/solutions/${ticket}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="form-card" style={{ maxWidth: 680 }}>
      <h2>Edit Solution</h2>
      <p>Ticket <span className="badge">{ticket}</span> stays unchanged. The PDF document cannot be replaced here.</p>
      <Alert>{error}</Alert>
      <form onSubmit={submit}>
        <Field label="Solution Title"><input required minLength={5} maxLength={200} value={form.title} onChange={set("title")} /></Field>
        <Field label="Short Description"><textarea required minLength={20} rows={3} value={form.short_description} onChange={set("short_description")} /></Field>
        <Field label="Skills / Technologies"><input maxLength={500} value={form.skills} onChange={set("skills")} /></Field>
        <Field label="Expected Impact"><textarea required minLength={10} rows={3} value={form.expected_impact} onChange={set("expected_impact")} /></Field>
        <Field label="Contributors / Team Members"><input maxLength={500} value={form.contributors} onChange={set("contributors")} /></Field>
        <Field label="Estimated Resources"><input maxLength={500} value={form.estimated_resources} onChange={set("estimated_resources")} /></Field>
        <button className="btn" disabled={busy} type="submit">{busy ? "Saving..." : "Save Changes"}</button>
      </form>
    </div>
  );
}

export function SolutionTrack() {
  const { ticket } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    solutionsApi.track(ticket).then(setData).catch((e) => setError(e.message));
  }, [ticket]);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  return (
    <>
      <h2>Track Solution</h2>
      <p><span className="badge">{data.ticket}</span> <span className="badge ok">{data.status.replace(/_/g, " ")}</span></p>
      <div className="card">
        {data.stages.map((s, i) => (
          <p key={s.key}>{s.state === "done" ? "●" : s.state === "current" ? "◐" : "○"} <strong>{i + 1}. {s.label}</strong> {s.state === "current" && <span className="badge warn">current</span>}</p>
        ))}
      </div>
      <div className="btn-row"><Link className="btn secondary" to={`/solutions/${ticket}`}>View Solution</Link></div>
    </>
  );
}

export function MySolutions() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    solutionsApi.mine(0, 50).then((d) => { setItems(d.items); setTotal(d.total); })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <h2>My Solutions</h2>
      <Alert>{error}</Alert>
      {items.length === 0 && !error && <div className="card"><p>You have not submitted any solutions yet. Discover an approved problem to solve.</p></div>}
      {items.map((s) => (
        <div className="card" key={s.ticket} style={{ marginBottom: "0.8rem" }}>
          <p><span className="badge">{s.ticket}</span> <span className="badge ok">{s.status.replace(/_/g, " ")}</span></p>
          <h3 style={{ margin: "0.3rem 0" }}><Link to={`/solutions/${s.ticket}`}>{s.title}</Link></h3>
          <p>For <Link to={`/problems/${s.problem_ticket}`}>{s.problem_ticket}</Link></p>
        </div>
      ))}
      <p>Total: {total}</p>
    </>
  );
}

export function BrowseSolutions() {
  const LIMIT = 10;
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const load = (p) => {
    solutionsApi.browse((p - 1) * LIMIT, LIMIT).then((d) => { setItems(d.items); setTotal(d.total); setPage(p); })
      .catch((e) => setError(e.message));
  };
  useEffect(() => { load(1); }, []);
  const pages = Math.max(1, Math.ceil(total / LIMIT));
  return (
    <>
      <h2>Solutions</h2>
      <Alert>{error}</Alert>
      {items.length === 0 && !error && <div className="card"><p>No solutions published yet.</p></div>}
      {items.map((s) => (
        <div className="card" key={s.ticket} style={{ marginBottom: "0.8rem" }}>
          <p><span className="badge">{s.ticket}</span> <span className="badge ok">{s.status.replace(/_/g, " ")}</span></p>
          <h3 style={{ margin: "0.3rem 0" }}><Link to={`/solutions/${s.ticket}`}>{s.title}</Link></h3>
          <p>For <Link to={`/problems/${s.problem_ticket}`}>{s.problem_ticket}</Link></p>
        </div>
      ))}
      <p>Total: {total}</p>
      {pages > 1 && (
        <div className="btn-row">
          <button className="btn secondary" disabled={page <= 1} onClick={() => load(1)}>First</button>
          <button className="btn secondary" disabled={page <= 1} onClick={() => load(page - 1)}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button className="btn secondary" disabled={page >= pages} onClick={() => load(page + 1)}>Next</button>
          <button className="btn secondary" disabled={page >= pages} onClick={() => load(pages)}>Last</button>
        </div>
      )}
    </>
  );
}

export function ProblemSolutions({ problemTicket, isOwner, problemStatus }) {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  useEffect(() => {
    solutionsApi.forProblem(problemTicket, 0, 20).then((d) => setItems(d.items)).catch(() => setItems([]));
  }, [problemTicket]);
  // UI-level eligibility only; the backend still enforces which problems
  // accept solutions. Non-open problems explain why submission is absent.
  const open = canSubmitSolutions(problemStatus);
  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <h3>Solutions ({items.length})</h3>
      {items.length === 0 && <p>{open ? "No solutions submitted yet." : "Solutions open once the problem is assigned to the public."}</p>}
      {items.map((s) => (
        <p key={s.ticket}><Link to={`/solutions/${s.ticket}`}>{s.title}</Link> <span className="badge">{s.ticket}</span> <span className="badge ok">{s.status.replace(/_/g, " ")}</span></p>
      ))}
      {user && !isOwner && open && <Link className="btn" to={`/problems/${problemTicket}/submit-solution`}>Submit Solution</Link>}
      {user && !isOwner && !open && <p>Solution submission is available after the problem is assigned to the public.</p>}
      {user && isOwner && <p>As the problem owner you can review solutions here, but you cannot submit one yourself.</p>}
    </div>
  );
}
