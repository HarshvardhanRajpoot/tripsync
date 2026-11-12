# TripSync

AI-powered collaborative travel planner with budget optimization and adaptive re-planning.

## Project structure
```
tripsync/
├── backend/     FastAPI + PostgreSQL API
└── frontend/    React (Vite) UI
```

## Step 1 — Run the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate       # on Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at http://localhost:8000
Check it works by opening http://localhost:8000/api/health in your browser — you should see `{"status": "ok"}`.

## Step 2 — Run the frontend

Open a **second terminal** (keep the backend running in the first one):

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173

Open it in your browser — you should see "Backend connection status: ok". If it says "backend not reachable", make sure the backend terminal is still running.

## What's next

- [ ] Set up PostgreSQL and connect it using `.env` (copy `.env.example` to `.env` and fill in your DB URL)
- [ ] Build the database tables from the schema (User, Trip, TripMember, Preference, Place, ItineraryItem, Expense)
- [ ] Add signup/login
- [ ] Build trip creation
- [ ] Build the optimizer

## Team
Harsh Vardhan Singh Rajpoot, Atharva Dwivedi — SATI Vidisha, B.Tech CSE/IT
