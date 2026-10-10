import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useGovAuth } from "./context/useGovAuth";
import { Analytics } from "./pages/Analytics";
import { AuditLog } from "./pages/AuditLog";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Profile } from "./pages/Profile";
import { RequestDetail } from "./pages/RequestDetail";
import { Requests } from "./pages/Requests";
import { Settings } from "./pages/Settings";

function RequireGovAuth({ children }) {
  const { isAuthenticated, initializing } = useGovAuth();
  const location = useLocation();
  if (initializing) return <p>Loading...</p>;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<RequireGovAuth><Dashboard /></RequireGovAuth>} />
        <Route path="/requests" element={<RequireGovAuth><Requests /></RequireGovAuth>} />
        <Route
          path="/requests/:ticket"
          element={<RequireGovAuth><RequestDetail /></RequireGovAuth>}
        />
        <Route path="/profile" element={<RequireGovAuth><Profile /></RequireGovAuth>} />
        <Route path="/analytics" element={<RequireGovAuth><Analytics /></RequireGovAuth>} />
        <Route path="/audit" element={<RequireGovAuth><AuditLog /></RequireGovAuth>} />
        <Route path="/settings" element={<RequireGovAuth><Settings /></RequireGovAuth>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
