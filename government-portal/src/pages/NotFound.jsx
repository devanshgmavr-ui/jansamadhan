import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="form-card">
      <h2>Page not found</h2>
      <p className="muted">This portal page does not exist.</p>
      <div className="btn-row">
        <Link className="btn" to="/">Dashboard</Link>
        <Link className="btn secondary" to="/requests">Review Queue</Link>
      </div>
    </div>
  );
}
