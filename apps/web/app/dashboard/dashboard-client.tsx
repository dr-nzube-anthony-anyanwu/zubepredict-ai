"use client";

import { useMemo, useState } from "react";
import { createClient } from "../../lib/supabase/client";
import type { DashboardOverview, Experiment, TelegramLink } from "../../lib/types";

type Mode = "auto" | "expert";
type Constitution = Record<string, unknown> & { constitution_id: string; version: number };

function apiBase() {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8040/api/v1").replace(/\/$/, "");
}

function readable(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function DashboardClient({
  initialOverview,
  initialTelegramLink,
}: {
  initialOverview: DashboardOverview;
  initialTelegramLink: TelegramLink;
}) {
  const [overview, setOverview] = useState(initialOverview);
  const [telegramLink, setTelegramLink] = useState(initialTelegramLink);
  const [selectedProject, setSelectedProject] = useState(initialOverview.projects[0]?.id || "");
  const [selectedDataset, setSelectedDataset] = useState(initialOverview.projects[0]?.datasets[0]?.id || "");
  const [mode, setMode] = useState<Mode>("auto");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [linkCode, setLinkCode] = useState<{ code: string; expires: string } | null>(null);
  const [constitution, setConstitution] = useState<Constitution | null>(null);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);

  const project = overview.projects.find((item) => item.id === selectedProject);
  const dataset = project?.datasets.find((item) => item.id === selectedDataset);
  const recentExperiments = useMemo(
    () => [...overview.experiments].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))),
    [overview.experiments],
  );

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    if (!data.session?.access_token) window.location.assign("/login");
    const response = await fetch(`${apiBase()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${data.session?.access_token || ""}`,
        ...init?.headers,
      },
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message || "The request could not be completed.");
    }
    return payload as T;
  }

  async function requestArtifact(path: string): Promise<Response> {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    if (!data.session?.access_token) {
      window.location.assign("/login");
      throw new Error("Please sign in again before opening a report.");
    }
    const response = await fetch(`${apiBase()}${path}`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${data.session.access_token}` },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = payload?.detail;
      throw new Error(
        typeof detail === "string"
          ? detail
          : detail?.message || "The verified report could not be opened.",
      );
    }
    return response;
  }

  function safeDownloadName(response: Response, reportType: string) {
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/i);
    const candidate = match?.[1] || `zubepredict-${reportType.replaceAll("_", "-")}`;
    return candidate.replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 160);
  }

  async function refresh() {
    const next = await request<DashboardOverview>("/dashboard/overview");
    setOverview(next);
  }

  async function perform(name: string, action: () => Promise<void>) {
    setBusy(name);
    setMessage("");
    try { await action(); } catch (error) { setMessage(error instanceof Error ? error.message : "Something went wrong."); }
    finally { setBusy(""); }
  }

  async function createProject(formData: FormData) {
    await perform("project", async () => {
      const created = await request<{ id: string }>("/dashboard/projects", {
        method: "POST",
        body: JSON.stringify({ name: formData.get("name"), description: formData.get("description") || null }),
      });
      await refresh();
      setSelectedProject(created.id);
      setSelectedDataset("");
      setMessage("Project created. It is now available to both web and linked Telegram sessions.");
    });
  }

  async function uploadDataset(formData: FormData) {
    const file = formData.get("dataset");
    const privacyAttested = formData.get("privacy_attested") === "on";
    if (!(file instanceof File) || !file.size || !selectedProject) return setMessage("Choose a project and a CSV or XLSX file first.");
    if (!privacyAttested) return setMessage("Confirm the privacy and authorisation statement before uploading.");
    await perform("upload", async () => {
      const intent = await request<{ storage_path: string; upload_token: string }>("/datasets/upload-intents", {
        method: "POST",
        body: JSON.stringify({ project_id: selectedProject, filename: file.name, content_type: file.type || "application/octet-stream", privacy_attested: true }),
      });
      const supabase = createClient();
      const uploaded = await supabase.storage.from("datasets").uploadToSignedUrl(intent.storage_path, intent.upload_token, file, { contentType: file.type });
      if (uploaded.error) throw new Error("The private upload failed. Please try the file again.");
      const finalized = await request<{ dataset_id: string }>("/datasets/finalize", {
        method: "POST",
        body: JSON.stringify({ project_id: selectedProject, storage_path: intent.storage_path, filename: file.name, content_type: file.type || "application/octet-stream", privacy_attested: true }),
      });
      await refresh();
      setSelectedDataset(finalized.dataset_id);
      setMessage("Dataset validated, fingerprinted and stored privately.");
    });
  }

  async function proposeConstitution(formData: FormData) {
    if (!selectedDataset) return setMessage("Select a dataset first.");
    await perform("constitution", async () => {
      const proposed = await request<Constitution>("/dashboard/constitutions", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: selectedDataset,
          objective: formData.get("objective"),
          target: formData.get("target") || null,
          mode,
          max_candidate_models: mode === "expert" ? Number(formData.get("max_candidate_models")) : null,
          training_timeout_seconds: mode === "expert" ? Number(formData.get("training_timeout_seconds")) : null,
        }),
      });
      setConstitution(proposed);
      setMessage("Constitution proposed. Review it carefully before confirming.");
      await refresh();
    });
  }

  async function confirmAndStart() {
    if (!constitution) return;
    await perform("start", async () => {
      await request(`/dashboard/constitutions/${constitution.constitution_id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ constitution_version: constitution.version, confirmed: true }),
      });
      await request("/dashboard/experiments/start", {
        method: "POST",
        body: JSON.stringify({ constitution_id: constitution.constitution_id, idempotency_key: `web:${crypto.randomUUID()}` }),
      });
      await refresh();
      setConstitution(null);
      setMessage("Experiment queued. The worker continues even if you close this page.");
    });
  }

  async function generateLinkCode() {
    await perform("link", async () => {
      const result = await request<{ code: string; expires_at: string }>("/account-links/telegram/codes", { method: "POST", body: "{}" });
      setLinkCode({ code: result.code, expires: result.expires_at });
      setMessage("Send this one-time code only in a private chat with your ZubePredict bot.");
    });
  }

  async function checkLink() {
    await perform("link-check", async () => {
      const result = await request<TelegramLink>("/account-links/telegram");
      setTelegramLink(result);
      if (result.linked) setLinkCode(null);
      setMessage(result.linked ? "Telegram is securely linked." : "No active Telegram link was found yet.");
    });
  }

  async function revokeLink() {
    if (!window.confirm("Disconnect Telegram from this account? A new code will be required to reconnect.")) return;
    await perform("revoke", async () => {
      await request("/account-links/telegram", { method: "DELETE" });
      setTelegramLink({ linked: false, status: "not_linked" });
      setLinkCode(null);
      setMessage("Telegram access revoked. Your projects and experiments were not deleted.");
    });
  }

  async function loadEvidence(experiment: Experiment) {
    await perform(`evidence-${experiment.id}`, async () => {
      const result = await request<Record<string, unknown>>(`/dashboard/experiments/${experiment.id}/evidence`);
      setEvidence(result);
    });
  }

  async function downloadReport(experiment: Experiment, reportType: string) {
    const previewTypes = new Set(["html", "pdf", "evidence_card", "model_card", "reproducibility_manifest"]);
    const previewWindow = previewTypes.has(reportType) ? window.open("about:blank", "_blank") : null;
    await perform(`report-${experiment.id}-${reportType}`, async () => {
      try {
        const response = await requestArtifact(
          `/dashboard/experiments/${experiment.id}/reports/${encodeURIComponent(reportType)}/content`,
        );
        const contentType = (response.headers.get("Content-Type") || "application/octet-stream").toLowerCase();
        const filename = safeDownloadName(response, reportType);
        const bytes = await response.blob();
        const objectUrl = URL.createObjectURL(new Blob([bytes], { type: contentType }));
        const opensInline = contentType.startsWith("text/html") || contentType.startsWith("application/pdf");
        if (opensInline && previewWindow) {
          previewWindow.location.replace(objectUrl);
        } else {
          previewWindow?.close();
          const link = document.createElement("a");
          link.href = objectUrl;
          link.rel = "noopener noreferrer";
          if (opensInline) link.target = "_blank";
          else link.download = filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
        }
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
        setMessage(
          opensInline ? "Opened the verified report in a new tab." : `Downloaded ${filename}.`,
        );
      } catch (error) {
        previewWindow?.close();
        throw error;
      }
    });
  }

  async function answerClarification(experiment: Experiment, formData: FormData) {
    const pending = experiment.pending_clarification;
    if (!pending) return;
    await perform(`clarify-${experiment.id}`, async () => {
      const taskType = String(formData.get("task_type") || "");
      await request(`/dashboard/experiments/${experiment.id}/clarifications`, {
        method: "POST",
        body: JSON.stringify({
          clarification_id: pending.clarification_id,
          clarification_version: pending.clarification_version,
          response: formData.get("response"),
          task_type: taskType || null,
          target_column: formData.get("target_column") || null,
          confirmed_by_user: formData.get("confirmed_by_user") === "on",
        }),
      });
      await refresh();
      setMessage("Clarification accepted. The same durable experiment has resumed.");
    });
  }

  async function cancelExperiment(experiment: Experiment) {
    if (!window.confirm("Cancel this queued or running experiment? Completed evidence will not be deleted.")) return;
    await perform(`cancel-${experiment.id}`, async () => {
      await request(`/dashboard/experiments/${experiment.id}/cancel`, {
        method: "POST",
        body: JSON.stringify({ confirmation: true }),
      });
      await refresh();
      setMessage("Cancellation was recorded for this owned experiment.");
    });
  }

  return (
    <main className="dashboard-main">
      <header className="topbar" id="overview"><div><p className="kicker">UNIFIED WORKSPACE</p><h1>Good to see you.</h1><p>Projects started on Telegram and the web meet here.</p></div><span className="live-pill"><i /> System connected</span></header>
      {message && <div className="notice info" role="status">{message}<button onClick={() => setMessage("")} aria-label="Dismiss">×</button></div>}

      <section className="metric-grid" aria-label="Workspace summary">
        <Metric label="Projects" value={overview.summary.project_count} note="owned workspaces" />
        <Metric label="Datasets" value={overview.summary.dataset_count} note="privately stored" />
        <Metric label="Experiments" value={overview.summary.experiment_count} note={`${overview.summary.statuses.running || 0} currently running`} />
        <Metric label="Completed" value={overview.summary.statuses.completed || 0} note="verified evidence ready" accent />
      </section>

      <section className="panel-grid" id="projects">
        <article className="panel wide">
          <div className="panel-head"><div><p className="kicker">PROJECTS & DATA</p><h2>Build your next experiment</h2></div><span className="mode-note">Shared with Telegram</span></div>
          <div className="builder-grid">
            <div className="builder-block"><span className="step">1</span><h3>Select a project</h3><select value={selectedProject} onChange={(event) => { setSelectedProject(event.target.value); setSelectedDataset(overview.projects.find((item) => item.id === event.target.value)?.datasets[0]?.id || ""); }}><option value="">Choose project</option>{overview.projects.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.source_channel}</option>)}</select>
              <details><summary>+ Create a new project</summary><form action={createProject} className="compact-form"><input name="name" placeholder="Project name" required maxLength={120} /><textarea name="description" placeholder="Short description (optional)" maxLength={1000} /><button disabled={busy === "project"} className="button secondary">{busy === "project" ? "Creating…" : "Create project"}</button></form></details>
            </div>
            <div className="builder-block"><span className="step">2</span><h3>Add or select data</h3><select value={selectedDataset} onChange={(event) => setSelectedDataset(event.target.value)} disabled={!project}><option value="">Choose dataset</option>{project?.datasets.map((item) => <option key={item.id} value={item.id}>{item.filename} · {item.row_count ?? "?"} rows</option>)}</select>
              <form action={uploadDataset} className="upload-line"><input name="dataset" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required /><label className="confirm-line"><input name="privacy_attested" type="checkbox" required /> I am authorised to use this dataset and have removed direct identifiers.</label><button disabled={busy === "upload" || !selectedProject} className="button secondary">{busy === "upload" ? "Validating…" : "Upload safely"}</button></form>
            </div>
          </div>
          {dataset && <div className="dataset-strip"><strong>{dataset.filename}</strong><span>{dataset.row_count ?? "—"} rows</span><span>{dataset.column_count ?? dataset.schema_columns.length} columns</span><span>SHA-256 verified</span><b>{readable(dataset.source_channel)}</b></div>}
        </article>

        <article className="panel" id="connections">
          <div className="panel-head"><div><p className="kicker">CONNECTION</p><h2>Telegram</h2></div><span className={`status-dot ${telegramLink.linked ? "good" : ""}`}>{telegramLink.linked ? "Linked" : "Not linked"}</span></div>
          <p className="muted">Continue the same projects securely from a private chat.</p>
          {telegramLink.linked ? <><div className="connection-card"><span>✓</span><div><strong>Telegram {telegramLink.telegram_user}</strong><small>Linked {formatDate(telegramLink.linked_at)}</small></div></div><button className="button danger" onClick={revokeLink} disabled={busy === "revoke"}>Revoke link</button></> : <>
            {linkCode && <div className="link-code"><small>ONE-TIME CODE</small><strong>{linkCode.code.slice(0,4)} {linkCode.code.slice(4)}</strong><span>Expires {formatDate(linkCode.expires)}</span><p>Private bot chat: <b>/zlink {linkCode.code}</b></p></div>}
            <button className="button primary" onClick={generateLinkCode} disabled={busy === "link"}>{linkCode ? "Generate a new code" : "Connect Telegram"}</button>
            {linkCode && <button className="button ghost" onClick={checkLink} disabled={busy === "link-check"}>I sent the code — check link</button>}
          </>}
        </article>
      </section>

      <section className="panel experiment-builder" id="experiments">
        <div className="panel-head"><div><p className="kicker">NEW EXPERIMENT</p><h2>Configure with guardrails</h2></div><div className="mode-switch" aria-label="Experiment mode"><button className={mode === "auto" ? "active" : ""} onClick={() => setMode("auto")}>Auto mode</button><button className={mode === "expert" ? "active" : ""} onClick={() => setMode("expert")}>Expert mode</button></div></div>
        <form action={proposeConstitution} className="experiment-form">
          <label>Objective<textarea name="objective" required minLength={3} maxLength={2000} placeholder="For example: predict which synthetic records have a positive target." /></label>
          <label>Target column<input name="target" list="columns" placeholder={mode === "auto" ? "Optional — let ZubePredict assess" : "Choose a validated column"} required={mode === "expert"} /><datalist id="columns">{dataset?.schema_columns.map((column) => <option value={column} key={column} />)}</datalist></label>
          {mode === "expert" && <div className="expert-fields" style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}><label>Candidate model limit<input name="max_candidate_models" type="number" min="1" max="20" defaultValue="8" required /></label><label>Training timeout (seconds)<input name="training_timeout_seconds" type="number" min="10" max="86400" defaultValue="900" required /></label></div>}
          <div className="guardrail"><span>◈</span><div><strong>{mode === "auto" ? "Auto Mode" : "Expert Mode"}</strong><p>{mode === "auto" ? "Task, validation and metric are proposed from the validated dataset." : "You select the target; ZubePredict still enforces leakage, ownership and evidence checks."}</p></div></div>
          <button className="button primary" disabled={busy === "constitution" || !selectedDataset}>{busy === "constitution" ? "Assessing…" : "Create Experiment Constitution"}</button>
        </form>
        {constitution && <div className="constitution"><div><p className="kicker">REVIEW BEFORE STARTING</p><h3>Experiment Constitution v{constitution.version}</h3></div><dl>{["task","target","prediction_point","validation_method","primary_metric","exclusions","resource_budget","intended_use_warning"].map((key) => <div key={key}><dt>{readable(key)}</dt><dd>{typeof constitution[key] === "object" ? JSON.stringify(constitution[key]) : String(constitution[key] ?? "Not specified")}</dd></div>)}</dl><label className="confirm-line"><input type="checkbox" id="constitution-confirm" /> I reviewed this exact Constitution version.</label><button className="button primary" onClick={() => { const box = document.querySelector<HTMLInputElement>("#constitution-confirm"); if (!box?.checked) return setMessage("Tick the confirmation box after reviewing the Constitution."); confirmAndStart(); }} disabled={busy === "start"}>Confirm and queue experiment</button></div>}
      </section>

      <section className="panel" id="evidence">
        <div className="panel-head"><div><p className="kicker">EXPERIMENT HISTORY</p><h2>Progress and verified evidence</h2></div><button className="button ghost" onClick={() => perform("refresh", refresh)} disabled={busy === "refresh"}>Refresh status</button></div>
        {recentExperiments.length ? <div className="experiment-list">{recentExperiments.map((item) => <ExperimentRow key={item.id} experiment={item} busy={busy} onEvidence={() => loadEvidence(item)} onReport={(reportType) => downloadReport(item, reportType)} onCancel={() => cancelExperiment(item)} />)}</div> : <div className="empty-inline"><strong>No experiments yet</strong><span>Create a Constitution above or begin through Telegram.</span></div>}
        {recentExperiments.filter((item) => item.pending_clarification).map((item) => {
          const data = item.pending_clarification?.data as Record<string, unknown> | undefined;
          const taskDecision = data?.kind === "task_decision";
          return <form action={(formData) => answerClarification(item, formData)} className="constitution" key={`clarification-${item.id}`}><p className="kicker">CLARIFICATION REQUIRED</p><h3>{String(data?.question || "Please clarify this experiment before it continues.")}</h3><label>Answer<textarea name="response" required maxLength={2000} /></label>{taskDecision && <div className="expert-fields" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}><label>Confirmed task<select name="task_type" required><option value="">Choose task</option><option value="binary_classification">Binary classification</option><option value="multiclass_classification">Multiclass classification</option><option value="regression">Regression</option><option value="clustering">Clustering</option><option value="anomaly_detection">Anomaly detection</option><option value="time_series_forecasting">Time-series forecasting</option></select></label><label>Target column<input name="target_column" list="columns" /></label><label className="confirm-line"><input name="confirmed_by_user" type="checkbox" required /> I explicitly confirm this task decision.</label></div>}<button className="button primary" disabled={busy === `clarify-${item.id}`}>Answer and resume</button></form>;
        })}
        {evidence && <EvidenceView payload={evidence} onClose={() => setEvidence(null)} />}
      </section>
    </main>
  );
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function displayValue(value: unknown) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (value === null || value === undefined || value === "") return "Not recorded";
  return String(value);
}

