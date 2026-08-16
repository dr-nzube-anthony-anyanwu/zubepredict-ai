# ZubePredict AI: Owner's Product Guide

This is the plain-language guide to understanding, testing, demonstrating and explaining
ZubePredict AI. It is written for the product owner, first-time users and non-technical audiences.

Last updated: 2026-08-16
Current state: Stages 0-17 are complete locally. Stage 18 and public deployment have not begun.

---

## 1. The whole product in one sentence

**ZubePredict turns an authorised table of data and a real-world question into a tested prediction
experiment, understandable evidence and shareable reports.**

An even simpler version is:

> You give ZubePredict a spreadsheet and a question. It checks the data, compares suitable
> prediction methods fairly, and gives you evidence you can inspect instead of asking you to trust
> a guess.

Its public promise is: **Your data has answers. ZubePredict builds the evidence.**

## 2. Think of it like a careful science team

Imagine that you have a box of school records and want to know which pupils may need extra help. A
careless person might glance at a few records and guess. A careful science team would:

1. make sure it is allowed to use the records;
2. check whether they are complete and usable;
3. ask exactly what you want to learn;
4. write down the investigation rules before starting;
5. test several suitable methods fairly;
6. keep a notebook of what it did;
7. show the winning result and its weaknesses; and
8. give you a report another person can inspect.

ZubePredict behaves like that organised team. It does not merely chat about data. It manages a
controlled experiment and preserves the evidence behind the answer.

## 3. The problem it solves

Organisations often have useful information trapped in CSV files, Excel workbooks and databases.
They may want to ask:

- Which appointments are most likely to be missed?
- Which customers may not return?
- How much demand should we expect next month?
- Which records look unusual and need human review?
- Are there meaningful groups hidden inside the data?
- Which factors are associated with an outcome?

Turning those questions into reliable experiments normally requires specialists, several tools and
careful record-keeping. A general chatbot may explain ideas, but it should not invent a metric,
silently train a model or decide what evidence is trustworthy.

ZubePredict joins the journey together: question, data checks, agreed experiment, durable training,
verified results and readable reports.

## 4. Who may find it useful?

- Eye-care and healthcare research teams using properly authorised, de-identified data.
- Clinic operations teams studying attendance, follow-up or demand.
- Researchers who need repeatable prediction experiments.
- Small and medium-sized businesses studying customer or operational outcomes.
- Analysts who want a governed workflow instead of disconnected notebooks.
- Product owners who want to continue work through either web or Telegram.
- Technical teams that need an authenticated API and audit history behind the interface.

Eye care is an important product focus and reporting format, but the underlying workflow can support
other authorised tabular-data problems.

## 5. Questions it can investigate

| Task | Simple meaning | Example |
| --- | --- | --- |
| Binary classification | Choose between two outcomes | Will an appointment be attended: yes or no? |
| Multiclass classification | Choose one of several outcomes | Which service category is most likely? |
| Regression | Predict a number | How many days might the wait be? |
| Clustering | Find natural groups | Which records seem to belong together? |
| Anomaly detection | Find unusual records | Which activity looks different enough to review? |
| Time-series forecasting | Estimate what comes next over time | How many visits may occur next month? |

Prediction is an estimate, not certainty. A model can be wrong, biased, incomplete or unsuitable for
a new population. ZubePredict therefore records limitations and intended-use warnings.

## 6. What it is not

ZubePredict is not:

- a doctor or autonomous diagnostic system;
- a replacement for clinical, scientific or business judgement;
- proof that one factor caused another;
- a guarantee about a future event;
- permission to upload data you do not own or control;
- a way to make patient information public;
- a magic button that fixes poor data; or
- a Telegram agent with access to the owner's computer or terminal.

For healthcare work, describe current outputs as **decision support and research evidence requiring
appropriate human, scientific and regulatory validation**.

---

## 7. How a complete experiment works

### 1. Sign in

Supabase Auth verifies the web account. The backend uses that account to own projects, datasets,
experiments and reports. Ownership never comes from a name or user ID typed into a chat prompt.

### 2. Create a project

A project is a folder for one area of work, such as `Eye clinic follow-up study`. Web and Telegram
projects live in the same backend, not in separate systems.

### 3. Upload an authorised dataset

