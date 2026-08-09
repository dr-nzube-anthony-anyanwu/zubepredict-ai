-- Stage 4: deterministic decision evidence and trusted user-confirmed overrides.

alter table public.experiments
  add column decision_evidence jsonb not null default '{}'::jsonb,
  add column decision_source text not null default 'deterministic',
  add column decision_version integer not null default 1,
  add column decision_updated_at timestamptz,
  add column task_override_confirmed_at timestamptz,
  add constraint experiments_decision_evidence_object_check
    check (jsonb_typeof(decision_evidence) = 'object'),
  add constraint experiments_decision_source_check
    check (decision_source in ('deterministic', 'user_override')),
  add constraint experiments_decision_version_check
    check (decision_version > 0),
  add constraint experiments_detected_task_check
    check (
      detected_task is null or detected_task in (
        'binary_classification',
        'multiclass_classification',
        'regression',
        'clustering',
        'anomaly_detection',
        'time_series_forecasting',
        'needs_clarification'
      )
    );

-- Authenticated users can create and read their own experiment drafts. All
-- decision mutations and deletions go through the trusted backend and audit log.
drop policy if exists "experiments_own_all" on public.experiments;
create policy "experiments_own_select"
  on public.experiments for select to authenticated
  using ((select auth.uid()) = owner_id);
create policy "experiments_own_insert"
  on public.experiments for insert to authenticated
  with check ((select auth.uid()) = owner_id);

revoke insert, update, delete on table public.experiments from authenticated;
grant insert (
  project_id,
  dataset_id,
  owner_id,
  objective,
  target_column,
  configuration
) on table public.experiments to authenticated;
grant select on table public.experiments to authenticated;
