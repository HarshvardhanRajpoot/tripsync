"""
AI trip planner endpoints. Hooked into main.py with:

    import routes_ai
    app.include_router(routes_ai.router)

POST /api/trips/{id}/ai-plan  -> retrieve relevant places, optimize, write the plan with Gemini
GET  /api/trips/{id}/ai-plan  -> the last saved AI plan for the trip
"""
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import ai_planner
import auth
import budget_breakdown
import destination_places
import models
from database import get_db
from optimizer import optimize, PlaceIn, MemberIn, PLACES_PER_DAY, _is_must_see
from routes_optimizer import _require_member, DEFAULT_DAYS

router = APIRouter()

MAX_NEW_EMBEDDINGS = 40   # places embedded per request; the rest are done on later requests
MIN_RETRIEVED = 5         # fewer than this and retrieval isn't useful: use all places


class AIPlanRequest(BaseModel):
    request: Optional[str] = Field(None, max_length=ai_planner.MAX_REQUEST_CHARS)
    days: Optional[int] = Field(None, ge=1, le=14)
    activity_budget: Optional[float] = Field(None, gt=0)   # overrides the activities share of the breakdown
    budget_style: Literal["budget", "balanced", "comfort"] = "balanced"


def _members(trip_id: int, db: Session) -> list[MemberIn]:
    out = []
    for tm in db.query(models.TripMember).filter(models.TripMember.trip_id == trip_id).all():
        pref = tm.preference
        out.append(MemberIn(
            name=tm.user.name,
            tags=[t for t in (pref.interest_tags or "").split(",") if t] if pref else [],
            pace=(pref.pace if pref and pref.pace else "moderate"),
            must_see=[s for s in (pref.must_see_places or "").replace("\n", ",").split(",") if s.strip()] if pref else [],
        ))
    return out


def _to_place_in(p: models.Place) -> PlaceIn:
    return PlaceIn(p.id, p.name, p.category or "", p.estimated_cost or 0, p.rating, p.latitude, p.longitude)


def _ensure_embeddings(db: Session, places: list[models.Place], destination: str) -> None:
    """Embed places that don't have an embedding yet (a limited batch per request)."""
    missing = [p for p in places if p.embedding is None][:MAX_NEW_EMBEDDINGS]
    if not missing:
        return
    need_desc = [p for p in missing if p.description is None]
    if need_desc:
        found = ai_planner.fetch_descriptions([(p.name, destination) for p in need_desc])
        for p, text in zip(need_desc, found):
            p.description = text           # "" is stored when nothing was found, so we don't retry
    texts = [ai_planner.place_text(p.name, p.category, destination, p.description, p.rating) for p in missing]
    vectors = ai_planner.embed_texts(texts, "RETRIEVAL_DOCUMENT")
    for p, vec in zip(missing, vectors):
        p.embedding = vec
    db.commit()


def _retrieve(db: Session, places: list[models.Place], trip: models.Trip,
              members: list[MemberIn], request: Optional[str], k: int) -> list[models.Place]:
    """Top-k places for this group by embedding similarity (raises AIUnavailable on failure)."""
    _ensure_embeddings(db, places, trip.destination)
    query = ai_planner.build_query_text(
        trip.destination,
        [{"tags": m.tags, "pace": m.pace} for m in members],
        request,
    )
    qvec = ai_planner.embed_texts([query], "RETRIEVAL_QUERY")[0]
    return (db.query(models.Place)
            .filter(models.Place.destination == trip.destination, models.Place.embedding.isnot(None))
            .order_by(models.Place.embedding.cosine_distance(qvec))
            .limit(k).all())


