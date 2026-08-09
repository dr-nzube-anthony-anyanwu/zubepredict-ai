-- ZubePredict AI initial Supabase schema.
-- Apply through the Supabase SQL editor before creating application data.

create extension if not exists pgcrypto;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create type public.experiment_status as enum (
  'draft', 'needs_clarification', 'queued', 'profiling', 'training',
  'evaluating', 'reporting', 'completed', 'failed', 'cancelled'
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  telegram_user_id bigint unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id)
);

create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  original_filename text not null check (char_length(original_filename) between 1 and 255),
  storage_path text not null unique,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint not null check (size_bytes > 0),
  row_count integer check (row_count is null or row_count >= 0),
  column_count integer check (column_count is null or column_count >= 0),
  profile jsonb check (profile is null or jsonb_typeof(profile) = 'object'),
  created_at timestamptz not null default now(),
  unique (id, project_id, owner_id),
  constraint datasets_project_owner_fkey
    foreign key (project_id, owner_id)
    references public.projects(id, owner_id)
    on delete cascade
);

create table public.experiments (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  dataset_id uuid not null,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  objective text,
  target_column text,
  detected_task text,
  task_confidence numeric(5,4) check (
    task_confidence is null or task_confidence between 0 and 1
  ),
  primary_metric text,
  winner_model text,
  status public.experiment_status not null default 'draft',
  progress smallint not null default 0 check (progress between 0 and 100),
  warnings jsonb not null default '[]'::jsonb check (jsonb_typeof(warnings) = 'array'),
  error_message text,
  configuration jsonb not null default '{}'::jsonb check (
    jsonb_typeof(configuration) = 'object'
  ),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique (id, owner_id),
  constraint experiments_project_owner_fkey
    foreign key (project_id, owner_id)
    references public.projects(id, owner_id)
    on delete cascade,
  constraint experiments_dataset_project_owner_fkey
    foreign key (dataset_id, project_id, owner_id)
    references public.datasets(id, project_id, owner_id)
    on delete cascade
);

create table public.model_runs (
  id uuid primary key default gen_random_uuid(),
  experiment_id uuid not null,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  model_name text not null,
  hyperparameters jsonb not null default '{}'::jsonb check (
    jsonb_typeof(hyperparameters) = 'object'
  ),
  metrics jsonb not null default '{}'::jsonb check (jsonb_typeof(metrics) = 'object'),
  fold_scores jsonb not null default '[]'::jsonb check (
    jsonb_typeof(fold_scores) = 'array'
  ),
  fit_seconds numeric check (fit_seconds is null or fit_seconds >= 0),
  predict_seconds numeric check (predict_seconds is null or predict_seconds >= 0),
  status text not null default 'pending' check (
    status in ('pending', 'running', 'completed', 'failed', 'cancelled')
  ),
  error_message text,
  artifact_path text,
  created_at timestamptz not null default now(),
  constraint model_runs_experiment_owner_fkey
    foreign key (experiment_id, owner_id)
    references public.experiments(id, owner_id)
    on delete cascade
);

create table public.reports (
  id uuid primary key default gen_random_uuid(),
  experiment_id uuid not null,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  report_type text not null,
  storage_path text not null unique,
  created_at timestamptz not null default now(),
  constraint reports_experiment_owner_fkey
    foreign key (experiment_id, owner_id)
    references public.experiments(id, owner_id)
    on delete cascade
);

create table public.audit_logs (
  id bigint generated always as identity primary key,
  owner_id uuid references public.profiles(id) on delete set null,
  action text not null,
  resource_type text not null,
  resource_id uuid,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);

-- Index ownership predicates, foreign keys, and common list filters.
create index projects_owner_created_idx on public.projects(owner_id, created_at desc);
create index datasets_project_owner_idx on public.datasets(project_id, owner_id);
create index datasets_owner_created_idx on public.datasets(owner_id, created_at desc);
create index experiments_owner_status_created_idx
  on public.experiments(owner_id, status, created_at desc);