function metricValue(value: unknown) {
  const metric = objectValue(value);
  return displayValue(metric.mean ?? metric.value ?? value);
}

function EvidenceView({ payload, onClose }: { payload: Record<string, unknown>; onClose: () => void }) {
  const envelope = objectValue(payload.evidence);
  const leaderboard = Array.isArray(envelope.model_leaderboard) ? envelope.model_leaderboard : [];
  const selectedModel = displayValue(envelope.winner);
  const winner = leaderboard.map(objectValue).find((item) => String(item.model_name) === String(envelope.winner)) || objectValue(leaderboard[0]);
  const metrics = objectValue(winner.metrics);
  const primaryMetric = displayValue(envelope.primary_metric);
  const limitations = Array.isArray(envelope.limitations) ? envelope.limitations : [];
  const exclusions = Array.isArray(envelope.exclusions) ? envelope.exclusions : [];

  return <article className="evidence-card" aria-live="polite">
    <div className="panel-head"><div><p className="kicker">IMMUTABLE EVIDENCE ENVELOPE</p><h3>Verified result</h3></div><button className="text-button" onClick={onClose}>Close</button></div>
    <div className="evidence-summary"><strong>What this result says</strong><p>{displayValue(payload.deterministic_summary)}</p></div>
    <div className="evidence-facts">
      <div><span>Selected model</span><strong>{readable(selectedModel)}</strong></div>
      <div><span>{readable(primaryMetric)}</span><strong>{metricValue(metrics[primaryMetric])}</strong></div>
      <div><span>Task</span><strong>{readable(displayValue(envelope.task_type))}</strong></div>
      <div><span>Target</span><strong>{readable(displayValue(envelope.target))}</strong></div>
    </div>
    <div className="evidence-warning"><strong>Important use limitation</strong><p>{displayValue(envelope.intended_use_warning)}</p></div>
    <div className="evidence-columns">
      <section><h4>Study design</h4><dl><dt>Validation</dt><dd>{displayValue(envelope.validation_strategy)}</dd><dt>Excluded fields</dt><dd>{exclusions.length ? exclusions.map(displayValue).join(", ") : "None recorded"}</dd><dt>Constitution version</dt><dd>{displayValue(envelope.constitution_version)}</dd></dl></section>
      <section><h4>Limitations</h4><ul>{limitations.length ? limitations.map((item, index) => <li key={`${index}-${displayValue(item)}`}>{displayValue(item)}</li>) : <li>No additional limitations were recorded.</li>}</ul></section>
    </div>
    <div className="evidence-integrity"><strong>Integrity verified</strong><span>Experiment <code>{displayValue(envelope.experiment_id)}</code></span><span>Evidence hash <code>{displayValue(envelope.evidence_hash)}</code></span></div>
    <details className="evidence-technical"><summary>View technical Evidence Envelope</summary><pre>{JSON.stringify(payload, null, 2)}</pre></details>
  </article>;
}

