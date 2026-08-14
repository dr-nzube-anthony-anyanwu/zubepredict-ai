-- Stage 16: immutable, versioned report metadata for one backend-generated
-- artifact set shared by web, Telegram and authenticated API callers.

alter table public.reports
  add column if not exists report_version integer not null default 1
    check (report_version >= 1),
  add column if not exists filename text,
  add column if not exists content_type text,
  add column if not exists size_bytes bigint
    check (size_bytes is null or size_bytes >= 0),
  add column if not exists sha256 text
    check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
  add column if not exists evidence_hash text
    check (evidence_hash is null or evidence_hash ~ '^[0-9a-f]{64}$'),
  add column if not exists integrity_metadata jsonb not null default '{}'::jsonb;

create unique index if not exists reports_owner_experiment_type_version_uidx
  on public.reports (owner_id, experiment_id, report_type, report_version);

create index if not exists reports_experiment_created_idx
  on public.reports (experiment_id, created_at desc);

comment on column public.reports.sha256 is
  'SHA-256 of the exact private Storage object bytes.';

comment on column public.reports.evidence_hash is
  'Hash of the immutable Evidence Envelope used to generate this artifact.';
