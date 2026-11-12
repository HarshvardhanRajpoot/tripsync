"""
TripSync optimizer: pick the best set of places for a group within a budget
and a number of days, then spread them across days by location.

Pure Python, no database or FastAPI imports, so it can be unit-tested alone.

Pipeline
  1. score   -> how much does the GROUP like each place? (preferences + rating)
  2. select  -> best-scoring set that fits the budget and the daily-slot limit
                (exact 0/1 knapsack with a count limit; must-see places forced in)
  3. schedule-> order by proximity and cut into days

The same function is reused for re-planning: pass exclude_ids, the remaining
budget, and the remaining days.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---- Tunable constants ------------------------------------------------------
PLACES_PER_DAY = {"relaxed": 2, "moderate": 3, "packed": 4}
BUDGET_UNIT = 50            # rupees; costs are rounded UP to this unit for the DP
MUST_SEE_BONUS = 10.0       # large enough that a must-see always beats a normal pick
MEAN_WEIGHT, MIN_WEIGHT = 0.7, 0.3   # fairness blend: average liking vs least-happy member
RATING_WEIGHT = 0.3         # share of the final score that comes from Google rating
NEUTRAL_RATING = 3.5        # used when a place has no rating

# Preference tags (from the TripDetail UI) -> place categories (from places_service)
TAG_TO_CATEGORIES = {
    "food": {"food"},
    "culture": {"sightseeing"},
    "nature": {"sightseeing", "adventure"},
    "beach": {"sightseeing", "adventure"},
    "adventure": {"adventure"},
    "nightlife": {"food"},
    "shopping": {"sightseeing"},
}


@dataclass
class PlaceIn:
    id: int
    name: str
    category: str
    cost: float                      # per person, per visit
    rating: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


@dataclass
class MemberIn:
    name: str
    tags: list[str] = field(default_factory=list)
    pace: str = "moderate"
    must_see: list[str] = field(default_factory=list)   # free-text place names


@dataclass
class PlanItem:
    place_id: int
    name: str
    day: int
    order: int
    group_cost: float
    score: float
    reason: str


@dataclass
class Plan:
    items: list[PlanItem]
    total_cost: float
    budget: float
    remaining: float
    unmatched_must_sees: list[str]
    warnings: list[str]


# ---- 1. Scoring -------------------------------------------------------------
def _affinity(member: MemberIn, place: PlaceIn) -> float:
    """0..1: how well does this place match one member's interests?"""
    if not member.tags:
        return 0.5                                   # no preferences -> neutral
    cats = set()
    for tag in member.tags:
        cats |= TAG_TO_CATEGORIES.get(tag.strip().lower(), set())
    return 1.0 if place.category in cats else 0.0


def _is_must_see(place: PlaceIn, members: list[MemberIn]) -> bool:
    pname = place.name.lower()
    for m in members:
        for wanted in m.must_see:
            w = wanted.strip().lower()
            if w and (w in pname or pname in w):
                return True
    return False


def score_place(place: PlaceIn, members: list[MemberIn]) -> tuple[float, str]:
    affs = [_affinity(m, place) for m in members]
    group_pref = MEAN_WEIGHT * (sum(affs) / len(affs)) + MIN_WEIGHT * min(affs)
    rating = (place.rating if place.rating is not None else NEUTRAL_RATING) / 5.0
    score = (1 - RATING_WEIGHT) * group_pref + RATING_WEIGHT * rating
    liked_by = sum(1 for a in affs if a >= 1.0)
    reason = f"liked by {liked_by}/{len(members)} members"
    if place.rating is not None:
        reason += f", rated {place.rating:.1f}"
    return score, reason


# ---- 2. Selection (knapsack) ------------------------------------------------
def _knapsack(values: list[float], weights: list[int], cap: int, max_items: int) -> list[int]:
    """Best subset (indices) with total weight <= cap and at most max_items items."""
    n = len(values)
    if n == 0 or cap <= 0 or max_items <= 0:
        return []
    NEG = float("-inf")
    # dp[k][w] = best value using exactly k items and exactly weight w (or <= w via scan)
    dp = [[NEG] * (cap + 1) for _ in range(max_items + 1)]
    dp[0][0] = 0.0
    choice = [[[False] * (cap + 1) for _ in range(max_items + 1)] for _ in range(n)]
    for i in range(n):
        v, wt = values[i], weights[i]
        for k in range(min(max_items, i + 1), 0, -1):
            row, prev = dp[k], dp[k - 1]
            for w in range(cap, wt - 1, -1):
                cand = prev[w - wt] + v
                if cand > row[w]:
                    row[w] = cand
                    choice[i][k][w] = True
    best, bk, bw = 0.0, 0, 0
    for k in range(max_items + 1):
        for w in range(cap + 1):
            if dp[k][w] > best:
                best, bk, bw = dp[k][w], k, w
    picked, k, w = [], bk, bw
    for i in range(n - 1, -1, -1):
        if k > 0 and choice[i][k][w]:
            picked.append(i)
            w -= weights[i]
            k -= 1
    return picked


