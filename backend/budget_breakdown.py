"""
Splits a trip's total budget into travel, stay, food, activities and a buffer.

Pure and simple on purpose: fixed percentage splits (three styles), then a few
derived "per person / per night" figures. These are ESTIMATES. There is no free
source of real prices, so the page labels them as rough guides, and the
thresholds below that trigger warnings are rough guides too.

The activities amount is what the optimizer spends on places; everything here
is calculated by code, never by the AI.
"""
from __future__ import annotations

import math

STYLES = {
    "budget":   {"label": "Budget-friendly", "split": {"travel": 30, "stay": 25, "food": 22, "activities": 15, "buffer": 8}},
    "balanced": {"label": "Balanced",        "split": {"travel": 25, "stay": 30, "food": 20, "activities": 20, "buffer": 5}},
    "comfort":  {"label": "Comfortable",     "split": {"travel": 20, "stay": 35, "food": 20, "activities": 20, "buffer": 5}},
}
LABELS = {"travel": "Travel", "stay": "Stay", "food": "Food", "activities": "Activities", "buffer": "Buffer"}
ORDER = ["travel", "stay", "food", "activities", "buffer"]

# rough guides (INR) used only to show a warning, not to change any number
MIN_FOOD_PER_PERSON_DAY = 250
MIN_STAY_PER_ROOM_NIGHT = 800


def inr(n: float) -> str:
    """12345678 -> '₹1,23,45,678' (Indian digit grouping)."""
    s = str(int(round(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return "₹" + s


def compute_breakdown(total_budget: float, days: int, people: int, style: str = "balanced") -> dict:
    style = style if style in STYLES else "balanced"
    total = max(int(round(total_budget)), 0)
    days, people = max(int(days), 1), max(int(people), 1)
    nights = days - 1
    rooms = math.ceil(people / 2)

    split = dict(STYLES[style]["split"])
    if nights == 0:                       # a day trip has no hotel: share its money with the rest
        stay = split.pop("stay")
        scale = 100 / (100 - stay)
        split = {k: v * scale for k, v in split.items()}
        split["stay"] = 0

    amounts = {k: int(total * split[k] / 100) for k in ORDER}      # rounded down...
    amounts["buffer"] += total - sum(amounts.values())             # ...the leftover rupees go to the buffer

    per_day_person = lambda k: amounts[k] / (days * people)
    detail = {
        "travel": f"to get there and around, about {inr(amounts['travel'] / people)} per person",
        "stay": (f"about {inr(amounts['stay'] / (rooms * nights))} per room per night "
                 f"({rooms} room{'s' if rooms > 1 else ''}, {nights} night{'s' if nights > 1 else ''})")
                if nights else "no hotel needed for a day trip",
        "food": f"about {inr(per_day_person('food'))} per person per day",
        "activities": f"about {inr(per_day_person('activities'))} per person per day",
        "buffer": "for shopping, tips and surprises",
    }

    warnings = []
    if per_day_person("food") < MIN_FOOD_PER_PERSON_DAY:
        warnings.append(f"Food budget is about {inr(per_day_person('food'))} per person per day, which is tight. "
                        "Consider a larger budget or fewer days.")
    if nights and amounts["stay"] / (rooms * nights) < MIN_STAY_PER_ROOM_NIGHT:
        warnings.append(f"Stay budget is about {inr(amounts['stay'] / (rooms * nights))} per room per night, "
                        "so expect basic guesthouses or hostels.")

    return {
        "style": style,
        "style_label": STYLES[style]["label"],
        "total": total,
        "days": days,
        "nights": nights,
        "people": people,
        "categories": [{"key": k, "label": LABELS[k], "amount": amounts[k],
                        "percent": round(100 * amounts[k] / total) if total else 0, "detail": detail[k]}
                       for k in ORDER],
        "activities_amount": amounts["activities"],
        "warnings": warnings,
        "note": "Estimates from simple rules, not real prices.",
    }
