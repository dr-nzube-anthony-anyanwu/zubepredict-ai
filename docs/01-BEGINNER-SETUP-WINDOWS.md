# Beginner Setup Guide for Windows

Follow one numbered section at a time. Do not rush and do not paste secret keys into chat, screenshots or GitHub.

## Part A — Unzip and open the project

1. Download `ZubePredict-AI-Starter.zip`.
2. Open your Windows **Downloads** folder.
3. Right-click the ZIP file.
4. Click **Extract All**.
5. Choose a simple location such as `Documents\Projects`.
6. Click **Extract**.
7. Open Visual Studio Code.
8. Click **File** and then **Open Folder**.
9. Select the extracted `ZubePredict-AI-Starter` folder.
10. If VS Code asks whether you trust the authors, choose **Yes, I trust the authors** because this is your project package.

Make sure VS Code shows files such as `README.md`, `compose.yaml` and `pyproject.toml`. If you only see another ZIP or one empty folder, you opened the wrong level.

## Part B — Open a terminal

1. In VS Code, click **Terminal**.
2. Click **New Terminal**.
3. A panel opens at the bottom.
4. The path should end with `ZubePredict-AI-Starter`.

Run the tailored diagnostic from the project root:

```powershell
.\scripts\diagnose.ps1
```

Expected result:

- The project `.venv` should report Python 3.11.
- Node, npm, Git, Docker and Docker Compose should report versions.
- Docker Desktop should be running and the temporary Redis smoke test should pass.
- A warning that this extracted folder is not a Git worktree does not prevent local use.

If `docker` is not recognised, open Docker Desktop and wait until it says the engine is running. Close and reopen the VS Code terminal.

If the diagnostic says `.venv` is missing, create it with the installed Python 3.11 executable and install the locked dependencies:

```powershell
$python311 = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $python311 -m venv .venv
.\.venv\Scripts\python.exe -m pip install uv
.\.venv\Scripts\uv.exe sync --extra dev --extra ml
.\scripts\diagnose.ps1
```

## Part C — Create your private environment file

In PowerShell, run:

```powershell
Copy-Item .env.example .env
```

You should now see `.env` in VS Code. It contains private settings. Never upload it to GitHub and never send it to anyone.

For the first local test, leave:

```text
LLM_PROVIDER=template
```

This means the application works without an OpenRouter account or local Hermes model.

## Part D — Start Redis and the API with Docker

1. Make sure Docker Desktop is open.
2. In the VS Code terminal, run:

```powershell
docker compose up --build
```

The first build downloads the full ML dependency set and may take 20â€“25 minutes on a slower connection. Later cached builds are much faster.

Wait until you see a message saying Uvicorn is running. Do not close this terminal while using the backend.

Open your browser and visit:

```text
http://localhost:8040/health
```

You should see a response containing `"status":"healthy"`.

Then visit:

```text
http://localhost:8040/docs
```

This is the interactive FastAPI testing page.

## Part E — Test a real dataset

1. On the API documentation page, find `POST /api/v1/analysis/profile`.
2. Click it.
3. Click **Try it out**.
4. Click **Choose File**.
5. Select `sample_data/readmission_demo.csv` from the project.
6. Click **Execute**.
7. Look for response code `200`.

Now test task detection:

1. Open `POST /api/v1/analysis/detect-task`.
2. Click **Try it out**.
3. Upload the same file.
4. Enter `readmitted` as `target_column`.
5. Enter `Predict whether a patient will be readmitted` as the objective.
6. Click **Execute**.

The detected task should be `binary_classification`.

Now test the starter model tournament using `POST /api/v1/analysis/quick-tournament`. Use the same target and objective. The demo dataset is deliberately tiny, so its scores are only a software test—not trustworthy evidence.

## Part F — Start the web interface

Keep Docker running. In VS Code, click the plus button in the terminal panel to open a second terminal.

Run:

```powershell
cd apps/web
npm install
npm run dev
```

Visit:

```text
http://localhost:3040
```

You should see the ZubePredict starter page.

## Part G — Stop the application safely

1. Return to the terminal running Docker.
2. Press `Ctrl + C` once.
3. Run:

```powershell
docker compose down
```

This stops the services without deleting your project.

## Part H — Give Codex the master prompt

1. Open `docs/codex-prompts/00-MASTER-PROMPT.md`.
2. Copy the complete contents.
3. Paste it into Codex while the ZubePredict folder is open.
4. Allow Codex to inspect the repository.
5. Codex must begin with Stage 0 and Stage 1 only.
6. Do not ask it to complete every stage in one turn.
7. After it reports a stage complete, read the tests and changed-files summary.
8. If tests fail, tell Codex to repair that same stage before continuing.

## What to send back if something fails

Send:

- The section you were following.
- The exact command you ran.
- The complete error text.
- A screenshot if the error is visual.

Do not send `.env`, passwords, tokens or secret keys.
