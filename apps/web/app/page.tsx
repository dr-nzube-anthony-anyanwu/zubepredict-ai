const stages = [
  "Understand the objective",
  "Inspect data quality",
  "Choose the ML task",
  "Run a model tournament",
  "Explain and report",
];

export default function Home() {
  return (
    <main>
      <nav><span className="mark">ZP</span><strong>ZubePredict AI</strong><span className="badge">Starter v0.1</span></nav>
      <section className="hero">
        <p className="eyebrow">AUTONOMOUS DATA SCIENCE, WITH EVIDENCE</p>
        <h1>From raw dataset to a defensible model decision.</h1>
        <p className="lead">ZubePredict profiles the data, identifies the task, compares appropriate models and explains what won—and why.</p>
        <div className="actions"><a href="http://localhost:8040/docs">Open API workspace</a><span>Telegram and project dashboard arrive in later stages.</span></div>
      </section>
      <section className="grid">
        {stages.map((stage, index) => <article key={stage}><small>0{index + 1}</small><h2>{stage}</h2></article>)}
      </section>
      <footer>Built as a stage-based foundation for ZubePredict AI.</footer>
    </main>
  );
}
