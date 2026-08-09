-- Stage 12: private, owner-scoped LangGraph checkpoints. Only trusted server
-- processes use these tables; authenticated clients inspect bounded workflow
-- status through the existing experiments API instead of reading graph internals.

create unique index if not exists experiments_id_owner_unique
  on public.experiments (id, owner_id);

create table if not exists public.workflow_checkpoints (
  owner_id uuid not null references auth.users(id) on delete cascade,
  thread_id uuid not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  parent_checkpoint_id text,
  checkpoint_type text not null,
  checkpoint_blob text not null,
  metadata_type text not null,
  metadata_blob text not null,
  created_at timestamptz not null default now(),
  primary key (owner_id, thread_id, checkpoint_ns, checkpoint_id),
  foreign key (thread_id, owner_id)
    references public.experiments(id, owner_id) on delete cascade,
  constraint workflow_checkpoint_namespace_length check (char_length(checkpoint_ns) <= 500),
  constraint workflow_checkpoint_id_length check (char_length(checkpoint_id) between 1 and 200)
);

create table if not exists public.workflow_checkpoint_writes (
  owner_id uuid not null references auth.users(id) on delete cascade,
  thread_id uuid not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  task_id text not null,
  write_index integer not null,
  channel text not null,
  value_type text not null,
  value_blob text not null,
  task_path text not null default '',
  created_at timestamptz not null default now(),
  primary key (
    owner_id, thread_id, checkpoint_ns, checkpoint_id, task_id, write_index
  ),
  foreign key (thread_id, owner_id)
    references public.experiments(id, owner_id) on delete cascade,
  constraint workflow_checkpoint_write_namespace_length
    check (char_length(checkpoint_ns) <= 500)
);

create index if not exists workflow_checkpoints_thread_created_idx
  on public.workflow_checkpoints (owner_id, thread_id, checkpoint_ns, created_at desc);

create index if not exists workflow_checkpoint_writes_checkpoint_idx
  on public.workflow_checkpoint_writes (owner_id, thread_id, checkpoint_ns, checkpoint_id);

alter table public.workflow_checkpoints enable row level security;
alter table public.workflow_checkpoint_writes enable row level security;

-- Deliberately no anon/authenticated grants or policies: graph checkpoints can
-- contain internal routing state and are server-only. The service role is kept
-- explicit for projects using Supabase's new non-auto-exposure defaults.
revoke all on public.workflow_checkpoints from anon, authenticated;
revoke all on public.workflow_checkpoint_writes from anon, authenticated;
grant all on public.workflow_checkpoints to service_role;
grant all on public.workflow_checkpoint_writes to service_role;
