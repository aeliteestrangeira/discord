-- Current application schema snapshot.
-- This is the only deployable SQL artifact. It is idempotent and replaces the historical
-- numbered migration fragments while preserving their effective order and controls.

-- ============================================================
-- Consolidated section from 000_migration_ledger.sql
-- ============================================================
-- Private application control schema. It is intentionally not exposed through
-- Supabase Data API. The dashboard/SQL editor can still inspect it directly.
create schema if not exists app_private;

revoke all on schema app_private from public;
revoke all on schema app_private from anon;
revoke all on schema app_private from authenticated;

create table if not exists app_private.schema_migrations (
    migration text primary key,
    checksum_sha256 text not null check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz not null default now()
);

revoke all on table app_private.schema_migrations from public;
revoke all on table app_private.schema_migrations from anon;
revoke all on table app_private.schema_migrations from authenticated;

-- ============================================================
-- Consolidated section from 001_core.sql
-- ============================================================
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    global_name text check (global_name is null or char_length(global_name) <= 32),
    username text check (username is null or char_length(username) <= 32),
    date_of_birth date,
    marketing_opt_in boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists profiles_username_unique
on public.profiles (lower(username))
where username is not null;

alter table public.profiles enable row level security;
alter table public.profiles force row level security;

revoke all on table public.profiles from public;
revoke all on table public.profiles from anon;
grant usage on schema public to authenticated;
grant select, insert, update on table public.profiles to authenticated;

drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self
on public.profiles
for select
to authenticated
using ((select auth.uid()) = id);

drop policy if exists profiles_insert_self on public.profiles;
create policy profiles_insert_self
on public.profiles
for insert
to authenticated
with check ((select auth.uid()) = id);

drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self
on public.profiles
for update
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

-- ============================================================
-- Consolidated section from 002_registration_constraints.sql
-- ============================================================
-- Registration invariants for username availability and profile materialization.
-- Idempotent and safe to re-run. A duplicate existing username intentionally
-- causes the migration to fail rather than silently preserve an ambiguous state.

alter table public.profiles
    drop constraint if exists profiles_username_format;

alter table public.profiles
    add constraint profiles_username_format
    check (username is null or username ~ '^[A-Za-z0-9_.]{2,32}$');

create unique index if not exists profiles_username_unique
on public.profiles (lower(username))
where username is not null;

create or replace function public.sync_profile_from_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    v_username text := nullif(btrim(new.raw_user_meta_data->>'username'), '');
    v_global_name text := nullif(btrim(new.raw_user_meta_data->>'global_name'), '');
    v_dob date := null;
    v_marketing boolean := false;
begin
    if v_username is not null and v_username !~ '^[A-Za-z0-9_.]{2,32}$' then
        raise exception 'invalid username metadata' using errcode = '23514';
    end if;

    begin
        if nullif(new.raw_user_meta_data->>'date_of_birth', '') is not null then
            v_dob := (new.raw_user_meta_data->>'date_of_birth')::date;
        end if;
    exception when others then
        v_dob := null;
    end;

    begin
        v_marketing := coalesce((new.raw_user_meta_data->>'marketing_opt_in')::boolean, false);
    exception when others then
        v_marketing := false;
    end;

    insert into public.profiles(id, global_name, username, date_of_birth, marketing_opt_in, updated_at)
    values (new.id, v_global_name, v_username, v_dob, v_marketing, now())
    on conflict (id) do update set
        global_name = excluded.global_name,
        username = excluded.username,
        date_of_birth = excluded.date_of_birth,
        marketing_opt_in = excluded.marketing_opt_in,
        updated_at = now();

    return new;
end;
$$;

revoke all on function public.sync_profile_from_auth_user() from public;

drop trigger if exists on_auth_user_created_profile on auth.users;
create trigger on_auth_user_created_profile
after insert on auth.users
for each row execute function public.sync_profile_from_auth_user();

-- Materialize existing valid username metadata so the unique index protects
-- both historical and future accounts. Existing duplicates fail closed.
-- Historical date_of_birth values are left untouched because legacy metadata
-- may not satisfy the current ISO-date contract.
insert into public.profiles(id, global_name, username, marketing_opt_in, updated_at)
select
    u.id,
    nullif(btrim(u.raw_user_meta_data->>'global_name'), ''),
    nullif(btrim(u.raw_user_meta_data->>'username'), ''),
    case
        when lower(coalesce(u.raw_user_meta_data->>'marketing_opt_in', 'false')) in ('true','false')
        then (u.raw_user_meta_data->>'marketing_opt_in')::boolean
        else false
    end,
    now()
