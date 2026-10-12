-- job-search-agent, online beta: schema, row-level security and the invite gate.
--
-- Run once in the Supabase SQL editor of a project hosted in the EU
-- (Frankfurt). Every table holding a person's data is readable and writable
-- only by that person; shared data (postings, country facts) is read-only for
-- signed-in users; everything else is written by the worker with the service
-- role key, which bypasses RLS and never reaches a browser.

-- ------------------------------------------------------------------ invites
-- Private beta: an account can be created only for an email on this list.
create table if not exists public.beta_allowlist (
  email     text primary key,
  note      text,
  added_at  timestamptz not null default now()
);
alter table public.beta_allowlist enable row level security;
-- No policies: neither visitors nor users can read or change the list.

-- Before-user-created auth hook (Authentication → Hooks → "Before User
-- Created" → Postgres function public.hook_before_user_created). It runs for
-- every sign-up method: email link, Google and Apple alike.
create or replace function public.hook_before_user_created(event jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  candidate text := lower(coalesce(event -> 'user' ->> 'email', ''));
begin
  if candidate = '' or not exists (
    select 1 from public.beta_allowlist a where lower(a.email) = candidate
  ) then
    return jsonb_build_object('error', jsonb_build_object(
      'http_code', 403,
      'message', 'La beta è su invito e questa email non è nella lista. / The beta is invite-only.'
    ));
  end if;
  return '{}'::jsonb;
end;
$$;
revoke all on function public.hook_before_user_created(jsonb) from public, anon, authenticated;
grant execute on function public.hook_before_user_created(jsonb) to supabase_auth_admin;
grant usage on schema public to supabase_auth_admin;
grant select on public.beta_allowlist to supabase_auth_admin;

-- ----------------------------------------------------------------- profiles
create table if not exists public.profiles (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  profile     jsonb   not null default '{}'::jsonb,  -- the engine's profile format
  tracks      text[]  not null default '{}',         -- ids from the track library
  countries   text[]  not null default '{}',         -- ISO codes the person accepts
  lang        text    not null default 'it' check (lang in ('it', 'en')),
  onboarded   boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
alter table public.profiles enable row level security;
create policy "profiles: own row" on public.profiles
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- --------------------------------------------------------------------- jobs
-- Shared: every posting is public on its employer's board already.
create table if not exists public.jobs (
  id          text primary key,
  source      text not null,
  company     text not null,
  title       text not null,
  location    text not null default '',
  country     text not null default '',
  remote      text not null default 'unknown',
  url         text not null default '',
  posted_at   text not null default '',
  italian     boolean not null default false,
  description text not null default '',            -- shortened for display
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  closed_at   timestamptz
);
create index if not exists jobs_open_country on public.jobs (country) where closed_at is null;
alter table public.jobs enable row level security;
create policy "jobs: readable when signed in" on public.jobs
  for select to authenticated using (true);

-- ------------------------------------------------------------------- scores
create table if not exists public.scores (
  user_id    uuid not null references auth.users (id) on delete cascade,
  job_id     text not null references public.jobs (id) on delete cascade,
  track      text not null,
  score      integer not null,
  verdict    text not null check (verdict in ('pass', 'review', 'reject')),
  breakdown  jsonb not null default '{}'::jsonb,
  scored_at  timestamptz not null default now(),
  primary key (user_id, job_id)
);
create index if not exists scores_user_rank on public.scores (user_id, score desc);
alter table public.scores enable row level security;
create policy "scores: own rows" on public.scores
  for select to authenticated using (user_id = auth.uid());

-- ------------------------------------------------------------- applications
create table if not exists public.applications (
  user_id     uuid not null references auth.users (id) on delete cascade,
  job_id      text not null references public.jobs (id) on delete cascade,
  status      text not null check (status in ('shortlisted', 'drafted', 'ready', 'submitted',
                'screening', 'interview', 'offer', 'rejected', 'withdrawn', 'ghosted')),
  notes       text not null default '',
  updated_at  timestamptz not null default now(),
  primary key (user_id, job_id)
);
alter table public.applications enable row level security;
create policy "applications: own rows" on public.applications
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---------------------------------------------------------------- countries
create table if not exists public.countries (
  code       text primary key,
  facts      jsonb not null,
  guide_url  text not null default ''
);
alter table public.countries enable row level security;
create policy "countries: public" on public.countries
  for select to anon, authenticated using (true);

-- ------------------------------------------------------------- CV uploads
-- The browser uploads the file to a private bucket and queues it here; the
-- worker reads it, fills the profile and deletes the file. The file itself is
-- never kept.
create table if not exists public.cv_imports (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  path        text not null,
  status      text not null default 'pending' check (status in ('pending', 'done', 'failed')),
  error       text,
  created_at  timestamptz not null default now(),
  done_at     timestamptz
);
alter table public.cv_imports enable row level security;
create policy "cv_imports: queue own" on public.cv_imports
  for insert to authenticated
  with check (user_id = auth.uid() and path like auth.uid()::text || '/%');
create policy "cv_imports: read own" on public.cv_imports
  for select to authenticated using (user_id = auth.uid());

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('cv-uploads', 'cv-uploads', false, 5242880,
        array['application/pdf',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'text/plain'])
on conflict (id) do nothing;
create policy "cv-uploads: own folder, upload only" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'cv-uploads' and (storage.foldername(name))[1] = auth.uid()::text);

-- ---------------------------------------------------------- scoring queue
-- "Score me now", after onboarding or a change of countries or roles.
create table if not exists public.score_requests (
  user_id       uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  requested_at  timestamptz not null default now()
);
alter table public.score_requests enable row level security;
create policy "score_requests: own" on public.score_requests
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- -------------------------------------------------------- leaving the beta
-- Deleting the account removes every row above through the cascades.
create or replace function public.delete_my_account()
returns void
language sql
security definer
set search_path = public
as $$
  delete from auth.users where id = auth.uid();
$$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;
