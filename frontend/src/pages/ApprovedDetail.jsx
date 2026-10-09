import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert } from "../components/ui";
import { problemsApi } from "../services/api";
import { statusLabel } from "../services/problemStatus";

const REFRESH_MS = 30000;

function Timeline({ events }) {
  if (!events || events.length === 0) return null;
  return (
    <div className="card">
      <h3>Timeline</h3>
      {events.map((e, i) => (
        <p key={`${e.created_at}-${i}`}>
          <strong>{e.label}</strong>{" "}
          <span className="muted">· {new Date(e.created_at).toLocaleString()}</span>
          {e.detail && <><br />{e.detail}</>}
        </p>
      ))}
    </div>
  );
}

export function ApprovedDetail() {
  const { ticket } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const loadedRef = useRef(false);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      problemsApi.transparencyDetail(ticket).then((fresh) => {
        if (!cancelled) {
          loadedRef.current = true;
          setData(fresh);
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
  }, [ticket]);

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <p>Loading...</p>;
  const isChallenge = data.resolution_type === "PUBLIC";
  return (
    <>
      <h2>{data.title}</h2>
      <p>
        <span className="badge">{data.ticket}</span>{" "}
        <span className="badge">{isChallenge ? "Open for Solutions" : "Government Action in Progress"}</span>{" "}
        <span className="badge">{statusLabel(data.status)}</span>
      </p>
      <div className="card">
        <dl className="kv">
          <dt>Category</dt><dd>{data.category}</dd>
          <dt>Location</dt><dd>{data.location}</dd>
          <dt>Priority</dt><dd>{data.severity}</dd>
          <dt>Status</dt><dd>{statusLabel(data.status)}</dd>
          <dt>Resolution Type</dt>
          <dd>{isChallenge ? "Public Challenge" : "Government Issue"}</dd>
          {data.decided_at && (
            <><dt>Approval Date</dt><dd>{new Date(data.decided_at).toLocaleDateString()}</dd></>
          )}
        </dl>
        {data.decision_reason && (
          <><h3>Government Remark</h3><p>{data.decision_reason}</p></>
        )}
      </div>
      {isChallenge ? (
        <div className="card">
          <h3>Solutions ({data.solution_count})</h3>
          {data.solution_count === 0 && <p>No solutions submitted yet.</p>}
          {data.selected_solution && (
            <div className="alert success">
              <strong>Winning solution:</strong>{" "}
              <Link to={`/solutions/${data.selected_solution.ticket}`}>
                {data.selected_solution.title}
              </Link>
            </div>
          )}
          {data.solutions.map((s) => (
            <p key={s.ticket}>
              <Link to={`/solutions/${s.ticket}`}>{s.title}</Link>{" "}
              <span className="badge">{s.ticket}</span>{" "}
              {s.is_selected && <span className="badge warn">Selected</span>}
            </p>
          ))}
        </div>
      ) : (
        <div className="card">
          <h3>Implementation Progress</h3>
          {data.implementation_updates.length === 0 && (
            <p>No progress updates published yet.</p>
          )}
          {data.implementation_updates.map((u) => (
            <div key={u.id} style={{ marginBottom: "0.8rem" }}>
              <p>
                <strong>{u.stage.replace(/_/g, " ")}</strong>: {u.title}{" "}
                <span className="muted">· {new Date(u.created_at).toLocaleString()}</span>
              </p>
              {u.description && <p style={{ whiteSpace: "pre-wrap" }}>{u.description}</p>}
              {u.attachments.map((a) => (
                <p key={a.id}>
                  <a href={problemsApi.implementationAttachmentUrl(data.ticket, u.id, a.id)} target="_blank" rel="noreferrer">{a.original_name}</a>
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
      <Timeline events={data.timeline} />
    </>
  );
}
