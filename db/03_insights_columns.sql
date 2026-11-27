alter table sleep_logs add column if not exists sleep_quality int check (sleep_quality between 1 and 10);
alter table sleep_logs add column if not exists study_hours numeric(3,1);
alter table sleep_logs add column if not exists screen_time numeric(3,1);
alter table sleep_logs add column if not exists temperature_c numeric(4,1);
alter table sleep_logs add column if not exists risk_level int check (risk_level between 0 and 2);