# ---- 3. Scheduling ----------------------------------------------------------
def _dist(a: PlaceIn, b: PlaceIn) -> float:
    if None in (a.lat, a.lng, b.lat, b.lng):
        return 0.0
    # equirectangular approximation, fine at city scale (km)
    x = math.radians(b.lng - a.lng) * math.cos(math.radians((a.lat + b.lat) / 2))
    y = math.radians(b.lat - a.lat)
    return 6371 * math.hypot(x, y)


def _order_by_proximity(places: list[PlaceIn]) -> list[PlaceIn]:
    if len(places) <= 2:
        return places
    # start from the place farthest from the centroid, then nearest-neighbour chain
    located = [p for p in places if p.lat is not None and p.lng is not None]
    unlocated = [p for p in places if p not in located]
    if not located:
        return places
    clat = sum(p.lat for p in located) / len(located)
    clng = sum(p.lng for p in located) / len(located)
    centre = PlaceIn(0, "", "", 0, lat=clat, lng=clng)
    current = max(located, key=lambda p: _dist(centre, p))
    ordered, rest = [current], [p for p in located if p is not current]
    while rest:
        current = min(rest, key=lambda p: _dist(ordered[-1], p))
        ordered.append(current)
        rest.remove(current)
    return ordered + unlocated


# ---- Public entry point -----------------------------------------------------
def optimize(
    places: list[PlaceIn],
    members: list[MemberIn],
    budget: float,
    days: int,
    start_day: int = 1,
    exclude_ids: Optional[set[int]] = None,
) -> Plan:
    """
    budget : total rupees available for activities, for the WHOLE group.
    days   : number of days to fill.
    start_day / exclude_ids : used by re-planning (continue from day N,
             skip places that are closed / already done).
    """
    exclude_ids = exclude_ids or set()
    warnings: list[str] = []
    n_members = max(len(members), 1)
    if not members:
        members = [MemberIn(name="(no preferences yet)")]
        warnings.append("No preferences saved yet; scoring on ratings only.")

    # group pace = rounded average of everyone's slots per day
    slots_pd = round(sum(PLACES_PER_DAY.get(m.pace, 3) for m in members) / len(members))
    max_items = max(days, 0) * slots_pd

    pool = [p for p in places if p.id not in exclude_ids]
    scored = []
    for p in pool:
        s, reason = score_place(p, members)
        must = _is_must_see(p, members)
        group_cost = p.cost * n_members
        scored.append({"p": p, "score": s + (MUST_SEE_BONUS if must else 0), "base": s,
                       "must": must, "cost": group_cost, "reason": reason + (", must-see" if must else "")})

    # must-sees first (cheapest first if they can't all fit)
    chosen, spent = [], 0.0
    for row in sorted((r for r in scored if r["must"]), key=lambda r: r["cost"]):
        if spent + row["cost"] <= budget and len(chosen) < max_items:
            chosen.append(row)
            spent += row["cost"]
        else:
            warnings.append(f"Must-see '{row['p'].name}' doesn't fit the budget/day limit.")
    matched = {r["p"].name.lower() for r in scored if r["must"]}
    unmatched = [w.strip() for m in members for w in m.must_see
                 if w.strip() and not any(w.strip().lower() in n or n in w.strip().lower() for n in matched)]

    # fill the rest optimally
    rest = [r for r in scored if not r["must"]]
    cap = int((budget - spent) // BUDGET_UNIT)
    weights = [max(1, math.ceil(r["cost"] / BUDGET_UNIT)) for r in rest]
    picked = _knapsack([r["base"] for r in rest], weights, cap, max_items - len(chosen))
    chosen += [rest[i] for i in picked]

    if len(chosen) < max_items and chosen:
        warnings.append(f"Only {len(chosen)} of {max_items} slots filled (budget or places ran out).")

    # schedule
    by_place = {r["p"].id: r for r in chosen}
    ordered = _order_by_proximity([r["p"] for r in chosen])
    items = []
    for idx, p in enumerate(ordered):
        day = start_day + idx // slots_pd if slots_pd else start_day
        if day >= start_day + days:
            day = start_day + days - 1
        r = by_place[p.id]
        items.append(PlanItem(p.id, p.name, day, idx % slots_pd, r["cost"], round(r["base"], 3), r["reason"]))
    # fix order_in_day to restart per day
    counters: dict[int, int] = {}
    for it in items:
        it.order = counters.get(it.day, 0)
        counters[it.day] = it.order + 1

    total = sum(i.group_cost for i in items)
    return Plan(items, total, budget, budget - total, unmatched, warnings)