The user uploads a supported table such as CSV or XLSX. The system checks its type and size, gives it
a safe internal name, stores it privately and calculates a SHA-256 fingerprint. The fingerprint is
like a unique digital thumbprint: changing the file changes the fingerprint.

### 4. State the objective

The objective is the plain-language question, for example:

> Using this synthetic dataset, predict whether a record will return within 60 days.

### 5. Profile and assess readiness

Profiling is like inspecting ingredients before cooking. The backend examines columns, types,
missing values and other characteristics. If the task or target is unclear, it asks a precise
clarification question and pauses.

### 6. Create the Experiment Constitution

The Constitution is the versioned rulebook written before training. It records:

- task and target;
- prediction point;
- validation strategy;
- primary metric;
- exclusions;
- resource budget; and
- intended-use warning.

This stops the goal from being quietly changed after seeing a result.

### 7. Confirm it

The user must review and explicitly confirm the exact Constitution version. The assistant cannot
approve it on the user's behalf.

### 8. Queue the experiment

The backend quickly creates a durable `queued` job. A background worker performs the longer work, so
closing the page or losing Telegram does not cancel the backend experiment.

### 9. Run the model tournament

The deterministic Python pipeline prepares the data, applies leakage protections, trains suitable
candidate models and compares them under the same recorded validation rules. The winner comes from
measurements, not the conversational AI's preference.

### 10. Build the evidence and reports

Results enter a structured evidence envelope containing verified metrics, leaderboard information,
limitations and integrity references. The backend generates all report formats from that envelope.
Hermes may explain the evidence, but cannot rewrite it. If an explanation conflicts with the
evidence, the evidence wins.

## 8. The technology under the bonnet

```text
Web dashboard or Telegram
        -> FastAPI security and product services
        -> LangGraph experiment workflow
        -> Redis queue and Dramatiq worker
        -> deterministic Python ML pipeline
        -> private Supabase records, evidence and reports
```

- **Next.js:** the visual website and authenticated dashboard.
- **Supabase Auth:** verifies web users.
- **FastAPI:** the guarded product doorway; validates requests and ownership.
- **LangGraph:** stores the official workflow state and permitted next step.
- **Redis:** supports the queue and distributed limits.
- **Dramatiq worker:** performs long jobs away from the browser request.
- **Python ML pipeline:** profiles data, trains candidates and measures evidence.
- **Supabase Postgres:** stores authoritative records and audit history.
- **Supabase Storage:** privately stores datasets and artifacts.
- **Hermes Agent:** provides the restricted Telegram conversation.
- **OpenRouter:** supplies Hermes with a language model for conversation and explanation.

Remember: **the language model helps people communicate; the deterministic backend owns identity,
permissions, state, metrics and reports.**

## 9. The website and dashboard pages

### Homepage — `/`

The homepage explains the problem, journey, model tournament, evidence outputs, safety boundary and
web/Telegram continuity. Use it to explain the “why” before showing the workspace's “how.”

### Overview — `/dashboard`

The control room. It answers: **What is happening in my workspace now?**

### Projects — `/dashboard/projects`

Create/select projects and privately upload authorised datasets. It answers: **What data are we
investigating, and where does it belong?**

### Experiments — `/dashboard/experiments`

State the objective, prepare and confirm a Constitution, queue work, answer clarification, follow
status or cancel an owned job. It answers: **What are we testing and under which rules?**

### Evidence — `/dashboard/evidence`

Inspect completed evidence, leaderboards and generated artifacts. It answers: **What did the
experiment measure, and where is the supporting record?**

### Connections — `/dashboard/connections`

Link or revoke a numerical Telegram identity using a short-lived one-time code. It answers: **How do
I use this same owned workspace from Telegram?**

## 10. Telegram: another door to the same workspace

```text
Private Telegram chat
  -> official Telegram Bot API
  -> pinned Hermes Telegram gateway
  -> restricted ZubePredict plugin
  -> the same FastAPI backend
```

Useful natural-language requests include:

- `Show my projects.`
- `Create a new project called Follow-up study.`
- `Upload this to the selected project.` with a real file attachment
- `Profile the dataset and assess readiness.`
- `Show me the Experiment Constitution.`
- `I confirm this exact Constitution version.`
- `Start the experiment.`
- `Show my experiment status.`
- `Show my verified results.`
- `Give me the temporary evidence report.`
- `Cancel my active experiment.` followed by confirmation
- `Reset this Telegram session.`

