import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import httpx
import joblib
import jwt
import pandas as pd
import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_HOURS = 24

app = FastAPI(title="AURA API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend URL on deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- ML model (loaded once when the server starts) ----
model = joblib.load(Path(__file__).parent / "burnout_model.pkl")
RISK_LABELS = {0: "Low", 1: "Moderate", 2: "High"}


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# =====================  AUTH  =====================
bearer = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS)
    return jwt.encode({"sub": user_id, "exp": exp}, JWT_SECRET, algorithm="HS256")


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """Reads the login token and returns the user_id. Used by every protected endpoint."""
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        return payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token. Please log in again.")


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=1, max_length=40)
    target_sleep_hours: float = Field(default=8.0, ge=4, le=12)
    worst_habit: str = Field(default="all-nighters", max_length=40)


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
def register(body: RegisterIn):
    username = body.username.strip().lower()
    with db() as conn:
        exists = conn.execute(
            "select 1 from users where lower(username) = %s", (username,)
        ).fetchone()
        if exists:
            raise HTTPException(409, "That username is already taken.")
        user = conn.execute(
            """insert into users (username, password_hash, display_name,
                                  target_sleep_hours, worst_habit)
               values (%s, %s, %s, %s, %s)
               returning user_id""",
            (username, hash_password(body.password), body.display_name.strip(),
             body.target_sleep_hours, body.worst_habit),
        ).fetchone()
        conn.commit()
    user_id = str(user["user_id"])
    return {"access_token": create_token(user_id), "token_type": "bearer"}


@app.post("/api/auth/login")
def login(body: LoginIn):
    username = body.username.strip().lower()
    with db() as conn:
        user = conn.execute(
            "select user_id, password_hash from users where lower(username) = %s",
            (username,),
        ).fetchone()
    # same message for wrong username or wrong password, so nobody can probe usernames
    if not user or not user["password_hash"] or not verify_password(
        body.password, user["password_hash"]
    ):
        raise HTTPException(401, "Invalid username or password.")
    return {"access_token": create_token(str(user["user_id"])), "token_type": "bearer"}


@app.get("/api/me")
def me(user_id: str = Depends(get_current_user)):
    with db() as conn:
        user = conn.execute(
            """select username, display_name, target_sleep_hours, worst_habit,
                      affection_points, current_mood_state
               from users where user_id = %s""",
            (user_id,),
        ).fetchone()
    if not user:
        raise HTTPException(404, "User not found.")
    return user


# =====================  REQUEST MODELS  =====================
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


# =====================  PERSONA  =====================
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


def predict_line(level: int, body: "PredictIn", temp: float, tier: str) -> str:
    """AURA's reaction to the ML result. Numbers come from the model and
    inputs; the tier only changes how warm she sounds (cold = no praise, never cruel)."""
    h = body.sleep_duration
    c = body.caffeine_intake
    lines = {
        2: {
            "cold": f"{h}h of sleep, {c} cups of coffee, {temp} degrees outside. Burnout risk is high. Rest early tonight and cut the caffeine.",
            "neutral": f"H-Hmph! {h}h of sleep and {c} cups of coffee at {temp} degrees?! Your burnout risk is high, idiot. Sleep early tonight!",
            "warm": f"Hey... {h}h of sleep isn't enough and your risk is high. I-I'm not worried or anything, but please rest tonight, okay?",
        },
        1: {
            "cold": f"Burnout risk is moderate. {h}h of sleep is not enough. Take a break and sleep on time tonight.",
            "neutral": f"Hmph. Moderate risk. You're not in trouble yet, but {h}h of sleep isn't great. Don't push it.",
            "warm": "Moderate risk... you're holding on, but I'm watching you. Get a proper rest tonight, alright?",
        },
        0: {
            "cold": "Burnout risk is low. Keep your routine as it is.",
            "neutral": "Low risk. Acceptable. Don't get comfortable, though.",
            "warm": "L-Low risk! ...Good job. It's not like I was cheering for you or anything!",
        },
    }
    return lines[level][tier]


# =====================  WEATHER (Open-Meteo, Davao City)  =====================
def get_davao_temp():
    """Live temperature from Open-Meteo; returns (temp, ok)."""
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": 7.1907, "longitude": 125.4553, "current": "temperature_2m"},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()["current"]["temperature_2m"], True
    except Exception:
        return 30.0, False  # fallback so the demo never crashes


# =====================  PROTECTED ENDPOINTS  =====================
def build_dashboard(user_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "select * from v_dashboard_today where user_id = %s", (user_id,)
        ).fetchone()
        history = conn.execute(
            """select log_date, hours_slept, calculated_sleep_debt
               from sleep_logs where user_id = %s
               order by log_date desc limit 7""",
            (user_id,),
        ).fetchall()
    if not row:
        raise HTTPException(404, "user not found")
    row["companion_message"] = companion_line(row)
    row["history"] = list(reversed(history))
    return row


@app.get("/api/dashboard")
def dashboard(user_id: str = Depends(get_current_user)):
    return build_dashboard(user_id)


@app.post("/api/sleep")
def log_sleep(body: SleepIn, user_id: str = Depends(get_current_user)):
    d = body.log_date or date.today()
    with db() as conn:
        # upsert; the DB triggers compute debt and update mood
        conn.execute(
            """insert into sleep_logs (user_id, log_date, hours_slept, caffeine_cups)
               values (%s, %s, %s, %s)
               on conflict (user_id, log_date)
               do update set hours_slept = excluded.hours_slept,
                             caffeine_cups = excluded.caffeine_cups""",
            (user_id, d, body.hours_slept, body.caffeine_cups),
        )
        conn.commit()
    return build_dashboard(user_id)