create index experiments_project_owner_idx on public.experiments(project_id, owner_id);
create index experiments_dataset_project_owner_idx
  on public.experiments(dataset_id, project_id, owner_id);
create index model_runs_experiment_owner_idx
  on public.model_runs(experiment_id, owner_id);
create index model_runs_owner_created_idx on public.model_runs(owner_id, created_at desc);
create index reports_experiment_owner_idx on public.reports(experiment_id, owner_id);
create index reports_owner_created_idx on public.reports(owner_id, created_at desc);
create index audit_logs_owner_created_idx on public.audit_logs(owner_id, created_at desc);

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.datasets enable row level security;
alter table public.experiments enable row level security;
alter table public.model_runs enable row level security;
alter table public.reports enable row level security;
alter table public.audit_logs enable row level security;

create policy "profiles_select_own"
  on public.profiles for select to authenticated
  using ((select auth.uid()) = id);
create policy "profiles_update_own"
  on public.profiles for update to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

create policy "projects_own_all"
  on public.projects for all to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);
create policy "datasets_own_all"
  on public.datasets for all to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);
create policy "experiments_own_all"
  on public.experiments for all to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

-- Model results, reports, and audit rows are written by trusted server workers.
create policy "model_runs_own_select"
  on public.model_runs for select to authenticated
  using ((select auth.uid()) = owner_id);
create policy "reports_own_select"
  on public.reports for select to authenticated
  using ((select auth.uid()) = owner_id);
create policy "audit_logs_own_select"
  on public.audit_logs for select to authenticated
  using ((select auth.uid()) = owner_id);

-- Explicit grants are required for projects where public tables are not exposed by default.
revoke all on table public.profiles, public.projects, public.datasets,
  public.experiments, public.model_runs, public.reports, public.audit_logs from anon;
grant usage on schema public to authenticated, service_role;
grant select on table public.profiles to authenticated;
grant update (full_name, telegram_user_id) on table public.profiles to authenticated;
grant select, insert, update, delete on table public.projects, public.datasets,
  public.experiments to authenticated;
grant select on table public.model_runs, public.reports, public.audit_logs to authenticated;
grant all on table public.profiles, public.projects, public.datasets,
  public.experiments, public.model_runs, public.reports, public.audit_logs to service_role;
grant usage, select on sequence public.audit_logs_id_seq to service_role;

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'full_name', ''))
  on conflict (id) do nothing;
  return new;
end;
$$;

revoke execute on function private.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function private.handle_new_user();

-- Backfill profiles if Auth users existed before this migration was applied.
insert into public.profiles (id, full_name)
select id, coalesce(raw_user_meta_data ->> 'full_name', '')
from auth.users
on conflict (id) do nothing;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'datasets', 'datasets', false, 10485760,
  array[
    'text/csv',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.apache.parquet',
    'application/octet-stream'
  ]
), (
  'artifacts', 'artifacts', false, 52428800, null
)
on conflict (id) do nothing;

create policy "dataset_objects_owner_read"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'datasets'
    and (storage.foldername(name))[1] = ((select auth.uid())::text)
  );
create policy "dataset_objects_owner_insert"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'datasets'
    and (storage.foldername(name))[1] = ((select auth.uid())::text)
  );
create policy "dataset_objects_owner_update"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'datasets'
    and owner_id = ((select auth.uid())::text)
    and (storage.foldername(name))[1] = ((select auth.uid())::text)
  )
  with check (
    bucket_id = 'datasets'
    and owner_id = ((select auth.uid())::text)
    and (storage.foldername(name))[1] = ((select auth.uid())::text)
  );
create policy "dataset_objects_owner_delete"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'datasets'
    and owner_id = ((select auth.uid())::text)
    and (storage.foldername(name))[1] = ((select auth.uid())::text)
  );
create policy "artifact_objects_owner_read"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'artifacts'
    and (storage.foldername(name))[1] = ((select auth.uid())::text)
  );
