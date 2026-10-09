import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { ProblemContributions } from "./Contributions";
import { ProblemSolutions } from "./Solutions";
import { Alert, Field, ProblemStatusBadge } from "../components/ui";
import { GovernmentReviewCard } from "../components/GovernmentReviewCard";
import { stageNote, statusDescription } from "../services/problemStatus";
import { problemsApi } from "../services/api";

const CATEGORIES = ["Education", "Healthcare", "Agriculture", "Environment",
  "Transportation", "Water", "Energy", "Employment", "Accessibility",
  "Infrastructure", "Digital Services", "Safety", "Other"];
const SEVERITIES = ["Low", "Moderate", "High", "Critical"];

const EMPTY = { title: "", category: "", location: "", description: "",
  affected_group: "", severity: "Moderate", desired_solution_type: "",
  skills: "", supporting_info: "", revision_note: "" };

export function SubmitProblem() {
  const { ticket } = useParams();
  const editing = Boolean(ticket);
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!editing) return;
    problemsApi.get(ticket).then((p) => setForm({ ...EMPTY, ...p, revision_note: "" }))
      .catch((e) => setError(e.message));
  }, [editing, ticket]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const body = { ...form };
      if (!editing) delete body.revision_note;
      Object.keys(body).forEach((k) => { if (body[k] === "") body[k] = editing ? undefined : body[k]; });
      const res = editing
        ? await problemsApi.update(ticket, body)
        : await problemsApi.submit(body);
      navigate(`/problems/${res.ticket}`, { state: { fresh: !editing, ticket: res.ticket } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card" style={{ maxWidth: 680 }}>
      <h2>{editing ? `Revise ${ticket}` : "Submit a Problem"}</h2>
      {editing && <div className="alert info">Revising creates a new version. Your ticket number stays the same.</div>}
      <Alert>{error}</Alert>
      <form onSubmit={submit}>
        <Field label="Problem Title"><input required minLength={5} maxLength={200} value={form.title} onChange={set("title")} /></Field>
        <Field label="Category / Domain">
          <input required list="js-cats" value={form.category} onChange={set("category")} placeholder="e.g. Education" />
          <datalist id="js-cats">{CATEGORIES.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
        <Field label="Location"><input required minLength={2} maxLength={200} value={form.location} onChange={set("location")} /></Field>
        <Field label="Description"><textarea required minLength={20} rows={5} value={form.description} onChange={set("description")} /></Field>
        <Field label="Who is affected"><input required minLength={2} maxLength={500} value={form.affected_group} onChange={set("affected_group")} /></Field>
        <Field label="Severity / Impact">
          <select value={form.severity} onChange={set("severity")}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="What kind of solution is needed"><textarea required minLength={2} rows={3} value={form.desired_solution_type} onChange={set("desired_solution_type")} /></Field>
        <Field label="Skills / Solution Areas (optional)"><input maxLength={500} value={form.skills} onChange={set("skills")} /></Field>
        <Field label="Supporting information (optional)"><textarea rows={3} value={form.supporting_info} onChange={set("supporting_info")} /></Field>
        {editing && <Field label="Revision note (optional)"><input maxLength={500} value={form.revision_note} onChange={set("revision_note")} /></Field>}
        <button className="btn" disabled={busy} type="submit">{busy ? "Saving..." : editing ? "Update & Resubmit" : "Submit Problem"}</button>
      </form>
    </div>
  );
}

export function ProblemDetail() {
  const { ticket } = useParams();
  const location = useLocation();
  const { user } = useAuth();
  const [problem, setProblem] = useState(null);
  const [mode, setMode] = useState("owner");
  const [reviews, setReviews] = useState([]);
  const [error, setError] = useState("");
  const [file, setFile] = useState(null);
  const [uploadMsg, setUploadMsg] = useState("");
  const [reviewMsg, setReviewMsg] = useState("");
  const fresh = Boolean(location.state?.fresh);

  const load = useCallback(() => {
    const pub = () => problemsApi.publicGet(ticket).then((p) => {
      setProblem(p);
      setMode("public");
    }).catch((e) => setError(e.message));
    if (user) {
      problemsApi.get(ticket).then((p) => { setProblem(p); setMode("owner"); })
        .catch((e) => {
          if (e.status === 404) pub();
          else setError(e.message);
        });
      problemsApi.reviews(ticket).then(setReviews).catch(() => setReviews([]));
    } else {
      pub();
    }
  }, [ticket, user]);
  useEffect(() => { load(); }, [load]);

  const upload = async () => {
    if (!file) return;
    setUploadMsg("");
    try {
      await problemsApi.upload(ticket, file);
      setFile(null);
      setUploadMsg("Attachment uploaded.");
      load();
    } catch (e) {
      setUploadMsg(e.message);
    }
  };

  const removeAttachment = async (id, name) => {
    if (!window.confirm(`Delete attachment "${name}"? This cannot be undone.`)) return;
    setUploadMsg("");
    try {
      await problemsApi.removeAttachment(ticket, id);
      setUploadMsg("Attachment deleted.");
      load();
    } catch (e) {
      setUploadMsg(e.message);
    }
  };

  const rerunReview = async () => {
    setReviewMsg("");
    try {
      await problemsApi.requestReview(ticket);
      setReviewMsg("Review completed.");
      load();
    } catch (e) {
      setReviewMsg(e.message);
    }
  };

  const latest = reviews.length ? reviews[reviews.length - 1] : null;

  if (error) return <Alert>{error}</Alert>;
  if (!problem) return <p>Loading...</p>;
  if (mode === "public") return <PublicDetail problem={problem} />;
  return (
    <>
      {fresh && (
        <div className="alert success">
          Problem submitted successfully. Your Ticket Number is <strong>{problem.ticket}</strong>. Keep this number to track your problem.
        </div>
      )}
      <h2>{problem.title}</h2>
      <p><span className="badge">{problem.ticket}</span> <ProblemStatusBadge status={problem.status} /> <span className="badge">v{problem.current_version}</span></p>
      <p>{statusDescription(problem.status)}</p>
      <div className="card">
        <dl className="kv">
          <div style={{ display: "contents" }}><dt>Category</dt><dd>{problem.category}</dd></div>
          <div style={{ display: "contents" }}><dt>Location</dt><dd>{problem.location}</dd></div>
          <div style={{ display: "contents" }}><dt>Affected group</dt><dd>{problem.affected_group}</dd></div>
          <div style={{ display: "contents" }}><dt>Severity</dt><dd>{problem.severity}</dd></div>
          <div style={{ display: "contents" }}><dt>Solution needed</dt><dd>{problem.desired_solution_type}</dd></div>
          <div style={{ display: "contents" }}><dt>Skills</dt><dd>{problem.skills || "—"}</dd></div>
          <div style={{ display: "contents" }}><dt>Submitted</dt><dd>{new Date(problem.created_at).toLocaleString()}</dd></div>
        </dl>
        <h3>Description</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{problem.description}</p>
        {problem.supporting_info && (<><h3>Supporting Information</h3><p style={{ whiteSpace: "pre-wrap" }}>{problem.supporting_info}</p></>)}
      </div>
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>AI Review</h3>
        {!latest && problem.status === "UNDER_REVIEW" && <p>AI Review in Progress — the review usually completes within a minute of submission.</p>}
        {latest && latest.status === "FAILED" && (
          <div className="alert error">The AI review service is temporarily unavailable. Your problem is preserved and still under review. <button className="btn secondary" onClick={rerunReview}>Retry Review</button> {reviewMsg && <span>{reviewMsg}</span>}</div>
        )}
        {latest && latest.status === "COMPLETED" && (
          <>
            <p>
              <span className={`badge ${latest.decision === "APPROVED" ? "ok" : "warn"}`}>
                {latest.decision === "APPROVED" ? "Approved for Government Review" : latest.decision === "NEEDS_INFORMATION" ? "Additional Information Required" : "Submission Not Approved"}
              </span>{" "}
              <span className="badge">review #{latest.review_number} · version {latest.version_number} · {latest.provider}</span>
            </p>
            <dl className="kv">
              <div style={{ display: "contents" }}><dt>Understandable</dt><dd>{latest.understandable ? "Passed" : "Failed"}</dd></div>
              <div style={{ display: "contents" }}><dt>Sufficient information</dt><dd>{latest.sufficient_info ? "Passed" : "More information required"}</dd></div>
              <div style={{ display: "contents" }}><dt>Potentially solvable</dt><dd>{latest.solvable ? "Passed" : "Failed"}</dd></div>
              <div style={{ display: "contents" }}><dt>Similar check</dt><dd>{latest.duplicate_status}</dd></div>
              <div style={{ display: "contents" }}><dt>Problem type</dt><dd>{latest.problem_type}</dd></div>
              <div style={{ display: "contents" }}><dt>Affected group</dt><dd>{latest.affected_group}</dd></div>
              <div style={{ display: "contents" }}><dt>Geographic context</dt><dd>{latest.geo_context}</dd></div>
              <div style={{ display: "contents" }}><dt>Category</dt><dd>{latest.category}</dd></div>
              <div style={{ display: "contents" }}><dt>Scope</dt><dd>{latest.scope}</dd></div>
              <div style={{ display: "contents" }}><dt>Technology areas</dt><dd>{(latest.tech_areas || []).join(", ") || "—"}</dd></div>
              <div style={{ display: "contents" }}><dt>Tags</dt><dd>{(latest.tags || []).join(", ") || "—"}</dd></div>
            </dl>
            <p>{latest.reason}</p>
            {latest.decision === "APPROVED" && (
              <p>
                Approval means your problem is now awaiting government
                routing review. It becomes publicly visible only after it
                is assigned to the public.
              </p>
            )}
            {latest.decision === "NEEDS_INFORMATION" && latest.missing_info.length > 0 && (
              <div className="alert info">
                <strong>What is missing:</strong>
                <ul>{latest.missing_info.map((m, i) => <li key={i}>{m}</li>)}</ul>
                <Link className="btn" to={`/problems/${ticket}/edit`}>Update &amp; Resubmit</Link>
              </div>
            )}
            {latest.decision === "NOT_SOCIETAL" && (
              <div className="alert error">This submission appears to describe a personal issue rather than a societal problem suitable for collaborative problem solving.</div>
            )}
            {latest.similar.length > 0 && (
              <div><strong>Potentially similar problems:</strong>
                <ul>{latest.similar.map((s, i) => <li key={i}>{s.ticket} ({s.relation}) — your problem was kept because its context may differ.</li>)}</ul>
              </div>
            )}
            {reviews.length > 1 && (
              <div><strong>Review history:</strong>
                <ul>{reviews.map((r) => <li key={r.review_number}>Review #{r.review_number} · version {r.version_number} · {r.decision || r.status}</li>)}</ul>
              </div>
            )}
          </>
        )}
      </div>
      <GovernmentReviewCard problem={problem} />
      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Attachments</h3>        {problem.attachments.length === 0 && <p>No attachments yet.</p>}
        {problem.attachments.map((a) => (
          <p key={a.id}>
            <a href={problemsApi.downloadUrl(ticket, a.id)} target="_blank" rel="noreferrer">{a.original_name}</a>{" "}
            <span className="badge">{Math.round(a.size_bytes / 1024)} KB</span>{" "}
            <button className="btn secondary" onClick={() => removeAttachment(a.id, a.original_name)}>Delete</button>
          </p>
        ))}
        <Field label="Add attachment (PDF, PNG, JPG, WEBP, TXT, CSV — max 10 MB)">
          <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        </Field>
        <button className="btn secondary" onClick={upload}>Upload</button>
        {uploadMsg && <p>{uploadMsg}</p>}
      </div>
      <div className="btn-row">
        <Link className="btn secondary" to={`/problems/${ticket}/track`}>Track Problem</Link>
        <Link className="btn secondary" to={`/problems/${ticket}/edit`}>Edit &amp; Resubmit</Link>
        <Link className="btn secondary" to={`/problems/${ticket}/history`}>View History</Link>
      </div>
      <ProblemSolutions problemTicket={ticket} isOwner problemStatus={problem.status} />
      <ProblemContributions ticket={ticket} />
    </>
  );
}

export function ProblemHistory() {
  const { ticket } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    problemsApi.history(ticket).then(setData).catch((e) => setError(e.message));
  }, [ticket]);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  return (
    <>
      <h2>History — {data.ticket}</h2>
      {data.versions.map((v) => (
        <div className="card" key={v.version_number} style={{ marginBottom: "1rem" }}>
          <h3>Version {v.version_number} <span className="badge">{new Date(v.created_at).toLocaleString()}</span></h3>
          <p><strong>{v.title}</strong></p>
          {v.revision_note && <p>Revision note: {v.revision_note}</p>}
          <p style={{ whiteSpace: "pre-wrap" }}>{v.description}</p>
        </div>
      ))}
      <Link className="btn secondary" to={`/problems/${ticket}`}>Back to Problem</Link>
    </>
  );
}

export function TrackProblem() {
  const { ticket } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const loadedRef = useRef(false);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      problemsApi.track(ticket).then((fresh) => {
        if (!cancelled) {
          loadedRef.current = true;
          setData(fresh);
          setError("");
        }
      }).catch((e) => {
        // Never fabricate state on failure: keep the last good snapshot
        // and surface the error only when nothing was ever loaded.
        if (!cancelled && !loadedRef.current) setError(e.message);
      });
    };
    load();
    // Government decisions land while this page is open; refresh so the
    // timeline always reflects the latest persisted backend state.
    const timer = setInterval(load, 7000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [ticket]);
  if (error && !data) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  const gov = data.government_review ?? null;
  return (
    <>
      <h2>Track Problem</h2>
      <p><span className="badge">{data.ticket}</span> <ProblemStatusBadge status={data.status} /></p>
      {gov && gov.review_status === "MORE_INFORMATION_REQUIRED" && gov.info_request && (
        <Alert kind="info">
          <strong>More information requested.</strong> {gov.info_request}
        </Alert>
      )}
      {gov && gov.escalation_flag && (
        <p className="muted">The review window was exceeded; the request was escalated in the review queue.</p>
      )}
      <div className="card">
        {data.stages.map((s, i) => (
          <Fragment key={s.key}>
            <p>
              {s.state === "done" ? "●" : s.state === "current" ? "◐" : "○"}{" "}
              <strong>{i + 1}. {s.label}</strong>{" "}
              {s.state === "current" && <span className="badge warn">current</span>}
            </p>
            {s.state === "current" && stageNote(s.key) && <p>{stageNote(s.key)}</p>}
          </Fragment>
        ))}
        <p>Version {data.current_version} · Updated {new Date(data.updated_at).toLocaleString()}</p>
      </div>
      <div className="btn-row">
        <Link className="btn secondary" to={`/problems/${ticket}`}>View My Ticket</Link>
      </div>
    </>
  );
}

