"""
Optimizer endpoints. Hook into main.py with two lines:

    import routes_optimizer
    app.include_router(routes_optimizer.router)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from optimizer import optimize, PlaceIn, MemberIn

router = APIRouter()

DEFAULT_DAYS = 3
ACTIVITY_BUDGET_FRACTION = 0.5   # share of total_budget spent on places (rest: stay, travel)


class OptimizeRequest(BaseModel):
    days: Optional[int] = None              # defaults to trip dates, else 3
    activity_budget: Optional[float] = None  # defaults to 50% of trip budget


def _require_member(trip_id: int, user_id: int, db: Session):
    m = (db.query(models.TripMember)
         .filter(models.TripMember.trip_id == trip_id, models.TripMember.user_id == user_id)
         .first())
    if not m:
        raise HTTPException(status_code=403, detail="You are not a member of this trip")


def _item_dict(it: models.ItineraryItem):
    return {"id": it.id, "place_id": it.place_id, "name": it.place.name, "category": it.place.category,
            "day": it.day_number, "order": it.order_in_day, "cost": it.estimated_cost,
            "score": it.score, "status": it.status}


@router.post("/api/trips/{trip_id}/optimize")
def run_optimizer(trip_id: int, req: OptimizeRequest = OptimizeRequest(),
                  db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_user)):
    _require_member(trip_id, current_user.id, db)
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    days = req.days
    if days is None:
        if trip.start_date and trip.end_date:
            days = max((trip.end_date - trip.start_date).days + 1, 1)
        else:
            days = DEFAULT_DAYS
    budget = req.activity_budget if req.activity_budget is not None else trip.total_budget * ACTIVITY_BUDGET_FRACTION

    places = db.query(models.Place).filter(models.Place.destination == trip.destination).all()
    if not places:
        raise HTTPException(status_code=400, detail="No places for this destination yet. Refresh or seed places first.")

    members = []
    for tm in db.query(models.TripMember).filter(models.TripMember.trip_id == trip_id).all():
        pref = tm.preference
        members.append(MemberIn(
            name=tm.user.name,
            tags=[t for t in (pref.interest_tags or "").split(",") if t] if pref else [],
            pace=(pref.pace if pref and pref.pace else "moderate"),
            must_see=[s for s in (pref.must_see_places or "").replace("\n", ",").split(",") if s.strip()] if pref else [],
        ))

    plan = optimize(
        [PlaceIn(p.id, p.name, p.category or "", p.estimated_cost or 0, p.rating, p.latitude, p.longitude)
         for p in places],
        members, budget=budget, days=days,
    )

    # replace the previous plan (keep completed/skipped history untouched)
    db.query(models.ItineraryItem).filter(
        models.ItineraryItem.trip_id == trip_id, models.ItineraryItem.status == "planned"
    ).delete()
    for it in plan.items:
        db.add(models.ItineraryItem(trip_id=trip_id, place_id=it.place_id, day_number=it.day,
                                    order_in_day=it.order, estimated_cost=it.group_cost,
                                    score=it.score, status="planned"))
    db.commit()

    return {
        "days": days, "budget": plan.budget, "total_cost": plan.total_cost, "remaining": plan.remaining,
        "unmatched_must_sees": plan.unmatched_must_sees, "warnings": plan.warnings,
        "items": [{"place_id": i.place_id, "name": i.name, "day": i.day, "order": i.order,
                   "cost": i.group_cost, "score": i.score, "reason": i.reason} for i in plan.items],
    }


@router.get("/api/trips/{trip_id}/itinerary")
def get_itinerary(trip_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_user)):
    _require_member(trip_id, current_user.id, db)
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    items = (db.query(models.ItineraryItem).filter(models.ItineraryItem.trip_id == trip_id)
             .order_by(models.ItineraryItem.day_number, models.ItineraryItem.order_in_day).all())
    spent = sum(i.estimated_cost for i in items if i.status != "skipped")
    return {"total_budget": trip.total_budget, "planned_cost": spent,
            "items": [_item_dict(i) for i in items]}