from auth.users u
where nullif(btrim(u.raw_user_meta_data->>'username'), '') ~ '^[A-Za-z0-9_.]{2,32}$'
on conflict (id) do update set
    global_name = excluded.global_name,
    username = excluded.username,
    marketing_opt_in = excluded.marketing_opt_in,
    updated_at = now();

-- ============================================================
-- Consolidated section from 003_username_lowercase.sql
-- ============================================================
-- Canonical username invariant: application usernames are always lowercase.
-- Idempotent and safe to re-run after 001/002. Existing profile usernames are
-- normalized before the lowercase constraint is enforced.

update public.profiles
   set username = lower(username),
       updated_at = now()
 where username is not null
   and username <> lower(username);

alter table public.profiles
    drop constraint if exists profiles_username_format;

alter table public.profiles
    add constraint profiles_username_format
    check (username is null or username ~ '^[a-z0-9_.]{2,32}$');

create unique index if not exists profiles_username_unique
on public.profiles (lower(username))
where username is not null;

create or replace function public.sync_profile_from_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    v_username text := nullif(lower(btrim(new.raw_user_meta_data->>'username')), '');
    v_global_name text := nullif(btrim(new.raw_user_meta_data->>'global_name'), '');
    v_dob date := null;
    v_marketing boolean := false;
begin
    if v_username is not null and v_username !~ '^[a-z0-9_.]{2,32}$' then
        raise exception 'invalid username metadata' using errcode = '23514';
    end if;

    begin
        if nullif(new.raw_user_meta_data->>'date_of_birth', '') is not null then
            v_dob := (new.raw_user_meta_data->>'date_of_birth')::date;
        end if;
    exception when others then
        v_dob := null;
    end;

    begin
        v_marketing := coalesce((new.raw_user_meta_data->>'marketing_opt_in')::boolean, false);
    exception when others then
        v_marketing := false;
    end;

    insert into public.profiles(id, global_name, username, date_of_birth, marketing_opt_in, updated_at)
    values (new.id, v_global_name, v_username, v_dob, v_marketing, now())
    on conflict (id) do update set
        global_name = excluded.global_name,
        username = excluded.username,
        date_of_birth = excluded.date_of_birth,
        marketing_opt_in = excluded.marketing_opt_in,
        updated_at = now();

    return new;
end;
$$;

revoke all on function public.sync_profile_from_auth_user() from public;

-- ============================================================
-- Consolidated section from 004_username_no_repeating_dots.sql
-- ============================================================
-- Prevent consecutive periods in application usernames.
-- NOT VALID avoids rewriting or silently renaming historical usernames while
-- still enforcing the invariant for every new/updated profile row.

alter table public.profiles
    drop constraint if exists profiles_username_no_repeating_dots;

alter table public.profiles
    add constraint profiles_username_no_repeating_dots
    check (username is null or username !~ '\.\.') not valid;

create or replace function public.sync_profile_from_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    v_username text := nullif(lower(btrim(new.raw_user_meta_data->>'username')), '');
    v_global_name text := nullif(btrim(new.raw_user_meta_data->>'global_name'), '');
    v_dob date := null;
    v_marketing boolean := false;
begin
    if v_username is not null and (
        v_username !~ '^[a-z0-9_.]{2,32}$'
        or v_username ~ '\.\.'
    ) then
        raise exception 'invalid username metadata' using errcode = '23514';
    end if;

    begin
        if nullif(new.raw_user_meta_data->>'date_of_birth', '') is not null then
            v_dob := (new.raw_user_meta_data->>'date_of_birth')::date;
        end if;
    exception when others then
        v_dob := null;
    end;

    begin
        v_marketing := coalesce((new.raw_user_meta_data->>'marketing_opt_in')::boolean, false);
    exception when others then
        v_marketing := false;
    end;

    insert into public.profiles(id, global_name, username, date_of_birth, marketing_opt_in, updated_at)
    values (new.id, v_global_name, v_username, v_dob, v_marketing, now())
    on conflict (id) do update set
        global_name = excluded.global_name,
        username = excluded.username,
        date_of_birth = excluded.date_of_birth,
        marketing_opt_in = excluded.marketing_opt_in,
        updated_at = now();

    return new;
end;
$$;

revoke all on function public.sync_profile_from_auth_user() from public;

