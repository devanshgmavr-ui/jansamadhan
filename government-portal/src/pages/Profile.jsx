import { useGovAuth } from "../context/useGovAuth";

export function Profile() {
  const { official } = useGovAuth();
  if (!official) return <p>Loading...</p>;
  return (
    <div className="card">
      <h2>Official Profile</h2>
      <dl className="kv">
        <dt>Employee ID</dt><dd>{official.employee_id}</dd>
        <dt>Name</dt><dd>{official.full_name || "—"}</dd>
        <dt>Designation</dt><dd>{official.designation || "—"}</dd>
        <dt>Status</dt>
        <dd>{official.is_active ? "Active" : "Inactive"}</dd>
      </dl>
    </div>
  );
}
