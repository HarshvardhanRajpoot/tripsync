from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    trip_memberships = relationship("TripMember", back_populates="user")


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    total_budget = Column(Float, nullable=False)
    status = Column(String, default="planning")  # planning / confirmed / ongoing / completed
    invite_code = Column(String, unique=True, index=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("TripMember", back_populates="trip")
    itinerary_items = relationship("ItineraryItem", back_populates="trip")
    expenses = relationship("Expense", back_populates="trip")


class TripMember(Base):
    __tablename__ = "trip_members"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    budget_contribution = Column(Float, default=0)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    trip = relationship("Trip", back_populates="members")
    user = relationship("User", back_populates="trip_memberships")
    preference = relationship("Preference", back_populates="trip_member", uselist=False)


class Preference(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, index=True)
    trip_member_id = Column(Integer, ForeignKey("trip_members.id"), nullable=False)
    interest_tags = Column(String)  # comma-separated for now, e.g. "beach,food,culture"
    pace = Column(String)  # "relaxed" / "moderate" / "packed"
    must_see_places = Column(Text, nullable=True)

    trip_member = relationship("TripMember", back_populates="preference")


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    google_place_id = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=False)
    category = Column(String)  # food / sightseeing / adventure / etc.
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    estimated_cost = Column(Float, default=0)
    rating = Column(Float, nullable=True)
    destination = Column(String, index=True)  # which city this place belongs to
    description = Column(Text, nullable=True)  # short text used for AI search ("" = looked up, none found)
    embedding = Column(Vector(768), nullable=True)  # pgvector embedding used by the AI planner

    itinerary_items = relationship("ItineraryItem", back_populates="place")


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    place_id = Column(Integer, ForeignKey("places.id"), nullable=False)
    day_number = Column(Integer, nullable=False)
    order_in_day = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0)
    score = Column(Float, nullable=True)  # why the optimizer picked this
    status = Column(String, default="planned")  # planned / completed / skipped / replaced

    trip = relationship("Trip", back_populates="itinerary_items")
    place = relationship("Place", back_populates="itinerary_items")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    paid_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    trip = relationship("Trip", back_populates="expenses")


class AiPlan(Base):
    """The last AI-generated plan for a trip, so it is still there after a page reload."""
    __tablename__ = "ai_plans"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    request = Column(Text, nullable=True)   # the group's free-text wish
    content = Column(Text, nullable=False)  # the plan as JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())
