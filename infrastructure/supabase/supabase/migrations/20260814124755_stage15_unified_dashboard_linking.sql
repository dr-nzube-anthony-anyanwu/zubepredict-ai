-- Stage 15: unified channel provenance and server-only Telegram linking attempts.
-- Source channel is descriptive metadata only; owner_id and RLS remain authoritative.

alter table public.projects
  add column if not exists source_channel text not null default 'api';
alter table public.datasets
  add column if not exists source_channel text not null default 'api';
alter table public.experiments
  add column if not exists source_channel text not null default 'api';

alter table public.projects
  add constraint projects_source_channel_check
  check (source_channel in ('web', 'telegram', 'api', 'administrative'));
alter table public.datasets
  add constraint datasets_source_channel_check
  check (source_channel in ('web', 'telegram', 'api', 'administrative'));
alter table public.experiments
  add constraint experiments_source_channel_check
  check (source_channel in ('web', 'telegram', 'api', 'administrative'));

create index if not exists experiments_owner_source_created_idx
  on public.experiments(owner_id, source_channel, created_at desc);

create table if not exists public.telegram_linking_attempts (
  id bigint generated always as identity primary key,
  principal_hash text not null check (principal_hash ~ '^[0-9a-f]{64}$'),
  succeeded boolean not null default false,
  reason text not null check (
    reason in ('invalid', 'invalid_or_expired', 'identity_conflict', 'owner_conflict', 'linked')
  ),
  attempted_at timestamptz not null default now()
);

create index if not exists telegram_linking_attempts_principal_time_idx
  on public.telegram_linking_attempts(principal_hash, attempted_at desc)
  where not succeeded;

alter table public.telegram_linking_attempts enable row level security;
revoke all on public.telegram_linking_attempts from anon, authenticated;
grant all on public.telegram_linking_attempts to service_role;
grant usage, select on sequence public.telegram_linking_attempts_id_seq to service_role;

comment on column public.experiments.source_channel is
  'Descriptive creation channel only. It never changes owner_id or authorization.';
comment on table public.telegram_linking_attempts is
  'Server-only rate-limit ledger. Stores an HMAC principal hash and never stores linking codes.';
