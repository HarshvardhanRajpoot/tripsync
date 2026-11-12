# Adding auth to TripSync — setup steps

## 1. Copy files in
Copy these 4 files into your `backend/` folder, next to your existing
`main.py`, `models.py`, `database.py`:

- `auth.py` (new)
- `schemas.py` (new)
- `dependencies.py` (new)
- `main.py` (**replaces** your existing one — it keeps your old
  `/` and `/api/health` routes and adds the new auth + trip routes)

## 2. Install the 3 new packages
With your venv activated:

```powershell
pip install python-jose[cryptography]==3.3.0 passlib[bcrypt]==1.7.4 email-validator==2.2.0
```

(Also add those 3 lines to your `requirements.txt` so Atharva's install
stays in sync — the exact lines are in `requirements-additions.txt`.)

## 3. Add a JWT secret to `.env`
Open your `backend/.env` (same file with `DATABASE_URL`) and add a new line:

```
JWT_SECRET_KEY=any-long-random-string-you-make-up-right-now
```

This is the key that signs login tokens — keep it out of GitHub (it
should already be covered by your `.gitignore` since `.env` is in there).

## 4. Restart the server
```powershell
uvicorn main:app --reload
```

## 5. Test it — open http://localhost:8000/docs
FastAPI auto-generates an interactive test page. Try it in this order:

1. **POST /api/auth/signup** → click "Try it out", fill in name/email/password, Execute.
   You should get back a `201` with an `access_token` and your user info.
2. **POST /api/auth/login** → same email/password, Execute. You should get
   another `access_token` back.
3. **GET /api/auth/me** → click the padlock icon (top right of the page or
   next to this endpoint), paste in just the token value (no "Bearer"
   prefix needed, the docs page adds it), Authorize, then Execute. It
   should return your own user info — this proves the token works.
4. **POST /api/trips** → with the padlock still authorized, fill in name/
   destination/start_date/end_date/total_budget, Execute. You should get
   back the created trip.
5. **GET /api/trips** → Execute, should return a list containing the trip
   you just made.

If any step 401s, the token either wasn't pasted in or `JWT_SECRET_KEY`
is missing from `.env` — restart the server after adding it.

## What each new file does
- `auth.py` — hashes passwords (bcrypt) so plain-text passwords never
  touch the database, and creates/verifies JWT tokens for login sessions.
- `schemas.py` — defines exactly what JSON your API accepts and returns,
  so a password hash can never accidentally leak back to the frontend.
- `dependencies.py` — the `get_current_user` function every protected
  endpoint uses to figure out "who sent this request" from their token.
- `main.py` — wires it together: signup, login, "who am I", create trip,
  list my trips.

## Next
Once this works end-to-end from the `/docs` page, the next step is
wiring your **React frontend** to call these — a signup/login form that
stores the token, and a "create trip" form. Say the word when you're
ready for that.
