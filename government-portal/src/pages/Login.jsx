import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Alert, Field } from "../components/ui";
import { useGovAuth } from "../context/useGovAuth";

export function Login() {
  const { login } = useGovAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(employeeId.trim(), password);
      navigate(location.state?.from ?? "/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card">
      <h2>Government Sign In</h2>
      <p className="muted">
        Authorized officials only. Sign in with your provisioned Employee
        ID. This portal has no public registration.
      </p>
      <Alert>{error}</Alert>
      <form onSubmit={submit}>
        <Field label="Employee ID">
          <input
            required
            type="text"
            autoComplete="username"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
          />
        </Field>
        <Field label="Password">
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <button className="btn" disabled={busy} type="submit">
          {busy ? "Signing in..." : "Sign In"}
        </button>
      </form>
    </div>
  );
}
