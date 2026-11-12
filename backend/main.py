import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import places_service
import routes_optimizer
import routes_explore

app = FastAPI(title="TripSync API")

app.include_router(routes_optimizer.router)
app.include_router(routes_explore.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "TripSync API is running"}


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/signup", response_model=schemas.UserOut)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        name=user.name,
        email=user.email,
        password_hash=auth.hash_password(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/api/auth/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not auth.verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = auth.create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


from fastapi.security import OAuth2PasswordRequestForm


@app.post("/api/auth/token", response_model=schemas.Token, include_in_schema=False)
def login_for_docs(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not auth.verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": auth.create_access_token({"sub": str(user.id)}), "token_type": "bearer"}


@app.get("/api/auth/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    """Confirms who you are based on your login token."""
    return current_user


# ---------------------------------------------------------------------------
# Trip endpoints
# ---------------------------------------------------------------------------

@app.post("/api/trips", response_model=schemas.TripOut)
def create_trip(
    trip: schemas.TripCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    new_trip = models.Trip(
        name=trip.name,
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        total_budget=trip.total_budget,
        invite_code=secrets.token_hex(4).upper(),  # e.g. "A1B2C3D4"
        created_by=current_user.id,
    )
    db.add(new_trip)
    db.commit()
    db.refresh(new_trip)

    membership = models.TripMember(
        trip_id=new_trip.id,
        user_id=current_user.id,
        budget_contribution=0,
    )
    db.add(membership)
    db.commit()

    return new_trip


@app.get("/api/trips", response_model=list[schemas.TripOut])
def list_my_trips(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    memberships = (
        db.query(models.TripMember)
        .filter(models.TripMember.user_id == current_user.id)
        .all()
    )
    trip_ids = [m.trip_id for m in memberships]
    return db.query(models.Trip).filter(models.Trip.id.in_(trip_ids)).all()


@app.get("/api/trips/{trip_id}", response_model=schemas.TripOut)
def get_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@app.post("/api/trips/{trip_id}/members", response_model=schemas.TripMemberOut)
def add_trip_member(
    trip_id: int,
    member: schemas.TripMemberAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    user_to_add = db.query(models.User).filter(models.User.email == member.user_email).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User with that email not found")

    existing = (
        db.query(models.TripMember)
        .filter(models.TripMember.trip_id == trip_id, models.TripMember.user_id == user_to_add.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this trip")

    new_member = models.TripMember(
        trip_id=trip_id,
        user_id=user_to_add.id,
        budget_contribution=member.budget_contribution,
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member


@app.post("/api/trips/join", response_model=schemas.TripOut)
def join_trip_by_code(
    payload: schemas.JoinTripRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Anyone with a valid invite code can join that trip themselves."""
    trip = (
        db.query(models.Trip)
        .filter(models.Trip.invite_code == payload.invite_code.strip().upper())
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    existing = (
        db.query(models.TripMember)
        .filter(models.TripMember.trip_id == trip.id, models.TripMember.user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="You're already a member of this trip")

    new_member = models.TripMember(
        trip_id=trip.id,
        user_id=current_user.id,
        budget_contribution=0,
    )
    db.add(new_member)
    db.commit()

    return trip


# ---------------------------------------------------------------------------
# Preference endpoints
# ---------------------------------------------------------------------------

def _get_or_404_trip_member(trip_id: int, user_id: int, db: Session) -> models.TripMember:
    member = (
        db.query(models.TripMember)
        .filter(models.TripMember.trip_id == trip_id, models.TripMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this trip")
    return member


@app.post("/api/trips/{trip_id}/preferences", response_model=schemas.PreferenceOut)
def set_my_preference(
    trip_id: int,
    pref: schemas.PreferenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Create or update the current user's preference for this trip (upsert)."""
    member = _get_or_404_trip_member(trip_id, current_user.id, db)

    existing = (
        db.query(models.Preference)
        .filter(models.Preference.trip_member_id == member.id)
        .first()
    )

    tags_str = ",".join(tag.strip() for tag in pref.interest_tags if tag.strip())

    if existing:
        existing.interest_tags = tags_str
        existing.pace = pref.pace
        existing.must_see_places = pref.must_see_places
        db.commit()
        db.refresh(existing)
        return existing

    new_pref = models.Preference(
        trip_member_id=member.id,
        interest_tags=tags_str,
        pace=pref.pace,
        must_see_places=pref.must_see_places,
    )
    db.add(new_pref)
    db.commit()
    db.refresh(new_pref)
    return new_pref


@app.get("/api/trips/{trip_id}/preferences", response_model=list[schemas.TripMemberPreferenceOut])
def list_trip_preferences(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Returns every member of this trip and their preference (if set yet)."""
    _get_or_404_trip_member(trip_id, current_user.id, db)  # confirm caller is a member

    members = db.query(models.TripMember).filter(models.TripMember.trip_id == trip_id).all()
    result = []
    for m in members:
        user = db.query(models.User).filter(models.User.id == m.user_id).first()
        pref = db.query(models.Preference).filter(models.Preference.trip_member_id == m.id).first()
        result.append(
            schemas.TripMemberPreferenceOut(
                user_id=user.id,
                user_name=user.name,
                preference=pref,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Places endpoints
# ---------------------------------------------------------------------------

@app.post("/api/trips/{trip_id}/places/refresh")
def refresh_places(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetches real places for this trip's destination from Google Places
    and caches them. Safe to call more than once — already-cached places
    are skipped, not duplicated.
    """
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    try:
        summary = places_service.fetch_and_cache_places(trip.destination, db)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return summary


@app.get("/api/trips/{trip_id}/places", response_model=list[schemas.PlaceOut])
def list_places_for_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Returns whatever places are already cached for this trip's destination."""
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    return db.query(models.Place).filter(models.Place.destination == trip.destination).all()
