import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Alert, DevNote, Field } from "../components/ui";
import { authApi } from "../services/api";

export function VerifyAccount() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState(state?.identifier || "");
  const [emailCode, setEmailCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [devOtp, setDevOtp] = useState(state?.devOtp || "");
  const [busy, setBusy] = useState(false);

  const verifyEmail = async () => {
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const res = await authApi.verifyEmail({ identifier, channel: "email", code: emailCode });
      setInfo(res.message);
      setTimeout(() => navigate("/signin"), 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const resendEmail = async () => {
    setError("");
    setInfo("");
    try {
      const res = await authApi.resendOtp({ identifier, channel: "email" });
      setInfo(res.message);
      if (res.dev_otp) setDevOtp(res.dev_otp);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="form-card">
      <h2>Verify Your Account</h2>
      <Alert>{error}</Alert>
      <Alert kind="success">{info}</Alert>
      <Field label="Email used at registration">
        <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
      </Field>
      <h3>Email OTP</h3>
      <Field label="6-digit email code">
        <input value={emailCode} maxLength={6} onChange={(e) => setEmailCode(e.target.value)} />
      </Field>
      <div className="btn-row">
        <button className="btn" disabled={busy} onClick={verifyEmail}>
          Verify Email
        </button>
        <button className="btn secondary" onClick={resendEmail}>Resend</button>
      </div>
      <DevNote label="OTP codes" value={devOtp} />
      <p><Link to="/signin">Back to Sign In</Link></p>
    </div>
  );
}

export function ForgotPassword() {
  const [identifier, setIdentifier] = useState("");
  const [info, setInfo] = useState("");
  const [devToken, setDevToken] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await authApi.forgot({ identifier });
      setInfo(res.message);
      setDevToken(res.dev_reset_token || "");
    } catch (err) {
      setInfo(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card">
      <h2>Forgot Password</h2>
      <Alert kind="success">{info}</Alert>
      <form onSubmit={submit}>
        <Field label="Email or Phone">
          <input required value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        </Field>
        <button className="btn" disabled={busy} type="submit">Send Reset Link</button>
      </form>
      <DevNote label="Reset token" value={devToken} />
    </div>
  );
}

export function ResetPassword() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const res = await authApi.reset({ token, new_password: password });
      setMsg(res.message);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card">
      <h2>Reset Password</h2>
      <Alert>{err}</Alert>
      <Alert kind="success">{msg}</Alert>
      <form onSubmit={submit}>
        <Field label="Reset Token"><input required value={token} onChange={(e) => setToken(e.target.value)} /></Field>
        <Field label="New Password (min 8 chars, letters + numbers)">
          <input required type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button className="btn" disabled={busy} type="submit">Reset Password</button>
      </form>
      <p><Link to="/signin">Back to Sign In</Link></p>
    </div>
  );
}
