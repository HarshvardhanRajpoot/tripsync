from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


# ---------- User ----------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Trip ----------
class TripCreate(BaseModel):
    name: str
    destination: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    total_budget: float


class TripOut(BaseModel):
    id: int
    name: str
    destination: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    total_budget: float
    status: str
    invite_code: str
    created_by: int

    class Config:
        from_attributes = True


class JoinTripRequest(BaseModel):
    invite_code: str


# ---------- Preference ----------
class PreferenceCreate(BaseModel):
    interest_tags: list[str]
    pace: str
    must_see_places: Optional[str] = None


class PreferenceOut(BaseModel):
    id: int
    trip_member_id: int
    interest_tags: str
    pace: str
    must_see_places: Optional[str]

    class Config:
        from_attributes = True


class TripMemberPreferenceOut(BaseModel):
    """A trip member paired with their preference and basic user info, for the group view."""
    user_id: int
    user_name: str
    preference: Optional[PreferenceOut]


# ---------- Place ----------
class PlaceOut(BaseModel):
    id: int
    name: str
    category: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    estimated_cost: float
    rating: Optional[float]
    destination: str

    class Config:
        from_attributes = True


class TripMemberAdd(BaseModel):
    user_email: EmailStr
    budget_contribution: float = 0


class TripMemberOut(BaseModel):
    id: int
    trip_id: int
    user_id: int
    budget_contribution: float

    class Config:
        from_attributes = True
