import { Link, NavLink, useNavigate } from "react-router-dom";
import { useGovAuth } from "../context/useGovAuth";

export function Layout({ children }) {
  const { official, logout } = useGovAuth();
  const navigate = useNavigate();
  const signOut = async () => {
    await logout();
    navigate("/login");
  };
  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <Link className="brand" to="/">JanSamadhan</Link>
          <span className="brand-sub">Government Review Portal</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/requests">Review Queue</NavLink>
          <NavLink to="/analytics">Analytics</NavLink>
          <NavLink to="/audit">Audit Log</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/profile">Profile</NavLink>
          {official && (
            <button className="btn secondary" onClick={signOut}>Logout</button>
          )}
        </nav>
      </header>
      <p className="scope-note">
        Authorized review interface. Routing decisions made here update the
        shared JanSamadhan record.
      </p>
      <main className="content">{children}</main>
    </div>
  );
}
