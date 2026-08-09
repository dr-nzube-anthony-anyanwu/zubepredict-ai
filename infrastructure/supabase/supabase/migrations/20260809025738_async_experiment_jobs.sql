-- Stage 7: durable, idempotent experiment jobs. Queue messages carry identifiers only.

alter table public.experiments
  add column if not exists job_id uuid,
  add column if not exists idempotency_key text,
  add column if not exists queued_at timestamptz,
  add column if not exists heartbeat_at timestamptz,
  add column if not exists cancel_requested_at timestamptz,
  add column if not exists attempt_count integer not null default 0,
  add column if not exists state_version integer not null default 1,
  add column if not exists result_summary jsonb not null default '{}'::jsonb;

alter table public.experiments
  add constraint experiments_attempt_count_nonnegative check (attempt_count >= 0),
  add constraint experiments_state_version_positive check (state_version >= 1),
  add constraint experiments_idempotency_key_length
    check (idempotency_key is null or char_length(idempotency_key) = 64),
  add constraint experiments_result_summary_object
    check (jsonb_typeof(result_summary) = 'object');

create unique index if not exists experiments_owner_idempotency_unique
  on public.experiments (owner_id, idempotency_key)
  where idempotency_key is not null;

create unique index if not exists experiments_job_id_unique
  on public.experiments (job_id)
  where job_id is not null;

create index if not exists experiments_stale_jobs_idx
  on public.experiments (heartbeat_at)
  where status in ('profiling', 'training', 'evaluating', 'reporting');

alter table public.model_runs
  add column if not exists job_id uuid;

alter table public.model_runs
  add constraint model_runs_experiment_job_model_unique
    unique (experiment_id, job_id, model_name);

-- Authenticated clients retain read-only visibility through ownership RLS. Job
-- creation and every state transition are service-role operations in the API/worker.
revoke insert (job_id, idempotency_key, queued_at, heartbeat_at,
  cancel_requested_at, attempt_count, state_version, result_summary)
  on public.experiments from authenticated;
revoke update (job_id, idempotency_key, queued_at, heartbeat_at,
  cancel_requested_at, attempt_count, state_version, result_summary)
  on public.experiments from authenticated;
revoke insert (job_id) on public.model_runs from authenticated;
revoke update (job_id) on public.model_runs from authenticated;

grant select on public.experiments, public.model_runs to authenticated;
grant all on public.experiments, public.model_runs to service_role;
