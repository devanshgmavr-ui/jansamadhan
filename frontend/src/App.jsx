import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./context/useAuth";
import { Dashboard, Profile, Settings } from "./pages/Account";
import { CollaborationDetail, MyCollaborations, ProjectDetail } from "./pages/Collaborations";
import { MyContributions } from "./pages/Contributions";
import Home from "./pages/Home";
import Register, { SignIn } from "./pages/Auth";
import { ForgotPassword, ResetPassword, VerifyAccount } from "./pages/Recovery";
import {
  BrowseProblems,
  MyProblems,
  ProblemDetail,
  ProblemHistory,
  SubmitProblem,
  TrackLookup,
  TrackProblem,
} from "./pages/Problems";
import { About, HowItWorks } from "./pages/Static";
import { ApprovedDetail } from "./pages/ApprovedDetail";
import { NotFound } from "./pages/NotFound";
import {
  BrowseSolutions,
  EditSolution,
  MySolutions,
  SolutionDetail,
  SolutionTrack,
  SubmitSolution,
} from "./pages/Solutions";

function RequireAuth({ children }) {
  const { user, initializing } = useAuth();
  const location = useLocation();
  if (initializing) return <p>Loading...</p>;
  if (!user)
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  return children;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/problems" element={<BrowseProblems />} />
        <Route path="/approved/:ticket" element={<ApprovedDetail />} />
        <Route path="/solutions" element={<BrowseSolutions />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/about" element={<About />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify-account" element={<VerifyAccount />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
        <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
        <Route path="/my-problems" element={<RequireAuth><MyProblems /></RequireAuth>} />
        <Route path="/submit-problem" element={<RequireAuth><SubmitProblem /></RequireAuth>} />
        <Route path="/problems/:ticket" element={<ProblemDetail />} />
        <Route path="/problems/:ticket/edit" element={<RequireAuth><SubmitProblem /></RequireAuth>} />
        <Route path="/problems/:ticket/history" element={<RequireAuth><ProblemHistory /></RequireAuth>} />
        <Route path="/problems/:ticket/track" element={<RequireAuth><TrackProblem /></RequireAuth>} />
        <Route path="/track" element={<RequireAuth><TrackLookup /></RequireAuth>} />
        <Route path="/problems/:ticket/submit-solution" element={<RequireAuth><SubmitSolution /></RequireAuth>} />
        <Route path="/solutions/:ticket" element={<SolutionDetail />} />
        <Route path="/solutions/:ticket/track" element={<SolutionTrack />} />
        <Route path="/solutions/:ticket/edit" element={<RequireAuth><EditSolution /></RequireAuth>} />
        <Route path="/my-solutions" element={<RequireAuth><MySolutions /></RequireAuth>} />
        <Route path="/my-contributions" element={<RequireAuth><MyContributions /></RequireAuth>} />
        <Route path="/my-collaborations" element={<RequireAuth><MyCollaborations /></RequireAuth>} />
        <Route path="/collaborations/:id" element={<RequireAuth><CollaborationDetail /></RequireAuth>} />
        <Route path="/projects/:id" element={<RequireAuth><ProjectDetail /></RequireAuth>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
