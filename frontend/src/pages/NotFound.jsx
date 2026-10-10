import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="form-card">
      <h2>Page not found</h2>
      <p className="muted">
        The page you are looking for does not exist or may have been moved.
      </p>
      <div className="btn-row">
        <Link className="btn" to="/">Go to Homepage</Link>
        <Link className="btn secondary" to="/track">Track a Problem</Link>
      </div>
    </div>
  );
}
