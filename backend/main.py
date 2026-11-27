import logging
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
from fastapi import Depends, FastAPI, HTTPException, Query
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


logger = logging.getLogger("aura")


def server_error(e: Exception) -> HTTPException:
    """Log the real error on the server, give the user only a generic message."""
    logger.exception("Unhandled error: %s", e)
    return HTTPException(500, "Something went wrong on the server. Please try again.")


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
        raise server_error(e)


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
        raise server_error(e)


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


# =====================  FULL DAILY CHECK-IN  =====================
class CheckinIn(BaseModel):
    sleep_duration: float = Field(ge=0, le=24)
    study_hours: float = Field(ge=0, le=24)
    screen_time: float = Field(ge=0, le=24)
    caffeine_intake: int = Field(ge=0, le=20)
    sleep_quality: int = Field(ge=1, le=10)
    log_date: Optional[date] = None


@app.post("/api/checkin")
def checkin(body: CheckinIn, user_id: str = Depends(get_current_user)):
    """One call for the daily form: saves everything, runs the model, returns AURA's reaction."""
    try:
        temp, weather_ok = get_davao_temp()
        p = PredictIn(
            sleep_duration=body.sleep_duration,
            study_hours=body.study_hours,
            screen_time=body.screen_time,
            caffeine_intake=body.caffeine_intake,
            sleep_quality=body.sleep_quality,
        )
        level, probs = run_model(p, temp)
        d = body.log_date or date.today()

        with db() as conn:
            # upsert; the DB triggers compute sleep debt, mood and affection
            conn.execute(
                """insert into sleep_logs
                     (user_id, log_date, hours_slept, caffeine_cups, sleep_quality,
                      study_hours, screen_time, temperature_c, risk_level)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (user_id, log_date) do update set
                     hours_slept = excluded.hours_slept,
                     caffeine_cups = excluded.caffeine_cups,
                     sleep_quality = excluded.sleep_quality,
                     study_hours = excluded.study_hours,
                     screen_time = excluded.screen_time,
                     temperature_c = excluded.temperature_c,
                     risk_level = excluded.risk_level""",
                (user_id, d, body.sleep_duration, body.caffeine_intake,
                 body.sleep_quality, body.study_hours, body.screen_time, temp, level),
            )
            conn.commit()
            u = conn.execute(
                "select affection_points from users where user_id = %s", (user_id,)
            ).fetchone()

        points = int(u["affection_points"]) if u else 0
        tier = affection_tier(points)
        return {
            "risk_level": level,
            "risk_label": RISK_LABELS[level],
            "risk_probabilities": probs,
            "temperature_c": temp,
            "weather_live": weather_ok,
            "affection_points": points,
            "affection_tier": tier,
            "aura_message": predict_line(level, p, temp, tier),
            "dashboard": build_dashboard(user_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise server_error(e)


# =====================  INSIGHTS (3-day recap + personal patterns)  =====================
RECAP_LOGS = 3             # recap looks at the last 3 check-ins
MIN_LOGS_FOR_PATTERNS = 7  # pattern insights unlock after this many check-ins
MIN_PER_GROUP = 2          # days needed on each side of a comparison
HIGH_CAFFEINE = 3          # cups per day counted as "high"
HOT_C = 32.0               # temperature counted as a hot day
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]  # Postgres dow: 0 = Sunday
NOT_CAUSE = " This is a pattern in your own logs, not proof of cause."


def num(x):
    return None if x is None else round(float(x), 1)


def build_recap(rows: list) -> dict:
    """rows: the latest check-ins, newest first."""
    if len(rows) < RECAP_LOGS:
        need = RECAP_LOGS - len(rows)
        return {
            "status": "locked",
            "logs_have": len(rows),
            "logs_needed": RECAP_LOGS,
            "message": f"Log {need} more check-in(s) to unlock your 3-day recap.",
        }
    rows = list(reversed(rows))  # oldest first
    sleeps = [float(r["hours_slept"]) for r in rows]
    qualities = [r["sleep_quality"] for r in rows if r["sleep_quality"] is not None]
    studies = [float(r["study_hours"]) for r in rows if r["study_hours"] is not None]
    cups = [r["caffeine_cups"] for r in rows]

    best = max(rows, key=lambda r: float(r["hours_slept"]))
    worst = min(rows, key=lambda r: float(r["hours_slept"]))

    debt_first = float(rows[0]["calculated_sleep_debt"] or 0)
    debt_last = float(rows[-1]["calculated_sleep_debt"] or 0)
    if debt_last < debt_first - 0.5:
        debt_trend = "shrinking"
    elif debt_last > debt_first + 0.5:
        debt_trend = "growing"
    else:
        debt_trend = "steady"

    risk_first, risk_last = rows[0]["risk_level"], rows[-1]["risk_level"]
    if risk_first is None or risk_last is None:
        risk_trend = None
    elif risk_last < risk_first:
        risk_trend = "improving"
    elif risk_last > risk_first:
        risk_trend = "getting worse"
    else:
        risk_trend = "steady"

    avg_sleep = num(sum(sleeps) / len(sleeps))
    message = f"Over your last {RECAP_LOGS} check-ins you averaged {avg_sleep}h of sleep, and your sleep debt is {debt_trend}."
    if risk_trend:
        message += f" Burnout risk is {risk_trend}."

    return {
        "status": "ready",
        "from_date": rows[0]["log_date"].isoformat(),
        "to_date": rows[-1]["log_date"].isoformat(),
        "avg_sleep_hours": avg_sleep,
        "avg_sleep_quality": num(sum(qualities) / len(qualities)) if qualities else None,
        "avg_study_hours": num(sum(studies) / len(studies)) if studies else None,
        "avg_caffeine_cups": num(sum(cups) / len(cups)),
        "best_day": {"date": best["log_date"].isoformat(), "hours_slept": num(best["hours_slept"])},
        "worst_day": {"date": worst["log_date"].isoformat(), "hours_slept": num(worst["hours_slept"])},
        "sleep_debt_trend": debt_trend,
        "risk_trend": risk_trend,
        "message": message,
    }


def compare_groups(key, title, a, b, label_a, label_b, unit, higher_is_better=True):
    """a / b are dicts with n and avg (e.g. high-caffeine days vs other days)."""
    if a["n"] < MIN_PER_GROUP or b["n"] < MIN_PER_GROUP:
        return {
            "key": key, "title": title, "status": "locked",
            "text": f"Not enough data yet: {a['n']} {label_a} day(s) and {b['n']} {label_b} day(s) so far (need {MIN_PER_GROUP} of each).",
        }
    avg_a, avg_b = float(a["avg"]), float(b["avg"])
    diff = round(abs(avg_a - avg_b), 1)
    data = {label_a: num(avg_a), label_b: num(avg_b), "difference": diff}
    if diff < 0.5:
        text = f"No clear difference: {label_a} days average {num(avg_a)}{unit}, {label_b} days {num(avg_b)}{unit}."
    else:
        word = "lower" if avg_a < avg_b else "higher"
        text = (f"On {label_a} days your average is {num(avg_a)}{unit} versus {num(avg_b)}{unit} "
                f"on {label_b} days ({diff}{unit} {word}).{NOT_CAUSE}")
    return {"key": key, "title": title, "status": "ready", "text": text, "data": data}


def build_weekday_pattern(days: list) -> dict:
    """days: weekdays that have enough logs, as dicts with dow, n, avg_sleep."""
    title = "Best and worst day of the week"
    if len(days) < 2:
        return {"key": "weekday", "title": title, "status": "locked",
                "text": f"Not enough data yet: need at least 2 different weekdays with {MIN_PER_GROUP}+ check-ins each."}
    best = max(days, key=lambda d: float(d["avg_sleep"]))
    worst = min(days, key=lambda d: float(d["avg_sleep"]))
    return {
        "key": "weekday", "title": title, "status": "ready",
        "text": (f"You sleep the most on {DAY_NAMES[best['dow']]}s (avg {num(best['avg_sleep'])}h) "
                 f"and the least on {DAY_NAMES[worst['dow']]}s (avg {num(worst['avg_sleep'])}h)."),
        "data": {
            "best_day": DAY_NAMES[best["dow"]], "best_avg_sleep": num(best["avg_sleep"]),
            "worst_day": DAY_NAMES[worst["dow"]], "worst_avg_sleep": num(worst["avg_sleep"]),
        },
    }


def build_patterns(total: int, caf: dict, heat: dict, days: list) -> list:
    if total < MIN_LOGS_FOR_PATTERNS:
        text = f"Pattern insights unlock at {MIN_LOGS_FOR_PATTERNS} check-ins. You have {total}."
        return [
            {"key": k, "title": t, "status": "locked", "text": text}
            for k, t in (("caffeine", "Caffeine vs sleep quality"),
                         ("heat", "Hot days vs sleep"),
                         ("weekday", "Best and worst day of the week"))
        ]
    return [
        compare_groups(
            "caffeine", "Caffeine vs sleep quality",
            {"n": caf["high_n"], "avg": caf["high_avg"]}, {"n": caf["low_n"], "avg": caf["low_avg"]},
            f"{HIGH_CAFFEINE}+ coffee", "other", "/10",
        ),
        compare_groups(
            "heat", "Hot days vs sleep",
            {"n": heat["hot_n"], "avg": heat["hot_avg"]}, {"n": heat["cool_n"], "avg": heat["cool_avg"]},
            f"hot ({int(HOT_C)}°C+)", "cooler", "h",
        ),
        build_weekday_pattern(days),
    ]


@app.get("/api/insights")
def insights(user_id: str = Depends(get_current_user)):
    with db() as conn:
        total = conn.execute(
            "select count(*) as n from sleep_logs where user_id = %s", (user_id,)
        ).fetchone()["n"]

        last_logs = conn.execute(
            """select log_date, hours_slept, sleep_quality, study_hours, caffeine_cups,
                      calculated_sleep_debt, risk_level
               from sleep_logs where user_id = %s
               order by log_date desc limit %s""",
            (user_id, RECAP_LOGS),
        ).fetchall()

        # SQL aggregations: compare two groups of days with FILTER
        caf = conn.execute(
            """select count(*) filter (where caffeine_cups >= %s)  as high_n,
                      avg(sleep_quality) filter (where caffeine_cups >= %s) as high_avg,
                      count(*) filter (where caffeine_cups < %s)   as low_n,
                      avg(sleep_quality) filter (where caffeine_cups < %s)  as low_avg
               from sleep_logs
               where user_id = %s and sleep_quality is not null""",
            (HIGH_CAFFEINE, HIGH_CAFFEINE, HIGH_CAFFEINE, HIGH_CAFFEINE, user_id),
        ).fetchone()

        heat = conn.execute(
            """select count(*) filter (where temperature_c >= %s)  as hot_n,
                      avg(hours_slept) filter (where temperature_c >= %s) as hot_avg,
                      count(*) filter (where temperature_c < %s)   as cool_n,
                      avg(hours_slept) filter (where temperature_c < %s)  as cool_avg
               from sleep_logs
               where user_id = %s and temperature_c is not null""",
            (HOT_C, HOT_C, HOT_C, HOT_C, user_id),
        ).fetchone()

        days = conn.execute(
            """select extract(dow from log_date)::int as dow,
                      count(*) as n,
                      avg(hours_slept) as avg_sleep
               from sleep_logs where user_id = %s
               group by 1 having count(*) >= %s""",
            (user_id, MIN_PER_GROUP),
        ).fetchall()

    return {
        "total_logs": total,
        "recap": build_recap(last_logs),
        "patterns_unlock_at": MIN_LOGS_FOR_PATTERNS,
        "patterns": build_patterns(total, caf, heat, days),
    }


# =====================  FORECAST-AWARE BEDTIME  =====================
HOT_NIGHT_C = 28.0       # average evening temperature that counts as hot
HUMID_NIGHT_PCT = 80.0   # average evening humidity that counts as humid
MANILA_TZ = timezone(timedelta(hours=8))  # Davao uses Philippine time (UTC+8, no daylight saving)


def get_tonight_forecast():
    """Average forecast temperature and humidity for 9 to 11 PM tonight (Davao).
    Returns (avg_temp_c, avg_humidity_pct, live). live is False if the call failed."""
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 7.1907,
                "longitude": 125.4553,
                "hourly": "temperature_2m,relative_humidity_2m",
                "forecast_days": 2,
                "timezone": "Asia/Manila",
            },
            timeout=5,
        )
        r.raise_for_status()
        hourly = r.json()["hourly"]
        today = datetime.now(MANILA_TZ).strftime("%Y-%m-%d")
        wanted = {f"{today}T{hh}:00" for hh in ("21", "22", "23")}
        temps, hums = [], []
        for t, temp, hum in zip(
            hourly["time"], hourly["temperature_2m"], hourly["relative_humidity_2m"]
        ):
            if t in wanted and temp is not None and hum is not None:
                temps.append(temp)
                hums.append(hum)
        if not temps:
            return None, None, False
        return round(sum(temps) / len(temps), 1), round(sum(hums) / len(hums)), True
    except Exception:
        return None, None, False


