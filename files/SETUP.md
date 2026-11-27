# AURA frontend base: setup (about 10 minutes)

You need Node.js installed (check with `node -v`). Recent Vite versions want Node 20.19+ or 22.12+.
The backend must be running (`uvicorn main:app --reload` in the backend folder).

## 1. Keep the old prototype, create the new app

From the project root (Productivity-Companion):

    Rename-Item frontend frontend-prototype
    npm create vite@latest frontend -- --template react
    cd frontend
    npm install
    npm install react-router-dom

If the Vite wizard asks questions, choose React with plain JavaScript, and answer No to
"install and start now".

## 2. Copy these files into the new frontend folder

- vite.config.js         replace the generated one
- .env.example           copy it to a new file named .env (do not commit .env)
- src/                   copy everything inside src over the generated src
                         (App.jsx, main.jsx, index.css are replaced; api, context,
                         components, pages and utils are new)
- Delete the leftovers you no longer need: src/App.css and the default images in src/assets.
- Optional: in frontend/index.html change the <title> to AURA.

## 3. Run it

    npm run dev

Open the address it prints (usually http://localhost:5173).

## 4. First-run checklist

1. Backend is running and http://127.0.0.1:8000/docs opens.
2. Click "Create an account", register, and you land on the dashboard.
3. Move the sliders, click "Analyze my day", and see the risk card and AURA's message change.
4. Refresh the page: you stay logged in (the token is saved in the browser).
5. Log out, then log in again with the same username and password.
6. Try the demo account: username demo, password demo12345 (after running seed_demo.py).

## Common problems

- "Cannot reach the server": the backend is not running, or VITE_API_URL in .env is wrong.
  After editing .env, stop and restart npm run dev.
- Blank page and red errors in the browser console (F12): send the first error line.
- Redirected back to login all the time: the token expired (24 hours) or JWT_SECRET changed.

## What is in this base

- Pages: login, register (with the onboarding fields), dashboard.
- AuthContext keeps the logged-in user; ProtectedRoute blocks the dashboard without login.
- src/api/client.js is the only file that talks to the backend. It already has functions for
  predict, whatif, recovery and insights, so Monday is mostly building screens.
- HashRouter and base './' in vite.config.js make it ready for GitHub Pages.

## Not built yet (next)

7-day chart, insights page (3-day recap and pattern cards), what-if sliders, recovery plan,
Gemini voice and audio, and the actual GitHub Pages deploy (the backend needs its own host).
