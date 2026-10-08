import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Alert, DevNote, Field } from "../components/ui";
import { useAuth } from "../context/useAuth";
import { authApi } from "../services/api";

const TYPES = ["student", "university", "organization", "individual"];

export default function Register() {
  const navigate = useNavigate();
  const [accountType, setAccountType] = useState("student");
  const [form, setForm] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [devOtp, setDevOtp] = useState("");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // India-only mobile validation, mirroring the backend rule:
  // 10 digits starting 6-9, optional +91 / 91 / 0 prefix.
  const normalizeIndianPhone = (raw) => {
    const v = String(raw || "").replace(/[\s\-()]/g, "");
    const m = v.match(/^(?:\+?91|0)?([6-9][0-9]{9})$/);
    return m ? `+91${m[1]}` : null;
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    const normalizedPhone = normalizeIndianPhone(form.phone);
    if (!normalizedPhone) {
      setError("Phone must be a valid Indian mobile number: 10 digits starting with 6-9 (e.g. +919812345678).");
      return;
    }
    setBusy(true);
    try {
      const body = {
        account_type: accountType,
        email: form.email,
        phone: normalizedPhone,
        password: form.password,
        first_name: form.first_name,
        last_name: form.last_name,
      };
      if (accountType === "student")
        body.student = { college: form.college, course: form.course, year: form.year, skills: form.skills };
      if (accountType === "university")
        body.university = { university_name: form.university_name, institution_type: form.institution_type, location: form.location, website: form.website };
      if (accountType === "organization")
        body.organization = { organization_name: form.organization_name, organization_type: form.organization_type, industry: form.industry, location: form.location, website: form.website };
      if (accountType === "individual")
        body.individual = { location: form.location, interests: form.interests, skills: form.skills };
      const res = await authApi.register(body);
      setDevOtp(res.dev_otp || "");
      navigate("/verify-account", { state: { identifier: form.email, devOtp: res.dev_otp || "" } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card">
      <h2>Create Account</h2>
      <Alert>{error}</Alert>
      <div className="type-grid">
        {TYPES.map((t) => (
          <button
            key={t}
            type="button"
            className={`type-btn${accountType === t ? " selected" : ""}`}
            onClick={() => setAccountType(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <form onSubmit={submit}>
        <Field label="Email"><input required type="email" onChange={set("email")} /></Field>
        <Field label="Phone — Indian mobile only (e.g. +919812345678)"><input required onChange={set("phone")} placeholder="+919812345678" /></Field>
        <Field label="Password (min 8 chars, letters + numbers)"><input required type="password" minLength={8} onChange={set("password")} /></Field>
        {(accountType === "student" || accountType === "individual") && (
          <>
            <Field label="First Name"><input required onChange={set("first_name")} /></Field>
            <Field label="Last Name"><input required onChange={set("last_name")} /></Field>
          </>
        )}
        {accountType === "student" && (
          <>
            <Field label="College / University"><input required onChange={set("college")} /></Field>
            <Field label="Course"><input onChange={set("course")} /></Field>
            <Field label="Year"><input onChange={set("year")} /></Field>
            <Field label="Field / Skills"><input onChange={set("skills")} /></Field>
          </>
        )}
        {accountType === "university" && (
          <>
            <Field label="University Name"><input required onChange={set("university_name")} /></Field>
            <Field label="Institution Type"><input onChange={set("institution_type")} /></Field>
            <Field label="Location"><input onChange={set("location")} /></Field>
            <Field label="Website"><input onChange={set("website")} /></Field>
          </>
        )}
        {accountType === "organization" && (
          <>
            <Field label="Organization Name"><input required onChange={set("organization_name")} /></Field>
            <Field label="Organization Type"><input onChange={set("organization_type")} /></Field>
            <Field label="Industry / Sector"><input onChange={set("industry")} /></Field>
            <Field label="Location"><input onChange={set("location")} /></Field>
            <Field label="Website"><input onChange={set("website")} /></Field>
          </>
        )}
        {accountType === "individual" && (
          <>
            <Field label="Location"><input onChange={set("location")} /></Field>
            <Field label="Areas of Interest"><input onChange={set("interests")} /></Field>
            <Field label="Skills"><input onChange={set("skills")} /></Field>
          </>
        )}
        <button className="btn" disabled={busy} type="submit">
          {busy ? "Creating..." : "Register"}
        </button>
      </form>
      <DevNote label="OTP codes" value={devOtp} />
      <p>
        Already have an account? <Link to="/signin">Sign In</Link>
      </p>
    </div>
  );
}

export function SignIn() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { state } = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(identifier, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card">
      <h2>Sign In</h2>
      {state?.from && (
        <div className="alert info">Please sign in to continue.</div>
      )}
      <Alert>{error}</Alert>
      <form onSubmit={submit}>
        <Field label="Email or Phone">
          <input required value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        </Field>
        <Field label="Password">
          <input required type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button className="btn" disabled={busy} type="submit">
          {busy ? "Signing in..." : "Sign In"}
        </button>
      </form>
      <p>
        <Link to="/forgot-password">Forgot password?</Link>
        {" · "}
        <Link to="/register">Create account</Link>
      </p>
    </div>
  );
}
