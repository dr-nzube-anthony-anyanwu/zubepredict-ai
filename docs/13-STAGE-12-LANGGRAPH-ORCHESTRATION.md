# Stage 12: LangGraph Orchestration

Stage 12 wraps the existing deterministic experiment pipeline in a typed
LangGraph state machine. Profiling, task detection, plan validation, training,
evaluation, artifact persistence, and completion remain Python-owned. No model
is allowed to calculate or alter metrics.

## Workflow

The graph follows these explicit routes:

```text
profile -> decide -> [clarify] -> plan -> [clarify] -> train -> finalize
```

- `profile`, `decide`, and `plan` have a bounded two-attempt transient retry
  policy.
- Cancellation is checked before and around expensive work.
- Clarification uses a LangGraph interrupt and preserves the experiment ID as
  the durable thread ID.
- `train` persists artifacts and model-run rows before its checkpoint. Repeating
  a job replaces model-run rows for the same job ID, and a completed checkpoint
  is returned without invoking training again.

## Durable checkpoint storage

Apply the Stage 12 migration before running a Stage 12 worker:

```powershell
npx supabase db push
```

`workflow_checkpoints` and `workflow_checkpoint_writes` are private server-only
tables. RLS is enabled, `anon` and `authenticated` have no grants, and only the
trusted service-role worker can access the serialized graph state. Every query
is additionally scoped by `owner_id`.

## Resuming clarification

Use the authenticated endpoint with the same experiment and job:

```http
POST /experiments/{experiment_id}/resume
Authorization: Bearer <supabase-user-access-token>
Content-Type: application/json

{
  "configuration": {
    "time_column": "date",
    "frequency": "D",
    "forecast_horizon": 7
  }
}
```

For a task decision, also provide `task_type`, `target_column`, and
`"confirmed_by_user": true`. Only an experiment in `needs_clarification` can be
resumed. Completed, cancelled, failed, and already-queued experiments are
rejected, preventing a completed training job from being duplicated.

## Verification

```powershell
.\.venv\Scripts\pytest.exe -q tests\unit\test_stage12_workflow.py
.\scripts\validate-supabase-migration.ps1
```
