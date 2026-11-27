"""Fills a demo account with 14 days of realistic check-ins.

Run from the backend folder, with the .venv active:
    python seed_demo.py

Then log in with:  username = demo   password = demo12345

The numbers are generated (not real student data). The patterns built in on
purpose are: hot days -> less sleep, 3+ coffees -> lower sleep quality,
weekends -> more sleep, a rough patch in the middle, and a recovery at the end.
"""
import os
import random
from datetime import date, timedelta

import bcrypt
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo12345"
DEMO_NAME = "Alex"


def clamp(value, low, high):
    return max(low, min(high, value))


def burnout_level(sleep, quality, temp, study, caffeine):
    """Same rules as the label in train_model.py (a heuristic, not real burnout data)."""
    score = 0
    if sleep < 5.5:
        score += 2
    elif sleep < 7.0:
        score += 1
    if quality <= 4:
        score += 2
    elif quality <= 6:
        score += 1
    if temp >= 32.0 and sleep < 6.5:
        score += 1
    if study > 6.0 or caffeine >= 3:
        score += 1
    return 2 if score >= 4 else 1 if score >= 2 else 0


def generate_rows(today, days=14, seed=42):
    """Returns a list of daily check-ins, oldest first."""
    rng = random.Random(seed)
    rows = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        weekend = d.weekday() >= 5
        rough_patch = 4 <= i <= 8
        recovery = i >= days - 4

        temp = round(rng.uniform(26.0, 35.0), 1)
        caffeine = rng.choice([0, 1, 2, 2, 3, 3, 4, 5])

        sleep = (7.6 if weekend else 6.8) + rng.uniform(-0.4, 0.4)
        if temp >= 32:
            sleep -= 1.4
        if caffeine >= 3:
            sleep -= 0.4
        if rough_patch:
            sleep -= 1.2
        if recovery:
            sleep += 1.0
        sleep = round(clamp(sleep, 3.5, 9.5), 1)

        quality = (
            7
            - 0.9 * max(caffeine - 2, 0)
            - (0.6 if temp >= 32 else 0)
            - (0.8 if rough_patch else 0)
            + (0.6 if recovery else 0)
            + rng.uniform(-0.8, 0.8)
        )
        quality = int(clamp(round(quality), 1, 10))

        study = clamp(rng.uniform(3, 7) + (2 if rough_patch else 0), 1, 12)
        screen = clamp(rng.uniform(2.5, 6.5) + (1 if rough_patch else 0), 1, 12)
        study = round(study * 2) / 2
        screen = round(screen * 2) / 2

        rows.append(
            {
                "log_date": d,
                "hours_slept": sleep,
                "caffeine_cups": caffeine,
                "sleep_quality": quality,
                "study_hours": study,
                "screen_time": screen,
                "temperature_c": temp,
                "risk_level": burnout_level(sleep, quality, temp, study, caffeine),
            }
        )
    return rows


def main():
    load_dotenv()
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()

    with conn:
        user = conn.execute(
            "select user_id from users where lower(username) = %s", (DEMO_USERNAME,)
        ).fetchone()
        if user:
            user_id = user["user_id"]
            conn.execute(
                """update users set password_hash = %s, display_name = %s,
                          target_sleep_hours = 8.0, affection_points = 0,
                          current_mood_state = 'neutral'
                   where user_id = %s""",
                (pw_hash, DEMO_NAME, user_id),
            )
            conn.execute("delete from sleep_logs where user_id = %s", (user_id,))
        else:
            user_id = conn.execute(
                """insert into users (username, password_hash, display_name, target_sleep_hours)
                   values (%s, %s, %s, 8.0) returning user_id""",
                (DEMO_USERNAME, pw_hash, DEMO_NAME),
            ).fetchone()["user_id"]

        # oldest first, so the database triggers build the 7-day sleep debt in order
        for r in generate_rows(date.today()):
            conn.execute(
                """insert into sleep_logs
                     (user_id, log_date, hours_slept, caffeine_cups, sleep_quality,
                      study_hours, screen_time, temperature_c, risk_level)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    user_id, r["log_date"], r["hours_slept"], r["caffeine_cups"],
                    r["sleep_quality"], r["study_hours"], r["screen_time"],
                    r["temperature_c"], r["risk_level"],
                ),
            )

    print("Demo account ready.")
    print(f"  username: {DEMO_USERNAME}")
    print(f"  password: {DEMO_PASSWORD}")
    print("  14 days of check-ins loaded.")


if __name__ == "__main__":
    main()