Use `Show my experiment status` because `/status` may be a built-in gateway command in the pinned
Hermes version.

Telegram is private-DM only in the current setup. Trusted identity comes from Telegram's numerical
metadata outside message text. Writing “my ID is 123” changes nothing. Unknown or revoked users are
rejected before the LLM or product tools. A session reset clears selections, not backend experiments.

### Linking Telegram

1. Sign in on the dashboard and open **Connections**.
2. Generate and copy the short-lived code.
3. In the private bot chat, send `/zlink YOUR_CODE` with the real code.
4. Return to the dashboard and refresh.
5. Confirm the linked identity appears safely.

The code is single-use and stored safely as a hash where appropriate. Revocation blocks new Telegram
product operations. Re-linking needs a new code. Never put bot tokens, OpenRouter keys, Supabase keys
or Hermes service credentials in chat.

## 11. Reports and artifacts

- **EyeCare Evidence Card:** concise, plain-language experiment summary. Start here.
- **HTML Evidence Report:** styled browser report with guided and expandable sections.
- **PDF Evidence Report:** portable, printable version of the authoritative record.
- **Model Card:** intended use, evaluation and limitations of the selected model.
- **Prediction CSV/Excel:** authorised row-level output when appropriate; it remains private data.
- **Reproducibility Manifest:** the experiment's recipe card—versions and fingerprints needed to
  understand or reproduce the run.
- **Evidence envelope:** machine-readable source of truth behind every human-facing artifact.

The web, Telegram and API deliver the same backend-generated artifacts. Report access is owned and
short-lived; a Telegram report link normally expires after about five minutes. Permanent public
bucket URLs and local filesystem paths must never be exposed.

## 12. Reading results carefully

- **Accuracy:** share of predictions that were correct; it can mislead on unbalanced outcomes.
- **Precision:** when the model says “yes,” how often is it right?
- **Recall:** of the real “yes” cases, how many did it find?
- **F1:** a balance of precision and recall.
- **ROC AUC:** how well a binary model ranks positive above negative cases across thresholds.
- **MAE:** average error size for number predictions, in the original unit.
- **Calibration:** whether stated probabilities behave like those probabilities over many cases.
- **Leaderboard:** fair comparison of candidates under the recorded validation rules.

Always ask:

1. What exactly was the target?
2. Was the data suitable and representative?
3. How was the model validated?
4. What does the primary metric leave out?
5. What limitations and warning were recorded?

## 13. Safety in plain language

- Authentication proves the web account.
- Trusted Telegram metadata—not prompt text—establishes channel identity.
- Backend ownership checks protect every project, dataset, experiment and report.
- Database RLS adds row-level separation.
- Private storage and expiring links protect files.
- File checks reject unsupported, oversized and suspicious uploads.
- Fingerprints and integrity hashes help detect changes.
- Constitution confirmation preserves human approval.
- Quotas, concurrency limits and timeouts bound resource use.
- Owned cancellation safely stops eligible work.
- Audit events record important actions without deliberately storing secrets.
- Retention controls support governed deletion.
- Telegram cannot use arbitrary terminal, shell, filesystem, package or database tools.

Never use real patient data for a casual demo. Use the fictional sample included here.

---

## 14. Start ZubePredict locally

These steps assume `.env`, Supabase, Python 3.11, `.venv`, Node packages and Docker Desktop are
already configured according to `README.md`. Open four separate PowerShell windows.

### Terminal 1 — Redis

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
docker compose up redis
```

### Terminal 2 — FastAPI on 8040

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
python -m uvicorn zubepredict_api.main:app --host 127.0.0.1 --port 8040
```

Visit `http://127.0.0.1:8040/health`. The correct route is `/health`, not `/api/v1/health`.

### Terminal 3 — worker

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
python -m dramatiq apps.worker.tasks --processes 1 --threads 1
```

### Terminal 4 — frontend on 3040

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI\apps\web
npm run dev
```

Visit `http://localhost:3040`.

### Optional Terminal 5 — configured Telegram gateway

