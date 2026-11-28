alter table users add column if not exists password_hash text;
alter table users add column if not exists display_name  text;
alter table users add column if not exists worst_habit   text default 'all-nighters';
create unique index if not exists users_username_unique on users (lower(username));