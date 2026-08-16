import Image from "next/image";
import Link from "next/link";
import heroImage from "../public/images/evidence-journey-hero.png";

const journey = [
  ["01", "Bring the question", "Start with an owned project, a de-identified dataset and the real-world outcome you want to understand."],
  ["02", "Investigate before modelling", "ZubePredict profiles the data, tests readiness and looks for identifiers, ambiguity and leakage."],
  ["03", "Agree on the experiment", "A plain-language Constitution records the task, target, validation strategy, metric, exclusions and budget."],
  ["04", "Compare suitable models", "The durable worker establishes baselines, runs a resource-aware tournament and records failures as well as successes."],
  ["05", "Challenge the result", "Calibration, error analysis, limitations and reproducibility evidence show where the result is useful—and where it is not."],
  ["06", "Carry the evidence", "The same verified Evidence Card and reports are available from the dashboard, Telegram and authenticated API."],
] as const;

const useCases = [
  ["Follow-up intelligence", "Investigate which de-identified records may need closer operational review—without turning a model into a clinical verdict."],
  ["Demand forecasting", "Explore likely appointment, service, inventory or workload demand so teams can plan earlier."],
  ["Cohort discovery", "Find useful groups and service-use patterns that may be difficult to see in a spreadsheet."],
  ["Anomaly detection", "Surface unusual operational patterns for human investigation rather than silently treating them as facts."],
  ["Outcome research", "Compare candidate models against a declared target and preserve the evidence behind the comparison."],
  ["Quality improvement", "Turn recurring analysis into a governed process that can be inspected, repeated and explained."],
] as const;

const artifacts = ["EyeCare Evidence Card", "Model leaderboard", "HTML and PDF report", "Model Card", "Prediction workbook", "Reproducibility manifest"];