@router.post("/api/trips/{trip_id}/ai-plan")
def generate_ai_plan(trip_id: int, req: AIPlanRequest = AIPlanRequest(),
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

    members = _members(trip_id, db)
    # split the whole budget (travel / stay / food / activities / buffer); the optimizer
    # only spends the activities share on places
    breakdown = budget_breakdown.compute_breakdown(trip.total_budget, days, len(members), req.budget_style)
    budget = req.activity_budget if req.activity_budget is not None else breakdown["activities_amount"]

    warnings: list[str] = []
    places = db.query(models.Place).filter(models.Place.destination == trip.destination).all()
    if not places:
        # new destination: fill the places table from OpenStreetMap / Wikipedia (no API key needed)
        try:
            info = destination_places.ensure_places(db, trip.destination)
        except destination_places.PlacesUnavailable as e:
            raise HTTPException(status_code=502, detail=f"Couldn't find places for '{trip.destination}': {e}")
        places = db.query(models.Place).filter(models.Place.destination == trip.destination).all()
        warnings.append(f"Found {info['created']} places for {trip.destination} from {info['source']}. "
                        "Costs are rough estimates, not real prices.")
        warnings += [f"Note: {n}." for n in info["notes"]]

    # 1. RETRIEVE: shortlist the places most relevant to this group and request
    slots = max(PLACES_PER_DAY.values())
    k = min(len(places), max(20, days * slots * 3))
    candidates, retrieval_used = places, False
    try:
        top = _retrieve(db, places, trip, members, req.request, k)
        if len(top) >= MIN_RETRIEVED:
            ids = {p.id for p in top}
            # must-see places named by members always stay in the pool
            extra = [p for p in places if p.id not in ids and _is_must_see(_to_place_in(p), members)]
            candidates, retrieval_used = top + extra, True
    except ai_planner.AIUnavailable as e:
        warnings.append(f"Smart search unavailable, used all places instead ({e}).")

    # 2. OPTIMIZE: budget + days + group fairness (the tested knapsack in optimizer.py)
    plan = optimize([_to_place_in(p) for p in candidates], members, budget=budget, days=days)
    warnings += plan.warnings
    by_id = {p.id: p for p in places}
    plan_items = [{
        "place_id": i.place_id, "name": i.name, "category": by_id[i.place_id].category,
        "day": i.day, "order": i.order, "cost": i.group_cost, "reason": i.reason,
        "about": (by_id[i.place_id].description or "")[:200],
    } for i in plan.items]

    # save the itinerary the same way /optimize does (keeps completed/skipped history)
    db.query(models.ItineraryItem).filter(
        models.ItineraryItem.trip_id == trip_id, models.ItineraryItem.status == "planned"
    ).delete()
    for it in plan.items:
        db.add(models.ItineraryItem(trip_id=trip_id, place_id=it.place_id, day_number=it.day,
                                    order_in_day=it.order, estimated_cost=it.group_cost,
                                    score=it.score, status="planned"))

    # 3. GENERATE: the LLM writes the text; if it fails we still return the optimizer's plan
    narrative, ai_used = None, False
    if plan_items:
        system, user = ai_planner.build_prompt(
            trip.name, trip.destination, days, budget, plan.total_cost,
            [{"name": m.name, "tags": m.tags, "pace": m.pace} for m in members],
            req.request, plan_items,
        )
        try:
            narrative = ai_planner.generate_narrative(system, user)
            ai_used = True
        except ai_planner.AIUnavailable as e:
            warnings.append(f"AI text unavailable, showing the optimizer's plan only ({e}).")

    result = {
        "trip_id": trip_id,
        "summary": narrative.summary if narrative else "",
        "budget_note": narrative.budget_note if narrative else "",
        "days": ai_planner.assemble_days(plan_items, narrative),
        "budget": {"activity_budget": plan.budget, "total_cost": plan.total_cost, "remaining": plan.remaining},
        "breakdown": breakdown,
        "unmatched_must_sees": plan.unmatched_must_sees,
        "warnings": warnings,
        "ai_used": ai_used,
        "retrieval_used": retrieval_used,
    }
    db.add(models.AiPlan(trip_id=trip_id, user_id=current_user.id, request=req.request,
                         content=json.dumps(result)))
    db.commit()
    return result


@router.get("/api/trips/{trip_id}/ai-plan")
def get_latest_ai_plan(trip_id: int, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_user)):
    _require_member(trip_id, current_user.id, db)
    row = (db.query(models.AiPlan).filter(models.AiPlan.trip_id == trip_id)
           .order_by(models.AiPlan.id.desc()).first())
    if not row:
        raise HTTPException(status_code=404, detail="No AI plan yet")
    return json.loads(row.content)