def compute_bedtime(wake_time: str, target: float, debt: float, avg_temp, avg_humidity) -> dict:
    """Bedtime = wake time - sleep target - extra time for sleep debt - extra for a hot, humid night.
    These adjustments are simple heuristics, not medical rules."""
    h, m = map(int, wake_time.split(":"))
    wake_min = h * 60 + m
    debt_min = round(min(debt / 8, 1.0) * 60)   # up to 1 hour extra when the debt is large
    hot_humid = (
        avg_temp is not None
        and avg_humidity is not None
        and avg_temp >= HOT_NIGHT_C
        and avg_humidity >= HUMID_NIGHT_PCT
    )
    heat_min = 30 if hot_humid else 0           # hot, humid nights make it harder to fall asleep
    total_min = round(target * 60) + debt_min + heat_min
    bed_min = (wake_min - total_min) % 1440
    bed_min = (round(bed_min / 5) * 5) % 1440   # nearest 5 minutes
    return {
        "bedtime": f"{bed_min // 60:02d}:{bed_min % 60:02d}",
        "target_sleep_hours": target,
        "debt_adjustment_min": debt_min,
        "heat_adjustment_min": heat_min,
        "hot_humid_night": hot_humid,
    }


@app.get("/api/bedtime")
def bedtime(
    wake_time: str = Query("07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    user_id: str = Depends(get_current_user),
):
    """Recommended bedtime for tonight, based on the user's target, sleep debt and tonight's forecast."""
    with db() as conn:
        row = conn.execute(
            "select target_sleep_hours, calculated_sleep_debt from v_dashboard_today where user_id = %s",
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")

    target = float(row["target_sleep_hours"])
    debt = float(row["calculated_sleep_debt"] or 0)
    avg_temp, avg_humidity, live = get_tonight_forecast()
    plan = compute_bedtime(wake_time, target, debt, avg_temp, avg_humidity)

    reasons = []
    if plan["debt_adjustment_min"]:
        reasons.append(f"you owe {debt}h of sleep")
    if plan["hot_humid_night"]:
        reasons.append(f"tonight is hot and humid ({avg_temp} C, {avg_humidity}% humidity)")
    because = (" That is earlier because " + " and ".join(reasons) + ".") if reasons else ""
    message = f"Hmph. Be in bed by {plan['bedtime']} to wake up at {wake_time}.{because}"
    if not live:
        message += " (No live forecast, so I ignored the weather.)"

    return {
        **plan,
        "wake_time": wake_time,
        "sleep_debt_hours": debt,
        "forecast": {"avg_temp_c": avg_temp, "avg_humidity_pct": avg_humidity, "live": live, "window": "9-11 PM tonight"},
        "aura_message": message,
    }