export function TrackLookup() {
  const navigate = useNavigate();
  const [ticket, setTicket] = useState("");
  return (
    <div className="form-card">
      <h2>Track a Problem</h2>
      <form onSubmit={(e) => { e.preventDefault(); navigate(`/problems/${ticket.trim()}/track`); }}>
        <Field label="Problem Ticket (e.g. JS-PS-2026-004821)">
          <input required value={ticket} onChange={(e) => setTicket(e.target.value)} placeholder="JS-PS-YYYY-XXXXXX" />
        </Field>
        <button className="btn" type="submit">Track</button>
      </form>
    </div>
  );
}

function PublicDetail({ problem }) {
  return (
    <>
      <h2>{problem.title}</h2>
      <p>
        <span className="badge">{problem.ticket}</span>{" "}
        <span className="badge ok">{problem.status.replace(/_/g, " ")}</span>{" "}
        {problem.area && <span className="badge">{problem.area}</span>}{" "}
        {problem.scope && <span className="badge">{problem.scope}</span>}
      </p>
      <div className="card">
        <dl className="kv">
          <div style={{ display: "contents" }}><dt>Category</dt><dd>{problem.category}</dd></div>
          <div style={{ display: "contents" }}><dt>Location</dt><dd>{problem.location}</dd></div>
          <div style={{ display: "contents" }}><dt>Affected group</dt><dd>{problem.affected_group}</dd></div>
          <div style={{ display: "contents" }}><dt>Severity</dt><dd>{problem.severity}</dd></div>
          <div style={{ display: "contents" }}><dt>Solution needed</dt><dd>{problem.desired_solution_type}</dd></div>
          <div style={{ display: "contents" }}><dt>Skills</dt><dd>{problem.skills || "—"}</dd></div>
          {problem.problem_type && <div style={{ display: "contents" }}><dt>Problem type</dt><dd>{problem.problem_type}</dd></div>}
          {problem.tech_areas?.length > 0 && <div style={{ display: "contents" }}><dt>Technology areas</dt><dd>{problem.tech_areas.join(", ")}</dd></div>}
          {problem.tags?.length > 0 && <div style={{ display: "contents" }}><dt>Tags</dt><dd>{problem.tags.join(", ")}</dd></div>}
          <div style={{ display: "contents" }}><dt>Published</dt><dd>{new Date(problem.created_at).toLocaleDateString()}</dd></div>
        </dl>
        <h3>Description</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{problem.description}</p>
      </div>
      <ProblemSolutions problemTicket={problem.ticket} isOwner={false} problemStatus={problem.status} />
      <div className="btn-row">
        <Link className="btn secondary" to="/problems">Back to Problems</Link>
      </div>
    </>
  );
}

