-- Stage 14: server-owned Telegram links, resumable channel state, and one-time
-- account-linking codes. These tables are intentionally inaccessible to anon
-- and authenticated Data API clients; trusted backend services mediate access.

create table if not exists public.telegram_account_links (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  platform text not null default 'telegram' check (platform = 'telegram'),
  external_user_id text not null check (external_user_id ~ '^[0-9]{1,20}$'),
  status text not null default 'active' check (status in ('active', 'revoked')),
  link_source text not null check (link_source in ('development_config', 'one_time_code')),
  linked_at timestamptz not null default now(),
  revoked_at timestamptz,
  updated_at timestamptz not null default now(),
  unique (platform, external_user_id),
  unique (owner_id, platform)
);

create table if not exists public.telegram_channel_states (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  account_link_id uuid not null unique references public.telegram_account_links(id) on delete cascade,
  selected_project_id uuid references public.projects(id) on delete set null,
  selected_dataset_id uuid references public.datasets(id) on delete set null,
  active_experiment_id uuid references public.experiments(id) on delete set null,
  pending_clarification_id text,
  pending_clarification_version integer check (pending_clarification_version is null or pending_clarification_version > 0),
  constitution_id uuid references public.experiments(id) on delete set null,
  constitution_version integer check (constitution_version is null or constitution_version > 0),
  approval_status text not null default 'none' check (approval_status in ('none', 'proposed', 'approved')),
  last_safe_interaction_state text not null default 'start' check (
    last_safe_interaction_state in (
      'start', 'project_selected', 'dataset_uploaded', 'objective_received',
      'profiled', 'readiness_reviewed', 'clarification_required',
      'constitution_proposed', 'constitution_approved', 'queued', 'running',
      'completed', 'failed', 'cancelled', 'reset'
    )
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.telegram_linking_codes (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  code_hash text not null unique check (code_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  used_at timestamptz,
  revoked_at timestamptz,
  failed_attempts integer not null default 0 check (failed_attempts between 0 and 10),
  created_at timestamptz not null default now(),
  check (expires_at > created_at)
);

create index if not exists telegram_account_links_owner_idx
  on public.telegram_account_links(owner_id, status);
create index if not exists telegram_channel_states_owner_idx
  on public.telegram_channel_states(owner_id);
create index if not exists telegram_linking_codes_owner_expiry_idx
  on public.telegram_linking_codes(owner_id, expires_at desc);

alter table public.telegram_account_links enable row level security;
alter table public.telegram_channel_states enable row level security;
alter table public.telegram_linking_codes enable row level security;

revoke all on public.telegram_account_links from anon, authenticated;
revoke all on public.telegram_channel_states from anon, authenticated;
revoke all on public.telegram_linking_codes from anon, authenticated;

grant all on public.telegram_account_links to service_role;
grant all on public.telegram_channel_states to service_role;
grant all on public.telegram_linking_codes to service_role;

comment on table public.telegram_account_links is
  'Server-mediated Telegram-to-ZubePredict links. Never writable from Telegram or the browser directly.';
comment on table public.telegram_channel_states is
  'Authoritative resumable Telegram workflow state; Hermes conversation memory is not authoritative.';
comment on table public.telegram_linking_codes is
  'Hashed, short-lived, one-time account linking codes. Plaintext codes are never stored.';
