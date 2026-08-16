-- Stage 17: privacy attestations, artifact retention metadata and immutable
-- customer audit history. Runtime rate/concurrency counters live in Redis;
-- authoritative ownership and retained-byte accounting remain in Postgres.

alter table public.datasets
  add column if not exists privacy_attested_at timestamptz,
  add column if not exists deidentified_confirmed boolean not null default false,
  add column if not exists consent_scope text;

alter table public.datasets
  drop constraint if exists datasets_consent_scope_length_check,
  add constraint datasets_consent_scope_length_check
    check (consent_scope is null or char_length(consent_scope) between 1 and 120);

alter table public.reports
  add column if not exists retention_status text not null default 'active',
  add column if not exists retention_expires_at timestamptz,
  add column if not exists deleted_at timestamptz;

update public.reports
set retention_expires_at = created_at + interval '30 days'
where retention_expires_at is null;

alter table public.reports
  alter column retention_expires_at set default (now() + interval '30 days'),
  drop constraint if exists reports_retention_status_check,
  add constraint reports_retention_status_check
    check (retention_status in ('active', 'deletion_pending', 'expired', 'legal_hold')),
  drop constraint if exists reports_retention_expiry_check,
  add constraint reports_retention_expiry_check
    check (retention_expires_at is null or retention_expires_at >= created_at);

create index if not exists datasets_retention_sweep_idx
  on public.datasets(retention_expires_at, owner_id)
  where retention_status = 'active';
create index if not exists reports_retention_sweep_idx
  on public.reports(retention_expires_at, owner_id)
  where retention_status = 'active';
create index if not exists experiments_owner_active_quota_idx
  on public.experiments(owner_id, status, created_at desc)
  where status in ('queued', 'profiling', 'training', 'evaluating', 'reporting');

create table if not exists public.user_security_limits (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  storage_quota_bytes bigint not null default 524288000 check (storage_quota_bytes > 0),
  concurrent_experiment_limit integer not null default 2
    check (concurrent_experiment_limit between 1 and 100),
  updated_at timestamptz not null default now()
);

alter table public.user_security_limits enable row level security;
revoke all on table public.user_security_limits from anon, authenticated;
grant all on table public.user_security_limits to service_role;

create or replace function private.enforce_owner_resource_limits()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  configured_limit bigint;
  current_usage bigint;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(new.owner_id::text, 17017)
  );
  if tg_table_name = 'datasets' then
    select coalesce(l.storage_quota_bytes, 524288000)
      into configured_limit
      from (select 1) seed
      left join public.user_security_limits l on l.owner_id = new.owner_id;
    select coalesce(sum(d.size_bytes), 0)
      into current_usage
      from public.datasets d
      where d.owner_id = new.owner_id
        and d.retention_status = 'active'
        and d.id <> new.id;
    if current_usage + new.size_bytes > configured_limit then
      raise exception 'owner storage quota exceeded' using errcode = 'P0001';
    end if;
  elsif new.status in ('queued', 'profiling', 'training', 'evaluating', 'reporting')
    and (tg_op = 'INSERT' or old.status is distinct from new.status) then
    select coalesce(l.concurrent_experiment_limit, 2)
      into configured_limit
      from (select 1) seed
      left join public.user_security_limits l on l.owner_id = new.owner_id;
    select count(*) into current_usage
      from public.experiments e
      where e.owner_id = new.owner_id
        and e.status in ('queued', 'profiling', 'training', 'evaluating', 'reporting')
        and e.id <> new.id;
    if current_usage >= configured_limit then
      raise exception 'owner concurrent experiment quota exceeded' using errcode = 'P0001';
    end if;
  end if;
  return new;
end;
$$;

revoke execute on function private.enforce_owner_resource_limits()
  from public, anon, authenticated;
grant execute on function private.enforce_owner_resource_limits() to service_role;

drop trigger if exists enforce_dataset_storage_quota on public.datasets;
create trigger enforce_dataset_storage_quota
before insert or update of size_bytes, retention_status on public.datasets
for each row execute function private.enforce_owner_resource_limits();

drop trigger if exists enforce_experiment_concurrency_quota on public.experiments;
create trigger enforce_experiment_concurrency_quota
before insert or update of status on public.experiments
for each row execute function private.enforce_owner_resource_limits();

-- Customers can read their own audit history but cannot forge, edit or delete it.
alter table public.audit_logs enable row level security;
revoke insert, update, delete on table public.audit_logs from anon, authenticated;
grant select on table public.audit_logs to authenticated;
grant all on table public.audit_logs to service_role;

comment on column public.datasets.privacy_attested_at is
  'When the owner explicitly acknowledged the upload privacy boundary.';
comment on column public.datasets.deidentified_confirmed is
  'Owner attestation only; never interpreted as independent de-identification proof.';
comment on column public.reports.retention_expires_at is
  'Earliest normal deletion eligibility. Legal hold prevents automated deletion.';
comment on table public.user_security_limits is
  'Server-only authoritative resource caps. Keep values aligned with runtime quota settings.';