export default function Home() {
  return (
    <main className="landing">
      <nav className="landing-nav" aria-label="Primary navigation">
        <Link className="brand" href="/"><span className="brand-mark">ZP</span><span>ZubePredict AI</span></Link>
        <div className="landing-links">
          <a href="#journey">How it works</a>
          <a href="#eye-care">Eye care</a>
          <a href="#evidence">Evidence</a>
        </div>
        <Link className="button small primary" href="/dashboard">Open workspace <span aria-hidden="true">→</span></Link>
      </nav>

      <section className="landing-hero">
        <div className="hero-copy">
          <p className="eyebrow">AUTONOMOUS DATA SCIENCE, GOVERNED BY EVIDENCE</p>
          <h1>Your data has answers. <em>ZubePredict builds the evidence.</em></h1>
          <p className="lead">Turn an underused spreadsheet and a real-world question into a careful, resumable data-science investigation—complete with human checkpoints, model comparisons and reports people can understand.</p>
          <div className="hero-actions">
            <Link className="button primary" href="/dashboard">Start in your workspace <span aria-hidden="true">→</span></Link>
            <a className="button quiet" href="#journey">See the journey</a>
          </div>
          <div className="hero-trust" aria-label="Product safeguards">
            <span><i /> Private, owner-scoped data</span>
            <span><i /> Human confirmation before training</span>
            <span><i /> Evidence before explanation</span>
          </div>
        </div>
        <div className="hero-visual">
          <Image src={heroImage} alt="Abstract journey from tabular data through validation checkpoints to a structured evidence report" priority sizes="(max-width: 900px) 100vw, 48vw" />
          <div className="hero-proof-card">
            <span>THE OUTCOME</span>
            <strong>A governed investigation, not a guessed answer.</strong>
            <small>Traceable • resumable • reproducible</small>
          </div>
        </div>
      </section>

      <section className="trust-ribbon" aria-label="Core capabilities">
        <span>Private data intake</span><i />
        <span>Leakage protection</span><i />
        <span>Durable experiments</span><i />
        <span>Verified reports</span><i />
        <span>Web + Telegram continuity</span>
      </section>

      <section className="story-section story-intro">
        <div>
          <p className="eyebrow">FROM ABANDONED SPREADSHEETS TO DEFENSIBLE DECISIONS</p>
          <h2>Valuable data should not end its life in a folder.</h2>
        </div>
        <div className="story-prose">
          <p>Clinics and organisations collect appointments, outcomes, operations, customers, inventory and follow-up records every day. Yet answering one predictive question can still require several specialists, disconnected tools and weeks of careful decisions.</p>
          <p>ZubePredict assembles that work into one governed system. It investigates the dataset, asks when the objective is unclear, proposes a safe experiment, compares appropriate models and preserves the evidence required to trust, challenge and reproduce the result.</p>
        </div>
      </section>

      <section className="journey-section" id="journey">
        <div className="section-heading">
          <p className="eyebrow">THE SCIENTIFIC JOURNEY</p>
          <h2>It knows when to proceed—and when to ask you.</h2>
          <p>A spreadsheet does not go straight into a random model. Every important assumption becomes visible before expensive work begins.</p>
        </div>
        <div className="journey-grid">
          {journey.map(([number, title, copy]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p></article>)}
        </div>
      </section>

      <section className="difference-section">
        <div className="difference-copy">
          <p className="eyebrow">MORE THAN A CHAT ABOUT YOUR CSV</p>
          <h2>The system conducts the analysis—and documents what happened.</h2>
          <p>General assistants can suggest code or discuss a file. ZubePredict connects agentic reasoning to deterministic machine-learning pipelines, durable jobs, private storage and immutable evidence.</p>
          <Link href="/dashboard" className="text-link">Explore the unified workspace <span aria-hidden="true">→</span></Link>
        </div>
        <div className="comparison-cards">
          <article className="comparison-muted"><small>A GENERAL CHAT ASSISTANT</small><h3>Suggests an analysis</h3><ul><li>Conversation-led</li><li>May generate disposable code</li><li>Explanation can outrun evidence</li></ul></article>
          <article className="comparison-primary"><small>ZUBEPREDICT</small><h3>Runs a governed process</h3><ul><li>Owner-scoped, durable state</li><li>Declared experiment and safety gates</li><li>Verified artifacts shared across channels</li></ul></article>
        </div>
      </section>

      <section className="use-case-section" id="eye-care">
        <div className="section-heading split-heading">
          <div><p className="eyebrow">EYE-CARE AND OPERATIONAL INTELLIGENCE</p><h2>Built around questions that matter before problems become visible.</h2></div>
          <p>ZubePredict’s strongest starting point is predictive and operational intelligence for eye-care organisations, while its tabular workflow also supports responsible business and research use cases.</p>
        </div>
        <div className="use-case-grid">
          {useCases.map(([title, copy], index) => <article key={title}><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span><h3>{title}</h3><p>{copy}</p></article>)}
        </div>
        <div className="responsible-banner"><strong>Decision support, not autonomous diagnosis.</strong><span>Outputs require domain review, appropriate validation and accountable human oversight before high-stakes use.</span></div>
      </section>

      <section className="evidence-section" id="evidence">
        <div className="evidence-story">
          <p className="eyebrow">THE DELIVERABLE IS EVIDENCE</p>
          <h2>One authoritative result, shaped for every reader.</h2>
          <p>Decision-makers receive clear summaries and limitations. Technical teams can inspect metrics, validation, integrity references and reproducibility details. Hermes can explain the evidence, but it cannot rewrite the underlying numbers.</p>
        </div>
        <div className="artifact-grid">
          {artifacts.map((artifact, index) => <article key={artifact}><span>0{index + 1}</span><strong>{artifact}</strong><small>{index < 2 ? "Review in the workspace" : "Private, authorised delivery"}</small></article>)}
        </div>
      </section>

      <section className="channel-section">
        <div><p className="eyebrow">ONE EXPERIMENT, EVERY CHANNEL</p><h2>Begin on the web. Check progress on Telegram. Return to the same evidence.</h2></div>
        <div className="channel-flow" aria-label="Shared cross-channel workflow"><span>Dashboard</span><i>↔</i><strong>One owned experiment</strong><i>↔</i><span>Telegram</span></div>
      </section>

      <section className="closing-cta">
        <p className="eyebrow">FROM RAW DATA TO DEFENSIBLE DECISIONS</p>
        <h2>Ask a better question of the data you already have.</h2>
        <p>Start with synthetic or properly de-identified data. ZubePredict will help turn the question into a reviewable experiment.</p>
        <Link className="button primary" href="/dashboard">Open your workspace <span aria-hidden="true">→</span></Link>
      </section>

      <footer className="landing-footer"><Link className="brand" href="/"><span className="brand-mark">ZP</span><span>ZubePredict AI</span></Link><p>Autonomous data science for governed, reproducible evidence.</p><span>Decision support and research unless independently validated.</span></footer>
    </main>
  );
}
