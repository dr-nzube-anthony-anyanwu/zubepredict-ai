# ZubePredict AI Build Roadmap

Each stage has an exit gate. Codex must not continue if that gate fails.

| Stage | Outcome | Exit gate |
|---:|---|---|
| 0 | Verify Windows, Python, Node, Docker and Git | Diagnostic script passes |
| 1 | Stabilise starter and local Docker workflow | API, frontend and tests pass |
| 2 | Supabase repositories, auth and private storage | RLS ownership tests pass |
| 3 | Secure dataset upload and profiling | Invalid/oversized files rejected |
| 4 | Intent, target and task decision engine | Golden task-detection tests pass |
| 5 | Leakage and data-quality guardian | Synthetic leakage cases blocked |
| 6 | Classification and regression tournament | Baselines and CV comparisons pass |
| 7 | Redis/Dramatiq asynchronous jobs | Job survives API restart |
| 8 | Clustering and anomaly detection | Synthetic cluster/anomaly tests pass |
| 9 | Time-series forecasting | Time-aware split and naive baseline pass |
| 10 | Optuna tuning and resource budgets | Trials obey time and count limits |
| 11 | Explainability and error analysis | Outputs match supported model types |
| 12 | LangGraph orchestration | Pause/resume/clarify routes pass |
| 13 | Nous Hermes provider and grounded summaries | Complete: LLM cannot alter verified metrics |
| 14 | Hermes Telegram workflow | Implemented; mocked ownership/cancellation pass, real owner smoke pending |
| 15 | Full Next.js dashboard | End-to-end experiment works |
| 16 | HTML/PDF/model-card reporting | Artifacts reproduce stored results |
| 17 | Security, quotas and retention | Abuse and cross-user tests pass |
| 18 | Vercel/Render demonstration deployment | Health and smoke tests pass |

## Rules that apply to every stage

1. Read existing code before editing.
2. Preserve working functionality.
3. Never commit secrets.
4. Add tests for every decision rule.
5. Fit preprocessing only on training folds.
6. Compare every advanced model with a baseline.
7. Never claim “best” without stating the metric and validation method.
8. Never let the LLM invent metrics or silently change task configuration.
9. Do not use protected or sensitive attributes without an explicit fairness review.
10. Stop and request clarification when the target or objective is ambiguous.
11. Keep datasets private and scoped to their owner.
12. Record seeds, software versions, parameters and dataset fingerprints.
