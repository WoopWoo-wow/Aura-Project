# AURA: Student Burnout and Sleep Companion

AURA is a web app that helps students notice burnout early. Each day a student logs a short
check-in (sleep, sleep quality, study hours, screen time, caffeine). The backend adds the live
Davao City weather, a machine learning model predicts burnout risk, and AURA, a tsundere
persona, reacts. The warmer or colder her tone depends on affection points, which grow when a
student's honest logs look healthy. The app also explains the risk, simulates "what if" changes,
estimates a sleep recovery plan, recommends tonight's bedtime from the weather forecast, and
shows personal patterns from the student's own logs.

Course: Integrated IT Project (Full Stack Web Development, Systems Integration and Architecture,
Advanced Database Systems, Application Development and Emerging Technologies).
SDG alignment: SDG 3, Good Health and Well-being.

## Tech stack

| Part | Technology |
|---|---|
| Frontend | React, Vite, React Router |
| Backend / custom API | Python, FastAPI, Uvicorn |
| Operational database | PostgreSQL on Neon (psycopg) |
| Machine learning | scikit-learn (Random Forest), pandas, joblib |
| External API | Open-Meteo (weather and forecast) |
| Security | bcrypt password hashing, JWT login tokens, secrets in .env |

## Project structure

```
backend/     FastAPI app (main.py), model file, seed_demo.py, requirements.txt, .env.example
csv/         dataset, train_model.py, compare_models.py, experiments
db/          SQL scripts (run in order)
frontend/    React app
frontend-prototype/   old single-file prototype (design reference only)
docs/        diagrams (warehouse star schema)
```

## Setup (first time)

Requirements: Python 3.11 or newer, Node.js (Vite needs 20.19+ or 22.12+), a free Neon database.

### 1. Database
1. Create a Neon project and copy its connection string.
2. In the Neon SQL editor, run these files in order:
   `db/01_schema.sql`, then `db/02_auth.sql`, then `db/03_insights_columns.sql`.

### 2. Backend
```
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Copy `.env.example` to a new file named `.env` and fill in the values:
```
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
JWT_SECRET=<a long random string>
```
Generate a secret with: `python -c "import secrets; print(secrets.token_hex(32))"`
Never commit `.env`. Each teammate uses their own `.venv` and `.env`.

The trained model `burnout_model.pkl` must be inside `backend/`. To rebuild it:
```
cd csv
python train_model.py
copy burnout_model.pkl ..\backend\burnout_model.pkl
```

### 3. Frontend
```
cd frontend
npm install
```
Create `frontend/.env` with one line:
```
VITE_API_URL=http://127.0.0.1:8000
```

## Run the app (two terminals)

Terminal 1, backend:
```
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```
API documentation and testing page: http://127.0.0.1:8000/docs

Terminal 2, frontend:
```
cd frontend
npm run dev
```
Open http://localhost:5173. Check that the prompt ends in the right folder before each command.
After changing a `.env` file, stop the server (Ctrl + C) and start it again.

## Demo account (synthetic data)

From the `backend` folder, with the `.venv` active:
```
python seed_demo.py
```
Log in with username `demo` and password `demo12345`. The 14 days of check-ins are generated
for demonstration. They are synthetic, not real observations.

## API overview

All endpoints except register and login need a login token (`Authorization: Bearer <token>`).

| Endpoint | Purpose |
|---|---|
| POST /api/auth/register, POST /api/auth/login | Create account, log in |
| GET /api/me | Current user |
| GET /api/dashboard | Today's state, mood, affection, last 7 days |
| POST /api/checkin | Save the daily check-in, run the model, return risk, reasons and AURA's message |
| POST /api/predict | Risk only, nothing saved |
| POST /api/whatif | Re-run the model with changed inputs |
| GET /api/recovery | Nights of extra sleep needed to clear sleep debt |
| GET /api/insights | 3-day recap and personal pattern cards (unlock at 7 check-ins) |
| GET /api/bedtime | Recommended bedtime from wake time, sleep debt and tonight's forecast |
| POST /api/sleep | Older, smaller version of check-in |

## Machine learning

- Data: a public 500-row student sleep dataset in `csv/student_sleep_patterns.csv`
  (add the source link and license here).
- The dataset has no real burnout column, so the label is built from simple rules in
  `csv/train_model.py`, and the training temperature is simulated.
- `csv/compare_models.py` compares Logistic Regression, Decision Tree and Random Forest with
  5-fold cross-validation and writes `csv/model_comparison.txt`.
- Current results: Random Forest and Decision Tree F1 about 0.91, Logistic Regression 0.81,
  baseline 0.23. High-risk recall on the test split is 0.74 (improvement planned).

## Known limitations

- The model learns the rules used to create the label, so scores show how well it learns those
  rules, not real-world burnout prediction.
- Check-ins are self-reported. Weather and bedtime adjustments are simple heuristics.
- Demo data and the training temperature are synthetic.
- The app runs locally; public hosting is not set up.

## Planned work

Data warehouse (star schema in `docs/aura-star-schema.drawio`) and ETL with data quality checks,
algorithm improvement experiment, unit, integration and load tests, code inspection record,
Build vs Adopt matrix, architecture diagram, optional Gemini persona and voice.

## Team and contributions

Add each member's name, role and main contributions here. Git history shows individual commits.

## Credits and licenses

List the dataset source, libraries (FastAPI, scikit-learn, React, Vite and others) and the
Open-Meteo API with their licenses and attribution requirements.
