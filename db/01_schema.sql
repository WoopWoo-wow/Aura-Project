create extension if not exists "pgcrypto";

create table if not exists users (
  user_id            uuid primary key default gen_random_uuid(),
  username           text not null,
  email              text unique,
  target_sleep_hours numeric(3,1) not null default 8.0,
  affection_points   int not null default 0,
  current_mood_state text not null default 'neutral'
    check (current_mood_state in ('annoyed','strict','worried','neutral','flustered_praise')),
  created_at         timestamptz not null default now()
);

create table if not exists sleep_logs (
  sleep_id              bigserial primary key,
  user_id               uuid not null references users(user_id) on delete cascade,
  log_date              date not null default current_date,
  hours_slept           numeric(3,1) not null check (hours_slept between 0 and 24),
  caffeine_cups         int not null default 0 check (caffeine_cups >= 0),
  calculated_sleep_debt numeric(4,1),
  unique (user_id, log_date)
);

-- TRIGGER 1 (BEFORE): rolling 7-day cumulative sleep debt
create or replace function fn_calc_sleep_debt() returns trigger as $$
declare
  target numeric;
  prev_debt numeric;
begin
  select target_sleep_hours into target from users where user_id = new.user_id;

  select coalesce(sum(greatest(target - hours_slept, 0)), 0) into prev_debt
  from sleep_logs
  where user_id = new.user_id
    and log_date between new.log_date - 6 and new.log_date - 1;

  new.calculated_sleep_debt := prev_debt + greatest(target - new.hours_slept, 0);
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_calc_sleep_debt on sleep_logs;
create trigger trg_calc_sleep_debt
before insert or update on sleep_logs
for each row execute function fn_calc_sleep_debt();

-- TRIGGER 2 (AFTER): update companion mood + affection
create or replace function fn_update_mood() returns trigger as $$
declare
  target numeric;
  new_mood text;
begin
  select target_sleep_hours into target from users where user_id = new.user_id;

  new_mood := case
    when new.hours_slept >= target and new.calculated_sleep_debt <= 1 then 'flustered_praise'
    when new.calculated_sleep_debt <= 3  then 'neutral'
    when new.calculated_sleep_debt <= 6  then 'worried'
    when new.calculated_sleep_debt <= 10 then 'annoyed'
    else 'strict'
  end;

  update users
  set current_mood_state = new_mood,
      affection_points = affection_points + case when new.hours_slept >= target then 2 else 0 end
  where user_id = new.user_id;

  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_update_mood on sleep_logs;
create trigger trg_update_mood
after insert or update on sleep_logs
for each row execute function fn_update_mood();

-- VIEW: what the dashboard reads
create or replace view v_dashboard_today as
select u.user_id, u.username, u.target_sleep_hours, u.affection_points, u.current_mood_state,
       s.log_date, s.hours_slept, s.caffeine_cups, s.calculated_sleep_debt
from users u
left join lateral (
  select * from sleep_logs where user_id = u.user_id order by log_date desc limit 1
) s on true;

-- Demo user (no auth tonight; JWT comes later)
insert into users (user_id, username, email)
values ('00000000-0000-0000-0000-000000000001', 'demo', 'demo@aura.dev')
on conflict do nothing;