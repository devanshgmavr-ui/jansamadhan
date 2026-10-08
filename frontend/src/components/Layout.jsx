import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";

const LOGGED_OUT = [
  ["Home", "/"],
  ["Problems", "/problems"],
  ["Solutions", "/solutions"],
  ["How It Works", "/how-it-works"],
  ["About", "/about"],
];

const PROFILE_MENU = [
  ["My Dashboard", "/dashboard"],
  ["My Problems", "/my-problems"],
  ["My Solutions", "/my-solutions"],
  ["My Contributions", "/my-contributions"],
  ["My Collaborations", "/my-collaborations"],
  ["My Profile", "/profile"],
  ["Settings", "/settings"],
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const menuRef = useRef(null);

  useEffect(() => {
    const onDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const signOut = async () => {
    await logout();
    setOpen(false);
    navigate("/");
  };

  return (
    <>
      <header className="site-header">
        <div className="bar">
          <Link to="/" className="brand">
            <strong>JanSamadhan</strong>
            <small>From Problems to Possibilities. Together.</small>
          </Link>
          <nav className="main-nav">
            {LOGGED_OUT.map(([label, to]) => (
              <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
                {label}
              </NavLink>
            ))}
            {!user && (
              <NavLink to="/signin" className="btn-signin">
                Sign In
              </NavLink>
            )}
          </nav>
          {user && (
            <div className="profile-wrap" ref={menuRef}>
              <button
                className="profile-btn"
                onClick={() => setOpen((v) => !v)}
                aria-label="Profile menu"
                aria-expanded={open}
                title={user.email}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <circle cx="10" cy="6.5" r="3.2" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M3.5 16.5c1.2-3.2 3.7-4.8 6.5-4.8s5.3 1.6 6.5 4.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
              {open && (
                <div className="profile-menu">
                  {PROFILE_MENU.map(([label, to]) => (
                    <Link key={to} to={to} onClick={() => setOpen(false)}>
                      {label}
                    </Link>
                  ))}
                  <button onClick={signOut}>Sign Out</button>
                </div>
              )}
            </div>
          )}
        </div>
      </header>
      <main className="page">{children}</main>
      <footer className="site-footer">
        <div className="inner">
          JanSamadhan is an independent civic-technology platform. It is not a
          government website and is not affiliated with any government.
        </div>
      </footer>
    </>
  );
}