@app.post("/api/predict")
def predict(body: PredictIn, user_id: str = Depends(get_current_user)):
    try:
        temp, weather_ok = get_davao_temp()

        # affection points decide how warm AURA sounds
        try:
            with db() as conn:
                u = conn.execute(
                    "select affection_points from users where user_id = %s",
                    (user_id,),
                ).fetchone()
            points = int(u["affection_points"]) if u else 0
        except Exception:
            points = 0
        tier = affection_tier(points)

        row = pd.DataFrame([{
            "Sleep_Duration": body.sleep_duration,
            "Study_Hours": body.study_hours,
            "Screen_Time": body.screen_time,
            "Caffeine_Intake": body.caffeine_intake,
            "Sleep_Quality": body.sleep_quality,
            "Temperature_C": temp,
        }])
        level = int(model.predict(row)[0])
        probs = dict(zip(model.classes_, model.predict_proba(row)[0]))
        return {
            "risk_level": level,
            "risk_label": RISK_LABELS[level],
            "risk_probabilities": {
                RISK_LABELS[int(k)]: round(float(v), 2) for k, v in probs.items()
            },
            "temperature_c": temp,
            "weather_live": weather_ok,
            "affection_points": points,
            "affection_tier": tier,
            "aura_message": predict_line(level, body, temp, tier),
        }
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


# =====================  WHAT-IF SIMULATOR  =====================
class WhatIfIn(BaseModel):
    current: PredictIn                       # what the user entered today
    sleep_delta: float = Field(default=0, ge=-12, le=12)
    study_delta: float = Field(default=0, ge=-12, le=12)
    screen_delta: float = Field(default=0, ge=-12, le=12)
    caffeine_delta: int = Field(default=0, ge=-10, le=10)
    quality_delta: int = Field(default=0, ge=-9, le=9)


def clamp(value, low, high):
    return max(low, min(high, value))


def run_model(p: PredictIn, temp: float):
    """Runs the burnout model once. Returns (risk_level, probabilities by label)."""
    row = pd.DataFrame([{
        "Sleep_Duration": p.sleep_duration,
        "Study_Hours": p.study_hours,
        "Screen_Time": p.screen_time,
        "Caffeine_Intake": p.caffeine_intake,
        "Sleep_Quality": p.sleep_quality,
        "Temperature_C": temp,
    }])
    level = int(model.predict(row)[0])
    probs = dict(zip(model.classes_, model.predict_proba(row)[0]))
    return level, {RISK_LABELS[int(k)]: round(float(v), 2) for k, v in probs.items()}


@app.post("/api/whatif")
def whatif(body: WhatIfIn, user_id: str = Depends(get_current_user)):
    """'What if I slept 2h more / drank 2 fewer coffees?' Re-runs the same model."""
    try:
        temp, weather_ok = get_davao_temp()
        c = body.current
        changed = PredictIn(
            sleep_duration=clamp(c.sleep_duration + body.sleep_delta, 0, 24),
            study_hours=clamp(c.study_hours + body.study_delta, 0, 24),
            screen_time=clamp(c.screen_time + body.screen_delta, 0, 24),
            caffeine_intake=clamp(c.caffeine_intake + body.caffeine_delta, 0, 20),
            sleep_quality=clamp(c.sleep_quality + body.quality_delta, 1, 10),
        )
        before_level, before_probs = run_model(c, temp)
        after_level, after_probs = run_model(changed, temp)
        b, a = RISK_LABELS[before_level], RISK_LABELS[after_level]

        if after_level < before_level:
            message = f"Hmph. Do that and your risk goes from {b} to {a}. ...Not that I care. Just do it."
        elif after_level == before_level:
            message = f"That changes nothing. You're still at {a} risk. Try changing more than that, idiot."
        else:
            message = f"Is that a joke? That makes it worse: {b} to {a}."

        return {
            "before": {"risk_label": b, "risk_level": before_level, "risk_probabilities": before_probs},
            "after": {"risk_label": a, "risk_level": after_level, "risk_probabilities": after_probs},
            "changed_inputs": changed.model_dump(),
            "temperature_c": temp,
            "weather_live": weather_ok,
            "aura_message": message,
        }
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


# =====================  RECOVERY PLAN (plain math, no ML)  =====================
def recovery_plan(debt: float, target: float) -> dict:
    """How many nights of extra sleep clear the current 7-day sleep debt."""
    if debt <= 0:
        return {"debt_hours": 0, "options": [], "message": "No sleep debt. Keep it up, I guess."}
    options = []
    for extra in (1, 2):
        sleep_each_night = min(target + extra, 12)
        real_extra = sleep_each_night - target
        if real_extra > 0 and all(o["sleep_hours_per_night"] != sleep_each_night for o in options):
            options.append({
                "extra_hours_per_night": real_extra,
                "sleep_hours_per_night": sleep_each_night,
                "nights_needed": math.ceil(debt / real_extra),
            })
    best = options[-1] if options else None
    message = (
        f"You owe {debt}h of sleep. Sleep {best['sleep_hours_per_night']}h for "
        f"{best['nights_needed']} night(s) and the debt is gone."
        if best else f"You owe {debt}h of sleep. Start going to bed earlier."
    )
    return {"debt_hours": debt, "options": options, "message": message}


@app.get("/api/recovery")
def recovery(user_id: str = Depends(get_current_user)):
    with db() as conn:
        row = conn.execute(
            "select target_sleep_hours, calculated_sleep_debt from v_dashboard_today where user_id = %s",
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    debt = float(row["calculated_sleep_debt"] or 0)
    target = float(row["target_sleep_hours"])
    return recovery_plan(debt, target)