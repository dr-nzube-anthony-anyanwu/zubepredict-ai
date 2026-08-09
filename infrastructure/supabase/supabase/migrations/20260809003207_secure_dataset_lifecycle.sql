-- Stage 3: secure dataset lifecycle metadata and trusted mutations.

alter table public.datasets
  add column media_type text,
  add column file_format text,
  add column retention_status text not null default 'active',
  add column retention_expires_at timestamptz,
  add column validated_at timestamptz,
  add column updated_at timestamptz not null default now();

update public.datasets
set file_format = case
  when lower(original_filename) like '%.parquet' then 'parquet'
  when lower(original_filename) like '%.xlsx' then 'xlsx'
  when lower(original_filename) like '%.xls' then 'xls'
  else 'csv'
end,
media_type = case
  when lower(original_filename) like '%.parquet' then 'application/vnd.apache.parquet'
  when lower(original_filename) like '%.xlsx'
    then 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  when lower(original_filename) like '%.xls' then 'application/vnd.ms-excel'
  else 'text/csv'
end,
validated_at = created_at,
retention_expires_at = created_at + interval '30 days'
where file_format is null or media_type is null or validated_at is null;

alter table public.datasets
  alter column media_type set not null,
  alter column file_format set not null,
  alter column validated_at set not null,
  add constraint datasets_file_format_check
    check (file_format in ('csv', 'xls', 'xlsx', 'parquet')),
  add constraint datasets_retention_status_check
    check (retention_status in ('active', 'deletion_pending', 'expired', 'legal_hold')),
  add constraint datasets_retention_expires_check
    check (retention_expires_at is null or retention_expires_at >= created_at);

create index datasets_owner_retention_expiry_idx
  on public.datasets(owner_id, retention_status, retention_expires_at);

-- Dataset metadata mutations are trusted backend operations. Authenticated users
-- retain owned SELECT access while Storage uploads continue through signed URLs/RLS.
drop policy if exists "datasets_own_all" on public.datasets;
create policy "datasets_own_select"
  on public.datasets for select to authenticated
  using ((select auth.uid()) = owner_id);

revoke insert, update, delete on table public.datasets from authenticated;
grant select on table public.datasets to authenticated;

update storage.buckets
set allowed_mime_types = array[
  'text/csv',
  'text/plain',
  'application/csv',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.apache.parquet',
  'application/x-parquet',
  'application/zip',
  'application/octet-stream'
]
where id = 'datasets';
