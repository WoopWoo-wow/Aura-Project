# AURA: Adaptive User Routine & Accountability

A persona-driven behavioral analytics and student productivity app. It tracks sleep, focus and daily habits, finds patterns between them, and reacts through a strict-but-caring "tsundere" AI companion whose mood comes from your real data.

## Status
Work in progress.

- [x] PostgreSQL schema with triggers and a view (Neon)
- [x] FastAPI backend: `GET /api/dashboard`, `POST /api/sleep`
- [x] Sleep-debt and companion-mood triggers
- [ ] React frontend (Morning Check-In screen)
- [ ] Focus timer and distraction tracking
- [ ] Evening habits and streaks
- [ ] Gemini-powered companion dialogue
- [ ] Analytics hub and scikit-learn burnout model
- [ ] Authentication (JWT) and cloud deployment

## Tech Stack
| Layer | Tools |
|---|---|
| Database | PostgreSQL on Neon (triggers, views, PL/pgSQL) |
| Backend | Python, FastAPI, psycopg |
| Frontend | React, Vite, Tailwind CSS, Recharts (planned) |
| ML / AI | scikit-learn, Gemini API (planned) |

## How it works
1. A sleep log is sent to `POST /api/sleep`.
2. A database trigger calculates 7-day cumulative sleep debt.
3. A second trigger updates the companion's mood and affection points.
4. `GET /api/dashboard` returns the stats and a companion message based on the real numbers.

## Setup

### Database
1. Create a free project at [neon.com](https://neon.com).
2. Run `db/01_schema.sql` in the Neon SQL Editor.

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows PowerShell
pip install -r requirements.txt
```

Create `backend/.env`:
```
DATABASE_URL=your_neon_connection_string
```

Run:
```bash
uvicorn main:app --reload
```
Open http://localhost:8000/docs to test the API.

## Project Structure
```
backend/    FastAPI app
db/         SQL schema, triggers and views
frontend/   React app (coming soon)
```