Only after the private Hermes environment and restricted toolset are configured:

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\integrations\hermes\start-telegram-gateway.ps1
```

Never run the disabled aiogram fallback at the same time.

## 15. Your safe first experiment, step by step

Use `samples\eye_clinic_followup_demo.csv`. It has 60 fictional rows and contains no names, patient
IDs or real patient data.

### A. Meet the homepage

1. Open `http://localhost:3040`.
2. Read the hero and “question to evidence” sections.
3. Notice the decision-support warning.
4. Open the workspace and sign in.

### B. Create the project and upload

1. Open **Projects**.
2. Create `Eye clinic follow-up demo`.
3. Select it.
4. Choose the upload control and select `samples\eye_clinic_followup_demo.csv`.
5. Confirm the authorisation/de-identification statement because it is synthetic.
6. Upload it.

Expected: the project and safe dataset reference appear in your owned workspace.

### C. Prepare the experiment

1. Open **Experiments**.
2. Select the project and dataset.
3. Enter:

   ```text
   Using this synthetic dataset, predict whether a record will return within 60 days.
   ```

4. Use target column `returned_within_60_days`.
5. Choose guided mode if offered.
6. Create the Constitution.
7. Check task, target, prediction point, validation, metric, exclusions, budget and warning.
8. If asked for clarification, answer the exact question.
9. When everything is correct, confirm that exact Constitution version.

### D. Queue and observe

1. Queue the experiment and expect `queued` quickly—not instant completion.
2. Refresh status.
3. Close and reopen the page.
4. Return to **Experiments**.

The job should still exist because the worker, not the browser tab, owns it.

| Status | Meaning |
| --- | --- |
| queued | Safely waiting for the worker. |
| profiling | Inspecting the dataset. |
| needs clarification | Waiting for a precise human answer. |
| training | Testing candidates. |
| evaluating | Comparing recorded results. |
| reporting | Generating artifacts. |
| completed | Verified evidence and reports are ready. |
| failed | Stopped safely; inspect the safe reason. |
| cancelled | An authorised user cancelled it. |

### E. Inspect the evidence

1. Open **Evidence** and refresh.
2. Select the completed experiment.
3. Read the plain-language summary.
4. Compare the selected model and primary metric with the leaderboard.
5. Open the Evidence Card, HTML report, PDF, Model Card and Reproducibility Manifest.
6. Inspect prediction output only if authorised and generated.

All artifacts should agree on the experiment, fingerprint, model and metrics.

### F. Check cross-channel continuity

If Telegram is linked:

1. Say `Show my projects.`
2. Confirm the web-created project appears.
3. Say `Show my experiment status.`
4. Say `Show my verified results.`
5. Say `Give me the temporary evidence report.`
6. Open the full link promptly.

Web and Telegram should show the same backend record, not duplicate experiments or reports.

## 16. Whole-product feature checklist

| Test | Passing result |
| --- | --- |
| Read homepage on desktop/mobile | Value and safety boundary are understandable. |
| Open dashboard while signed out | You are redirected to sign in. |
| Create a project | It appears in the owner's workspace. |
| Upload the fictional CSV | Safe dataset reference appears; no public URL. |
| Prepare an experiment | Readiness and clarification are visible. |
| Review Constitution | Training requires explicit confirmation. |
| Queue, close and reopen | The same job and status return. |
| Open completed evidence | Metrics come from the evidence envelope. |
| Compare report formats | Artifacts agree and are readable. |
| Link Telegram with a fresh code | Linked numerical identity appears safely. |
| Create in one channel, view in the other | Same owner and backend record appear. |
| Revoke Telegram | New Telegram product operations are refused. |
| Reset Telegram | Selections clear; experiments remain. |
| Cancel an owned test | Only that owner's eligible job is cancelled. |
| Reuse an expired report link | It no longer works. |
| Message from an unknown account | It is denied before LLM/tools. |

Do not guess real connection codes against the bot. Automated tests cover guessing, expiry, reuse,
collisions, rate limits and cross-user takeover.

## 17. Stop everything safely

Press `Ctrl + C` in the frontend, backend, worker and Hermes windows. Then run:

```powershell
docker compose stop redis
```

Or remove stopped development containers and their network:

```powershell
docker compose down
```

