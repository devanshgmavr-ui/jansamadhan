export function Alert({ kind = "error", children }) {
  if (!children) return null;
  return <div className={`alert ${kind}`}>{children}</div>;
}

export function Field({ label, children }) {
  // Implicit association (control nested in the label) so every form
  // control is labelled without requiring ids, and testing tools and
  // assistive technology can resolve labels reliably.
  return (
    <div className="field">
      <label>
        {label}
        {children}
      </label>
    </div>
  );
}

const TONE = {
  PENDING: "",
  ASSIGNED_TO_PUBLIC: "ok",
  MORE_INFORMATION_REQUIRED: "warn",
  GOVERNMENT_ISSUE: "",
  AUTO_ESCALATED: "warn",
};

const LABEL = {
  PENDING: "Pending",
  ASSIGNED_TO_PUBLIC: "Assigned to Public",
  MORE_INFORMATION_REQUIRED: "More Information Required",
  GOVERNMENT_ISSUE: "Government Issue",
  AUTO_ESCALATED: "Auto Escalated",
};

export function ReviewStatusBadge({ status }) {
  const tone = TONE[status] ?? "";
  const label = LABEL[status] ?? String(status ?? "").replace(/_/g, " ");
  return <span className={`badge${tone ? ` ${tone}` : ""}`}>{label}</span>;
}
