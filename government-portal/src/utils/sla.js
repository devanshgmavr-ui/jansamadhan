// SLA display helper: human-readable distance to the server-provided
// sla_due_at. Display only — the backend owns expiry and escalation.
export function formatDue(iso) {
  const due = new Date(iso).getTime();
  const diff = due - Date.now();
  if (Number.isNaN(due)) return "—";
  if (diff <= 0) return "Overdue";
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    return `Due in ${days}d ${hours % 24}h`;
  }
  return `Due in ${hours}h ${minutes}m`;
}