const SEARCH_DEFAULTS = { q: "", category: "", location: "", area: "", scope: "", affected_group: "", technology: "", problem_type: "", tag: "", status: "", sort: "newest", page: 1, limit: 10 };

export function BrowseProblems() {
  const [params, setParams] = useState(SEARCH_DEFAULTS);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const run = (p = params) => {
    setLoading(true);
    setError("");
    problemsApi.browse(p).then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  };

  // Initial load runs once on mount. State updates happen only inside the
  // promise callbacks (never synchronously in the effect body), and the
  // defaults are module scope, so no effect dependencies are needed.
  useEffect(() => {
    let ignore = false;
    problemsApi.browse({ ...SEARCH_DEFAULTS, page: 1 })
      .then((d) => { if (!ignore) { setData(d); setLoading(false); } })
      .catch((e) => { if (!ignore) { setError(e.message); setLoading(false); } });
    return () => { ignore = true; };
  }, []);
  const set = (k) => (e) => setParams((f) => ({ ...f, [k]: e.target.value, page: 1 }));

  return (
    <>
      <h2>Problems</h2>
      <div className="card">
        <Field label="Search problems, skills, institutions...">
          <input value={params.q} onChange={set("q")} placeholder="e.g. water, internship, footbridge" />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.6rem" }}>
          <Field label="Category"><input value={params.category} onChange={set("category")} placeholder="e.g. Water" /></Field>
          <Field label="Location"><input value={params.location} onChange={set("location")} placeholder="e.g. Nashik" /></Field>
          <Field label="Area">
            <select value={params.area} onChange={set("area")}>
              <option value="">Any</option><option>Rural</option><option>Urban</option><option>Semi-Urban</option><option>General</option>
            </select>
          </Field>
          <Field label="Scope">
            <select value={params.scope} onChange={set("scope")}>
              <option value="">Any</option><option>Individual</option><option>Family</option><option>Community</option><option>Institution</option><option>Organization</option><option>Regional</option><option>National</option>
            </select>
          </Field>
          <Field label="Affected group"><input value={params.affected_group} onChange={set("affected_group")} /></Field>
          <Field label="Technology"><input value={params.technology} onChange={set("technology")} /></Field>
          <Field label="Tag"><input value={params.tag} onChange={set("tag")} /></Field>
          <Field label="Status">
            <select value={params.status} onChange={set("status")}>
              <option value="">All public</option><option value="OPEN">Open</option><option value="COLLABORATION">Collaboration</option><option value="IN_DEVELOPMENT">In Development</option><option value="PILOT">Pilot</option><option value="IMPLEMENTED">Implemented</option>
            </select>
          </Field>
          <Field label="Sort">
            <select value={params.sort} onChange={set("sort")}>
              <option value="newest">Newest</option><option value="updated">Recently updated</option><option value="relevance">Relevance</option>
            </select>
          </Field>
        </div>
        <div className="btn-row">
          <button className="btn" onClick={() => run()}>Search</button>
          <button className="btn secondary" onClick={() => { setParams({ ...SEARCH_DEFAULTS }); run({ ...SEARCH_DEFAULTS }); }}>Reset Filters</button>
        </div>
      </div>
      <Alert>{error}</Alert>
      {loading && <p>Loading...</p>}
      {data && data.total === 0 && !loading && <div className="card"><p>No problems match your search. Try different keywords or fewer filters.</p></div>}
      {data && data.items.map((p) => (
        <div className="card" key={p.ticket} style={{ marginTop: "0.8rem" }}>
          <p><span className="badge">{p.ticket}</span> <span className="badge ok">{p.status.replace(/_/g, " ")}</span></p>
          <h3 style={{ margin: "0.3rem 0" }}><Link to={`/problems/${p.ticket}`}>{p.title}</Link></h3>
          <p>{p.category} · {p.location} · {p.affected_group}</p>
          {p.tags?.length > 0 && <p>{p.tags.map((t) => <span key={t} className="badge" style={{ marginRight: "0.3rem" }}>{t}</span>)}</p>}
        </div>
      ))}
      {data && data.pages > 1 && (
        <div className="btn-row">
          <button className="btn secondary" disabled={params.page <= 1} onClick={() => { const p = { ...params, page: params.page - 1 }; setParams(p); run(p); }}>Previous</button>
          <span>Page {data.page} of {data.pages} ({data.total} total)</span>
          <button className="btn secondary" disabled={params.page >= data.pages} onClick={() => { const p = { ...params, page: params.page + 1 }; setParams(p); run(p); }}>Next</button>
        </div>
      )}
    </>
  );
}

