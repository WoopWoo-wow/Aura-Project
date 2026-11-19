import os
from datetime import date
from pathlib import Path
from typing import Optional

import httpx
import joblib
import pandas as pd
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
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

# ---- ML model (loaded once when the server starts) ----
model = joblib.load(Path(__file__).parent / "burnout_model.pkl")
RISK_LABELS = {0: "Low", 1: "Moderate", 2: "High"}


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# ---- Request models ----
class SleepIn(BaseModel):
    hours_slept: float = Field(ge=0, le=24)
    caffeine_cups: int = Field(default=0, ge=0, le=20)
    log_date: Optional[date] = None


class PredictIn(BaseModel):
    sleep_duration: float = Field(ge=0, le=24)
    study_hours: float = Field(ge=0, le=24)
    screen_time: float = Field(ge=0, le=24)
    caffeine_intake: int = Field(ge=0, le=20)
    sleep_quality: int = Field(ge=1, le=10)


class CheckinIn(PredictIn):
    log_date: Optional[date] = None


# ---- Persona ----
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


def affection_tier(points: int) -> str:
    if points <= 4:
        return "cold"
    if points <= 14:
        return "neutral"
    return "warm"


def predict_line(level: int, body: PredictIn, temp: float, tier: str) -> str:
    """AURA's reaction to the ML result. Numbers come from the model and
    inputs; the tier only changes how warm she sounds (cold = no praise, never cruel)."""
    h = body.sleep_duration
    c = body.caffeine_intake
    lines = {
        2: {  # High risk
            "cold": f"{h}h of sleep, {c} cups of coffee, {temp} degrees outside. Burnout risk is high. Rest early tonight and cut the caffeine.",
            "neutral": f"H-Hmph! {h}h of sleep and {c} cups of coffee at {temp} degrees?! Your burnout risk is high, idiot. Sleep early tonight!",
            "warm": f"Hey... {h}h of sleep isn't enough and your risk is high. I-I'm not worried or anything, but please rest tonight, okay?",
        },
        1: {  # Moderate risk
            "cold": f"Burnout risk is moderate. {h}h of sleep is not enough. Take a break and sleep on time tonight.",
            "neutral": f"Hmph. Moderate risk. You're not in trouble yet, but {h}h of sleep isn't great. Don't push it.",
            "warm": f"Moderate risk... you're holding on, but I'm watching you. Get a proper rest tonight, alright?",
        },
        0: {  # Low risk
            "cold": "Burnout risk is low. Keep your routine as it is.",
            "neutral": "Low risk. Acceptable. Don't get comfortable, though.",
            "warm": "L-Low risk! ...Good job. It's not like I was cheering for you or anything!",
        },
    }
    return lines[level][tier]


# ---- Weather (Open-Meteo, Davao City) ----
def get_davao_temp():
    """Live temperature from Open-Meteo; returns (temp, ok)."""
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 7.1907,
                "longitude": 125.4553,
                "current": "temperature_2m",
            },
            timeout=5,
        )
        r.raise_for_status()
        return r.json()["current"]["temperature_2m"], True
    except Exception:
        return 30.0, False  # fallback so the demo never crashes


# ---- Shared Helpers ----
def run_burnout_model(body: PredictIn, temp: float):
    row = pd.DataFrame(
        [
            {
                "Sleep_Duration": body.sleep_duration,
                "Study_Hours": body.study_hours,
                "Screen_Time": body.screen_time,
                "Caffeine_Intake": body.caffeine_intake,
                "Sleep_Quality": body.sleep_quality,
                "Temperature_C": temp,
            }
        ]
    )
    level = int(model.predict(row)[0])
    raw_probs = dict(zip(model.classes_, model.predict_proba(row)[0]))
    probs = {RISK_LABELS[int(k)]: round(float(v), 2) for k, v in raw_probs.items()}
    return level, RISK_LABELS[level], probs


def fetch_dashboard(conn) -> dict:
    row = conn.execute(
        "select * from v_dashboard_today where user_id = %s", (DEMO_USER,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")

    history = conn.execute(
        """select log_date, hours_slept, caffeine_cups, calculated_sleep_debt,
                  study_hours, screen_time, sleep_quality, risk_level, temperature_c
           from sleep_logs
           where user_id = %s
           order by log_date desc limit 7""",
        (DEMO_USER,),
    ).fetchall()

    row["companion_message"] = companion_line(row)
    row["history"] = list(reversed(history))
    return row


def get_affection_points(conn) -> int:
    try:
        u = conn.execute(
            "select affection_points from users where user_id = %s",
            (DEMO_USER,),
        ).fetchone()
        return int(u["affection_points"]) if u else 0
    except Exception:
        return 0


# ---- Endpoints ----
@app.get("/api/dashboard")
def dashboard():
    with db() as conn:
        return fetch_dashboard(conn)


@app.post("/api/checkin")
def checkin(body: CheckinIn):
    """Unified daily check-in: fetches weather, runs ML model, saves full log,
    and returns both the prediction/AURA message and updated dashboard state."""
    try:
        d = body.log_date or date.today()
        temp, weather_ok = get_davao_temp()
        level, label, probs = run_burnout_model(body, temp)

        with db() as conn:
            conn.execute(
                """insert into sleep_logs (
                       user_id, log_date, hours_slept, caffeine_cups,
                       study_hours, screen_time, sleep_quality,
                       risk_level, temperature_c
                   )
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (user_id, log_date)
                   do update set hours_slept = excluded.hours_slept,
                                 caffeine_cups = excluded.caffeine_cups,
                                 study_hours = excluded.study_hours,
                                 screen_time = excluded.screen_time,
                                 sleep_quality = excluded.sleep_quality,
                                 risk_level = excluded.risk_level,
                                 temperature_c = excluded.temperature_c""",
                (
                    DEMO_USER,
                    d,
                    body.sleep_duration,
                    body.caffeine_intake,
                    body.study_hours,
                    body.screen_time,
                    body.sleep_quality,
                    level,
                    temp,
                ),
            )
            conn.commit()

            dash = fetch_dashboard(conn)
            points = (
                int(dash["affection_points"])
                if dash.get("affection_points") is not None
                else get_affection_points(conn)
            )

        tier = affection_tier(points)
        return {
            **dash,
            "risk_level": level,
            "risk_label": label,
            "risk_probabilities": probs,
            "temperature_c": temp,
            "weather_live": weather_ok,
            "affection_points": points,
            "affection_tier": tier,
            "aura_message": predict_line(level, body, temp, tier),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.post("/api/sleep")
def log_sleep(body: SleepIn):
    d = body.log_date or date.today()
    with db() as conn:
        conn.execute(
            """insert into sleep_logs (user_id, log_date, hours_slept, caffeine_cups)
               values (%s, %s, %s, %s)
               on conflict (user_id, log_date)
               do update set hours_slept = excluded.hours_slept,
                             caffeine_cups = excluded.caffeine_cups""",
            (DEMO_USER, d, body.hours_slept, body.caffeine_cups),
        )
        conn.commit()
        return fetch_dashboard(conn)


@app.post("/api/predict")
def predict(body: PredictIn):
    try:
        temp, weather_ok = get_davao_temp()
        with db() as conn:
            points = get_affection_points(conn)
        tier = affection_tier(points)
        level, label, probs = run_burnout_model(body, temp)
        return {
            "risk_level": level,
            "risk_label": label,
            "risk_probabilities": probs,
            "temperature_c": temp,
            "weather_live": weather_ok,
            "affection_points": points,
            "affection_tier": tier,
            "aura_message": predict_line(level, body, temp, tier),
        }
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")