import { Link } from "react-router-dom";

export default function Home() {
  return (
    <>
      <section className="hero">
        <h1>Every Problem Deserves a Solution.</h1>
        <p>
          JanSamadhan connects people, students, universities and organizations
          to identify real-world societal problems and work together toward
          meaningful solutions.
        </p>
        <div className="btn-row">
          <Link className="btn" to="/problems">
            View Problems
          </Link>
          <Link className="btn secondary" to="/how-it-works">
            How It Works
          </Link>
        </div>
      </section>
      <section className="grid-3">
        <div className="card">
          <h3>Raise Problems</h3>
          <p>Submit societal problems with a permanent tracking ticket.</p>
        </div>
        <div className="card">
          <h3>Propose Solutions</h3>
          <p>Share detailed solution proposals linked to real problems.</p>
        </div>
        <div className="card">
          <h3>Collaborate</h3>
          <p>Work with students, universities and organizations on impact.</p>
        </div>
      </section>
    </>
  );
}