export function MyProblems() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    problemsApi.mine(0, 50).then((d) => { setItems(d.items); setTotal(d.total); })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <h2>My Problems</h2>
      <div className="btn-row" style={{ marginBottom: "1rem" }}>
        <Link className="btn" to="/submit-problem">Submit New Problem</Link>
        <Link className="btn secondary" to="/track">Track by Ticket</Link>
      </div>
      <Alert>{error}</Alert>
      {items.length === 0 && !error && <div className="card"><p>You have not submitted any problems yet.</p></div>}
      {items.map((p) => (
        <div className="card" key={p.ticket} style={{ marginBottom: "0.8rem" }}>
          <p><span className="badge">{p.ticket}</span> <ProblemStatusBadge status={p.status} /> <span className="badge">v{p.current_version}</span></p>
          <h3 style={{ margin: "0.3rem 0" }}>{p.title}</h3>
          <p>{p.category} · {new Date(p.created_at).toLocaleDateString()}</p>
          <p>{statusDescription(p.status)}</p>
          <div className="btn-row">
            <Link className="btn secondary" to={`/problems/${p.ticket}`}>View</Link>
            <Link className="btn secondary" to={`/problems/${p.ticket}/track`}>Track</Link>
            <Link className="btn secondary" to={`/problems/${p.ticket}/edit`}>Edit</Link>
          </div>
        </div>
      ))}
      <p>Total: {total}</p>
    </>
  );
}
