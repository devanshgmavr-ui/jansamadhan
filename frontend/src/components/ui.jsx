export function Alert({ kind = "error", children }) {
  if (!children) return null;
  return <div className={`alert ${kind}`}>{children}</div>;
}

export function Field({ label, children }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}

export function DevNote({ label, value }) {
  if (!value) return null;
  return (
    <div className="dev-note">
      <strong>{label} (development only):</strong> {value}
    </div>
  );
}

import { statusLabel, statusTone } from "../services/problemStatus";

export function ProblemStatusBadge({ status }) {
  // Central mapping: label text plus tone, never color alone.
  const tone = statusTone(status);
  return (
    <span className={`badge${tone ? ` ${tone}` : ""}`}>
      {statusLabel(status)}
    </span>
  );
}