function Metric({ label, value, note, accent = false }: { label: string; value: number; note: string; accent?: boolean }) {
  return <article className={`metric ${accent ? "accent" : ""}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function ExperimentRow({ experiment, busy, onEvidence, onReport, onCancel }: { experiment: Experiment; busy: string; onEvidence: () => void; onReport: (reportType: string) => void; onCancel: () => void }) {
  const primary = experiment.model_leaderboard[0];
  const metricValue = primary && Object.entries(primary.metrics || {})[0];
  const downloadable = experiment.reports.filter((report) => report.report_type !== "evidence");
  return <article className="experiment-row"><div className="experiment-title"><span className={`state ${experiment.status}`} /> <div><strong>{experiment.objective || "Untitled experiment"}</strong><small>{experiment.id.slice(0,8)} · {readable(experiment.source_channel)} · {formatDate(experiment.created_at)}</small></div></div><div className="experiment-meta"><span>{experiment.winner_model || primary?.model_name || "Awaiting model"}</span><strong>{metricValue ? `${readable(metricValue[0])}: ${String(metricValue[1])}` : `${experiment.progress}%`}</strong></div><span className={`status-chip ${experiment.status}`}>{readable(experiment.status)}</span><div className="row-actions"><button onClick={onEvidence} disabled={experiment.status !== "completed" || busy.includes(experiment.id)}>Evidence</button>{downloadable.map((report) => <button key={report.id} onClick={() => onReport(report.report_type)} disabled={experiment.status !== "completed" || busy.includes(experiment.id)} title={report.sha256 ? `SHA-256 ${report.sha256}` : undefined}>{readable(report.report_type)} ↗</button>)}{["queued","running","needs_clarification"].includes(experiment.status) && <button onClick={onCancel} disabled={busy.includes(experiment.id)}>Cancel</button>}</div></article>;
}
