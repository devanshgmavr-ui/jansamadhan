import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Field } from "../components/ui";
import { contribApi } from "../services/api";

const TYPES = ["SOLUTION_PROPOSAL", "RESEARCH", "TECHNICAL", "PROTOTYPE_TESTING", "DEVELOPMENT", "COLLABORATION", "OTHER"];

export function MyContributions() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [form, setForm] = useState({ problem_ticket: "", solution_ticket: "", type: "RESEARCH", description: "" });
  const [editing, setEditing] = useState(null);
  const [editText, setEditText] = useState("");

  const load = () => contribApi.mine(0, 50)
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
      if (!body.problem_ticket) delete body.problem_ticket;
      await contribApi.create(body);
      setForm({ problem_ticket: "", solution_ticket: "", type: "RESEARCH", description: "" });
      setInfo("Contribution recorded.");
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const saveEdit = async (id) => {
    setError("");
    try {
      await contribApi.update(id, { description: editText });
      setEditing(null);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const remove = async (id) => {
    setError("");
    try {
      await contribApi.remove(id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <h2>My Contributions</h2>
      <Alert>{error}</Alert>
      <Alert kind="success">{info}</Alert>
      <div className="form-card" style={{ maxWidth: 680, margin: "0 0 1rem" }}>
        <h3>Record a Contribution</h3>
        <form onSubmit={create}>
          <Field label="Related Problem Ticket (required unless a solution is given)">
            <input value={form.problem_ticket} onChange={(e) => setForm({ ...form, problem_ticket: e.target.value })} placeholder="JS-PS-YYYY-XXXXXX" />
          </Field>
          <Field label="Related Solution Ticket (optional)">
            <input value={form.solution_ticket} onChange={(e) => setForm({ ...form, solution_ticket: e.target.value })} placeholder="JS-SOL-YYYY-XXXXXX" />
          </Field>
          <Field label="Contribution Type">
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              {TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
          </Field>
          <Field label="Description"><textarea required minLength={10} rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <button className="btn" type="submit">Save Contribution</button>
        </form>
      </div>
      {items.map((c) => (
        <div className="card" key={c.id} style={{ marginBottom: "0.8rem" }}>
          <p>
            <span className="badge">{c.type.replace(/_/g, " ")}</span>{" "}
            <span className={`badge ${c.status === "ACCEPTED" ? "ok" : c.status === "DECLINED" ? "" : "warn"}`}>{c.status}</span>
          </p>
          {editing === c.id ? (
            <>
              <Field label="Description"><textarea rows={3} value={editText} onChange={(e) => setEditText(e.target.value)} /></Field>
              <div className="btn-row">
                <button className="btn" onClick={() => saveEdit(c.id)}>Save</button>
                <button className="btn secondary" onClick={() => setEditing(null)}>Cancel</button>
              </div>
            </>
          ) : (
            <p style={{ whiteSpace: "pre-wrap" }}>{c.description}</p>
          )}
          <p>
            {c.problem_ticket && <>Problem <Link to={`/problems/${c.problem_ticket}`}>{c.problem_ticket}</Link> </>}
            {c.solution_ticket && <>Solution <Link to={`/solutions/${c.solution_ticket}`}>{c.solution_ticket}</Link> </>}
            {new Date(c.created_at).toLocaleDateString()}
          </p>
          {c.status === "PENDING" && editing !== c.id && (
            <div className="btn-row">
              <button className="btn secondary" onClick={() => { setEditing(c.id); setEditText(c.description); }}>Edit</button>
              <button className="btn secondary" onClick={() => remove(c.id)}>Delete</button>
            </div>
          )}
        </div>
      ))}
      <p>Total: {total}</p>
    </>
  );
}

export function ProblemContributions({ ticket, onChanged }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const load = useCallback(() => contribApi.forProblem(ticket)
    .then((d) => setItems(d.items)).catch((e) => setError(e.message)), [ticket]);
  useEffect(() => { load(); }, [load]);

  const decide = async (id, status) => {
    setError("");
    try {
      await contribApi.setStatus(id, status);
      load();
      onChanged && onChanged();
    } catch (err) {
      setError(err.message);
    }
  };

  if (error) return <p>{error}</p>;
  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <h3>Contributions ({items.length})</h3>
      {items.length === 0 && <p>No contributions yet.</p>}
      {items.map((c) => (
        <div key={c.id} style={{ borderTop: "1px solid var(--line)", paddingTop: "0.5rem", marginTop: "0.5rem" }}>
          <p><span className="badge">{c.type.replace(/_/g, " ")}</span> <span className="badge warn">{c.status}</span></p>
          <p style={{ whiteSpace: "pre-wrap" }}>{c.description}</p>
          {c.status === "PENDING" && (
            <div className="btn-row">
              <button className="btn secondary" onClick={() => decide(c.id, "ACCEPTED")}>Accept</button>
              <button className="btn secondary" onClick={() => decide(c.id, "DECLINED")}>Decline</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