This does not delete hosted Supabase records. Do not add `-v` unless you intentionally want to remove
local Docker volumes and understand the consequence.

---

## 18. A five-minute demonstration

### Minute 1: the problem

> Organisations have valuable data but often lack a safe, repeatable path to reliable prediction
> evidence. ZubePredict connects the question, checks, model comparison and final evidence.

Show the homepage.

### Minute 2: ownership and data

Show **Projects** and the fictional dataset.

> Every project, dataset, experiment and report has an owner. Files remain private and receive a
> fingerprint so we know which exact data version produced a result.

### Minute 3: the Constitution

Show **Experiments**.

> Before training, the system writes down the task, target, validation, metric, budget and warning.
> The human confirms that exact version, preventing silent goal changes.

### Minute 4: the evidence

Show **Evidence**.

> Candidate models compete under recorded rules. The leaderboard, selected result, limitations and
> integrity references are stored in one evidence envelope. The chatbot cannot invent the score.

### Minute 5: continuity

Show **Connections** and optionally Telegram.

> Web and Telegram are two doors into the same owned workspace. Jobs continue after a page or chat
> closes, and Telegram receives only narrow product tools—not computer access.

Finish with:

> ZubePredict does not replace professional judgement. It makes the path from data to decision
> evidence more structured, inspectable and repeatable.

## 19. Ready-made explanations

### One line

> ZubePredict turns authorised spreadsheet data and a real-world question into a governed prediction
> experiment, verified evidence and understandable reports.

### Thirty seconds

> ZubePredict is an AI-assisted prediction workspace. A user provides authorised tabular data and a
> question; it checks readiness, agrees experiment rules, compares suitable models and produces
> evidence that can be inspected from web or Telegram. The assistant helps with conversation, while
> the controlled backend owns permissions, measurements and reports. It supports decisions and
> research rather than replacing expert judgement.

### Two minutes

> ZubePredict helps an authorised user investigate a prediction question without losing scientific
> and security controls. The user creates a project, uploads a private table and states the objective.
> ZubePredict profiles the data, checks readiness and asks precise questions when needed.
>
> Before training, it creates a versioned Experiment Constitution covering the task, target,
> prediction point, validation, metric, exclusions, budget and warning. The user explicitly approves
> it. A background worker then compares suitable models and records the result in an evidence
> envelope.
>
> From that same evidence, the backend creates an Evidence Card, HTML/PDF reports, Model Card,
> authorised prediction files and reproducibility manifest. Web, Telegram and API access the same
> owned records. The language model may explain evidence, but cannot choose the owner or rewrite a
> verified metric. The value is a clearer, safer and more defensible path from data to decision
> support.

## 20. Marketing pillars and honest claims

The strongest product pillars are:

1. **From question to evidence:** one connected journey, not a loose chat or isolated score.
2. **Guardrails before training:** readiness, clarification and a human-approved Constitution.
3. **Evidence over confidence:** metrics, leaderboards, warnings, fingerprints and manifests.
4. **One workspace across channels:** web, Telegram and API share ownership and records.
5. **Understandable but inspectable:** guided reports plus deeper technical evidence.
6. **Responsible by design:** privacy, restricted tools, quotas, audit and expiring access.

Good claims:

- “Turns authorised tabular data into structured prediction evidence.”
- “Compares suitable candidates under recorded experiment rules.”
- “Keeps web and Telegram work in one owned backend workspace.”
- “Generates readable artifacts from one authoritative evidence envelope.”
- “Allows long-running work to continue after a page or chat closes.”
- “Separates conversational AI from authoritative metrics and ownership.”

Never claim:

- it always finds the right answer;
- it replaces a doctor or data scientist;
- it diagnoses disease or eliminates bias;
- it guarantees future outcomes;
- it makes every dataset useful;
- it is publicly deployed, production-certified or medically approved.

Possible headlines:

- **Your data has answers. ZubePredict builds the evidence.**
- **From raw data to defensible decisions.**
- **Ask the question. Agree the rules. Inspect the evidence.**
- **Prediction work that remembers how it reached the result.**

## 21. ZubePredict versus a general chatbot

