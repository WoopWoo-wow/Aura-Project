import os
from datetime import date
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
DEMO_USER = "00000000-0000-0000-0000-000000000001"  # JWT auth replaces this later

app = FastAPI(title="AURA API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your Vercel URL on deploy
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


class SleepIn(BaseModel):
    hours_slept: float = Field(ge=0, le=24)
    caffeine_cups: int = Field(default=0, ge=0, le=20)
    log_date: Optional[date] = None


def companion_line(d: dict) -> str:
    """Placeholder persona text, grounded in real DB numbers.
    Later this gets swapped for a Gemini call using the same dict."""
    if d["hours_slept"] is None:
        return "Hmph. You haven't even checked in yet. Log your sleep already!"
    h = float(d["hours_slept"])
    debt = float(d["calculated_sleep_debt"])
    cups = d["caffeine_cups"]
    target = float(d["target_sleep_hours"])
    lines = {
        "flustered_praise": f"W-well... {h}h of sleep. It's not like I was worried or anything. Keep it up, I guess.",
        "neutral": f"{h}h last night, {debt}h of debt this week. Acceptable. Don't get comfortable.",
        "worried": f"You're {debt}h behind this week. ...Not that I care, but go to bed earlier, idiot.",
        "annoyed": f"{h}h?! Target is {target}h. That's {debt}h of debt. And {cups} cups of coffee won't fix it!",
        "strict": f"{debt}h of sleep debt. DEBT. Sit down. Phone away. We are fixing this tonight.",
    }
    return lines[d["current_mood_state"]]


@app.get("/api/dashboard")
def dashboard():
    with db() as conn:
        row = conn.execute(
            "select * from v_dashboard_today where user_id = %s", (DEMO_USER,)
        ).fetchone()
        history = conn.execute(
            """select log_date, hours_slept, calculated_sleep_debt
               from sleep_logs where user_id = %s
               order by log_date desc limit 7""",
            (DEMO_USER,),
        ).fetchall()
    if not row:
        raise HTTPException(404, "user not found")
    row["companion_message"] = companion_line(row)
    row["history"] = list(reversed(history))
    return row


@app.post("/api/sleep")
def log_sleep(body: SleepIn):
    d = body.log_date or date.today()
    with db() as conn:
        # upsert; the DB triggers compute debt and update mood
        conn.execute(
            """insert into sleep_logs (user_id, log_date, hours_slept, caffeine_cups)
               values (%s, %s, %s, %s)
               on conflict (user_id, log_date)
               do update set hours_slept = excluded.hours_slept,
                             caffeine_cups = excluded.caffeine_cups""",
            (DEMO_USER, d, body.hours_slept, body.caffeine_cups),
        )
        conn.commit()
    return dashboard()