-- ============================================================
-- Consolidated section from 005_email_delivery_events.sql
-- ============================================================
-- Provider-neutral delivery telemetry for account e-mail operations.
-- Recipient plaintext is deliberately not stored here; application audit may
-- correlate by user id and recipient hash without duplicating PII.
create table if not exists app_private.email_delivery_events (
    id bigint generated by default as identity primary key,
    user_id uuid references auth.users(id) on delete set null,
    recipient_sha256 text not null check (recipient_sha256 ~ '^[0-9a-f]{64}$'),
    purpose text not null check (purpose in ('email_verification','password_recovery','magic_link','test')),
    provider text not null check (provider in ('supabase','gmail')),
    outcome text not null check (outcome in ('requested','sent','failed')),
    provider_code text,
    created_at timestamptz not null default now()
);

create index if not exists email_delivery_events_user_time
    on app_private.email_delivery_events (user_id, created_at desc);
create index if not exists email_delivery_events_recipient_time
    on app_private.email_delivery_events (recipient_sha256, created_at desc);

revoke all on table app_private.email_delivery_events from public;
revoke all on table app_private.email_delivery_events from anon;
revoke all on table app_private.email_delivery_events from authenticated;

-- ============================================================
-- Consolidated section from 006_friend_requests.sql
-- ============================================================
-- Real application friend-request persistence in Supabase PostgreSQL.
-- Browser clients do not receive direct table privileges; all writes currently
-- pass through the authenticated Flask policy/CSRF/hCaptcha boundary.

