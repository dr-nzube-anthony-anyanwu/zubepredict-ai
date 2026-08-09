-- Minimal Supabase-owned objects used only to syntax-check the project migration.
-- This is not a Supabase emulator and must never be used as an application database.

create extension if not exists pgcrypto;

create role anon nologin;
create role authenticated nologin;
create role service_role nologin;

create schema auth;
create table auth.users (
  id uuid primary key,
  raw_user_meta_data jsonb not null default '{}'::jsonb
);

create function auth.uid()
returns uuid
language sql
stable
as $$ select null::uuid $$;

create schema storage;
create table storage.buckets (
  id text primary key,
  name text not null,
  public boolean not null default false,
  file_size_limit bigint,
  allowed_mime_types text[]
);
create table storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text not null references storage.buckets(id),
  name text not null,
  owner_id text
);
alter table storage.objects enable row level security;

create function storage.foldername(name text)
returns text[]
language sql
immutable
as $$ select string_to_array(name, '/') $$;