| General chatbot | ZubePredict |
| --- | --- |
| Primarily produces conversation | Runs a controlled backend workflow |
| May answer from prompt context | Stores authoritative state in Supabase |
| Can sound confident without evidence | Metrics must come from the evidence envelope |
| Usually has no resource ownership | Enforces ownership in FastAPI and database rules |
| Closing chat may lose working context | Worker jobs continue independently |
| Usually gives one response | Produces versioned reports and manifests |

ZubePredict uses a language model for helpful conversation, but places it behind strict identity and
tool boundaries rather than treating it as scientific truth.

## 22. Frequently asked questions

**Does it train models?**
Yes. The deterministic Python pipeline compares suitable machine-learning candidates for supported
tabular tasks under the confirmed Constitution.

**Can I use Excel?**
The safe web/Telegram starter flow supports CSV and XLSX. Only advertise formats deliberately enabled
and tested for the relevant channel.

**Does Telegram have a separate copy?**
No. Telegram and web call the same backend and owned records.

**Can the bot access my computer?**
Customer Telegram sessions cannot use arbitrary terminal, shell, code, package or filesystem tools.

**Who chooses the owner?**
Supabase Auth establishes the web user. Trusted Telegram metadata is linked through a one-time code.
Prompt text cannot change ownership.

**Does work continue after I close the page?**
Yes, after it is durably queued, provided the backend worker remains running.

**Are reports made up by the chatbot?**
No. The backend generates them from the structured evidence envelope. Hermes may only explain them.

**Can I share any temporary report link?**
Treat every report as private and follow organisational policy. Short-lived does not mean public.

**Can I upload patient data?**
Only under proper legal, ethical, governance, security and de-identification controls. Never use real
patient data for a demo.

**Why did it ask a question instead of training?**
Readiness found an essential ambiguity. Answer the exact backend question.

**Why is it not instant?**
Real training and comparison take compute. The queue keeps the interface responsive.

**Is it ready for the public internet?**
No public deployment has occurred. Stage 18 and remaining production operational gates are recorded
in `IMPLEMENTATION.md`.

## 23. Small glossary

- **API:** a controlled doorway software uses to request work.
- **Artifact:** an output such as a report, card, manifest or prediction file.
- **Audit event:** a safe record that an important action occurred.
- **Dataset fingerprint:** a hash identifying exact file contents.
- **De-identified:** identifying details removed or transformed under an appropriate process.
- **Evidence envelope:** authoritative structured experiment facts and results.
- **Experiment Constitution:** versioned rules agreed before training.
- **Feature:** an input column used to learn patterns.
- **Hermes:** the pinned runtime providing the restricted Telegram conversation.
- **LangGraph:** the component managing durable experiment steps and state.
- **LLM:** language model for conversation, not authoritative identity or metrics.
- **Model:** learned mathematical pattern used to estimate an outcome.
- **RLS:** database rules restricting which account can access which rows.
- **Target:** outcome column the model estimates.
- **Validation:** fair testing used to estimate how a model may generalise.
- **Worker:** separate process performing queued long-running work.

## 24. If you forget everything

Remember these seven points:

1. ZubePredict turns an authorised dataset and question into a governed experiment.
2. A human confirms the Constitution before training.
3. The backend—not the chatbot—owns verified metrics.
4. Worker jobs survive closed web pages or disconnected chats.
5. Web, Telegram and API use the same owned records.
6. Reports come from one authoritative evidence envelope and remain private.
7. Outputs support research and decisions; they do not replace professional judgement.

## 25. Read next

- `README.md` — technical overview and setup.
- `IMPLEMENTATION.md` — history, corrections, verification and stopping point.
- `docs/01-BEGINNER-SETUP-WINDOWS.md` — first-time Windows setup.
- `docs/15-STAGE-14-TELEGRAM.md` — Telegram gateway and smoke test.
- `docs/16-STAGE-15-DASHBOARD.md` — dashboard and linking.
- `docs/17-STAGE-16-REPORTING.md` — evidence and artifact delivery.
- `docs/18-STAGE-17-SECURITY.md` — security controls and production checklist.

When presenting ZubePredict, start with the human problem and the evidence journey. Explain the
technology only when the listener asks. The clearest final message is:

> **We made the path from a real question to inspectable prediction evidence clearer, safer and
> easier to continue across the tools people already use.**
