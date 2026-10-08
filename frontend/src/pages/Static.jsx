export function StageNote({ stage, what }) {
  return (
    <div className="card">
      <h3>{what}</h3>
      <p>
        This section arrives in <strong>{stage}</strong>. Problem and solution
        data will be served from the JanSamadhan database — no placeholder
        content is shown here.
      </p>
    </div>
  );
}

export function Problems() {
  return (
    <>
      <h2>Problems</h2>
      <StageNote stage="Stage 4 (problem submission) and Stage 6 (discovery)" what="Problem discovery" />
    </>
  );
}

export function Solutions() {
  return (
    <>
      <h2>Solutions</h2>
      <StageNote stage="Stage 7 (solution submission)" what="Solution discovery" />
    </>
  );
}

export function HowItWorks() {
  return (
    <>
      <h2>How It Works</h2>
      <div className="card">
        <p><strong>1. Register</strong> — choose Student, University, Organization or Individual, then verify email and phone.</p>
        <p><strong>2. Submit a problem</strong> — receive a permanent ticket such as JS-PS-2026-004821.</p>
        <p><strong>3. AI review</strong> — the problem is reviewed, classified and tagged.</p>
        <p><strong>4. Discover and solve</strong> — others find the problem through search and filters and submit solutions.</p>
        <p><strong>5. Collaborate</strong> — contributors form projects from prototype to implementation and impact.</p>
      </div>
    </>
  );
}

export function About() {
  return (
    <>
      <h2>About JanSamadhan</h2>
      <div className="card">
        <p>
          JanSamadhan is an independent platform for crowdsourcing societal
          problems and enabling collaborative problem solving across students,
          universities, organizations and individuals.
        </p>
        <p>
          JanSamadhan is not a government website and is not affiliated with
          any government.
        </p>
      </div>
    </>
  );
}