create table if not exists public.friend_requests (
    id uuid primary key default gen_random_uuid(),
    sender_id uuid not null references auth.users(id) on delete cascade,
    receiver_id uuid not null references auth.users(id) on delete cascade,
    status text not null default 'pending' check (status in ('pending','accepted','declined','cancelled')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint friend_requests_no_self check (sender_id <> receiver_id),
    constraint friend_requests_sender_receiver_unique unique (sender_id, receiver_id)
);

create index if not exists friend_requests_receiver_status_created
    on public.friend_requests (receiver_id, status, created_at desc);
create index if not exists friend_requests_sender_status_created
    on public.friend_requests (sender_id, status, created_at desc);

alter table public.friend_requests enable row level security;
alter table public.friend_requests force row level security;

revoke all on table public.friend_requests from public;
revoke all on table public.friend_requests from anon;
revoke all on table public.friend_requests from authenticated;

-- ============================================================
-- Consolidated section from 007_guilds.sql
-- ============================================================
-- Server/guild persistence for the authenticated application shell.
-- Browser clients receive no direct table privileges; all reads/writes pass
-- through the Flask Actor/Policy/CSRF boundary.

create table if not exists public.guilds (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    template_key text not null default 'custom',
    audience text not null default 'friends',
    icon_media_type text,
    icon_bytes bytea,
    icon_sha256 char(64),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint guilds_name_length check (char_length(btrim(name)) between 1 and 100),
    constraint guilds_template_key check (template_key in ('custom','gaming','friends','study_group','school_club','local_community','artists_creators')),
    constraint guilds_audience check (audience in ('friends','community','skipped')),
    constraint guilds_icon_consistency check (
        (icon_media_type is null and icon_bytes is null and icon_sha256 is null)
        or
        (icon_media_type in ('image/jpeg','image/png','image/gif','image/webp','image/avif') and icon_bytes is not null and icon_sha256 is not null)
    )
);

create index if not exists guilds_owner_created
    on public.guilds (owner_id, created_at asc, id asc);

create table if not exists public.guild_members (
    guild_id uuid not null references public.guilds(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    member_role text not null default 'member' check (member_role in ('owner','member')),
    joined_at timestamptz not null default now(),
    primary key (guild_id, user_id)
);

create index if not exists guild_members_user_joined
    on public.guild_members (user_id, joined_at asc, guild_id asc);

create table if not exists public.guild_channels (
    id uuid primary key default gen_random_uuid(),
    guild_id uuid not null references public.guilds(id) on delete cascade,
    name text not null,
    channel_type text not null default 'text' check (channel_type in ('text','voice')),
    position integer not null default 0 check (position >= 0),
    created_at timestamptz not null default now(),
    constraint guild_channels_name_length check (char_length(btrim(name)) between 1 and 100),
    constraint guild_channels_name_format check (name ~ '^[a-z0-9_-]+$'),
    constraint guild_channels_unique_position unique (guild_id, channel_type, position),
    constraint guild_channels_unique_name unique (guild_id, channel_type, name)
);

create index if not exists guild_channels_guild_position
    on public.guild_channels (guild_id, channel_type, position, id);

alter table public.guilds enable row level security;
alter table public.guilds force row level security;
alter table public.guild_members enable row level security;
alter table public.guild_members force row level security;
alter table public.guild_channels enable row level security;
alter table public.guild_channels force row level security;

revoke all on table public.guilds from public;
revoke all on table public.guilds from anon;
revoke all on table public.guilds from authenticated;
revoke all on table public.guild_members from public;
revoke all on table public.guild_members from anon;
revoke all on table public.guild_members from authenticated;
revoke all on table public.guild_channels from public;
revoke all on table public.guild_channels from anon;
revoke all on table public.guild_channels from authenticated;

-- ============================================================
-- Consolidated section from 008_voice_rtc.sql
-- ============================================================
-- WebRTC voice-channel signaling and ephemeral presence.
-- Browser clients never receive direct table privileges; the Flask Actor/Policy
-- boundary owns membership checks, session ownership, signaling and cleanup.

insert into public.guild_channels(guild_id, name, channel_type, position)
select g.id, 'general', 'voice', 0
  from public.guilds g
 where not exists (
       select 1
         from public.guild_channels ch
        where ch.guild_id = g.id
          and ch.channel_type = 'voice'
          and ch.position = 0
 )
on conflict do nothing;

create table if not exists public.voice_sessions (
    id uuid primary key default gen_random_uuid(),
    guild_id uuid not null references public.guilds(id) on delete cascade,
    channel_id uuid not null references public.guild_channels(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    joined_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    constraint voice_sessions_unique_actor unique (channel_id, user_id)
);

create index if not exists voice_sessions_channel_seen
    on public.voice_sessions (channel_id, last_seen_at desc, id);

create table if not exists public.voice_signals (
    id bigserial primary key,
    channel_id uuid not null references public.guild_channels(id) on delete cascade,
    sender_session_id uuid not null references public.voice_sessions(id) on delete cascade,
    target_session_id uuid not null references public.voice_sessions(id) on delete cascade,
    signal_type text not null check (signal_type in ('offer','answer','ice')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    constraint voice_signal_not_self check (sender_session_id <> target_session_id),
    constraint voice_signal_payload_object check (jsonb_typeof(payload) = 'object')
);

create index if not exists voice_signals_target_created
    on public.voice_signals (target_session_id, created_at asc, id asc);

alter table public.voice_sessions enable row level security;
alter table public.voice_sessions force row level security;
alter table public.voice_signals enable row level security;
alter table public.voice_signals force row level security;

revoke all on table public.voice_sessions from public;
revoke all on table public.voice_sessions from anon;
revoke all on table public.voice_sessions from authenticated;
revoke all on table public.voice_signals from public;
revoke all on table public.voice_signals from anon;
revoke all on table public.voice_signals from authenticated;
revoke all on sequence public.voice_signals_id_seq from public;
revoke all on sequence public.voice_signals_id_seq from anon;
revoke all on sequence public.voice_signals_id_seq from authenticated;

-- ============================================================
-- Consolidated section: Web Admin allowlist and service bridge
-- ============================================================
-- Explicit allowlist for the GitHub Pages administrative control plane.
-- Membership is assigned by UUID only after the owner identity is confirmed.
create schema if not exists app_private;

create table if not exists app_private.web_admins (
    user_id uuid primary key references auth.users(id) on delete cascade,
    enabled boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

revoke all on schema app_private from public;
revoke all on schema app_private from anon;
revoke all on schema app_private from authenticated;
revoke all on table app_private.web_admins from public;
revoke all on table app_private.web_admins from anon;
revoke all on table app_private.web_admins from authenticated;

-- Minimal service-only bridge for the admin Edge Function. The app_private
-- schema remains unexposed to PostgREST and browser roles cannot execute this.
create or replace function public.web_admin_authorization(p_user_id uuid)
returns table(enabled boolean, enabled_admins bigint)
language sql
stable
security definer
set search_path = ''
as $$
  select
    exists (
      select 1
      from app_private.web_admins wa
      where wa.user_id = p_user_id
        and wa.enabled = true
    ) as enabled,
    (
      select count(*)
      from app_private.web_admins wa
      where wa.enabled = true
    ) as enabled_admins;
$$;

revoke all on function public.web_admin_authorization(uuid) from public;
revoke all on function public.web_admin_authorization(uuid) from anon;
revoke all on function public.web_admin_authorization(uuid) from authenticated;
grant execute on function public.web_admin_authorization(uuid) to service_role;
