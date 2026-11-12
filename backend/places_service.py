"""
Fetches real places (restaurants, attractions, activities) from Google Places
and caches them in our own `places` table, so we don't hit Google's API
repeatedly for the same destination.
"""

import os
import requests
from sqlalchemy.orm import Session

import models

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Each query maps to the category we'll store places under.
CATEGORY_QUERIES = {
    "sightseeing": "top tourist attractions in {destination}",
    "food": "popular restaurants in {destination}",
    "adventure": "adventure activities in {destination}",
}

# Google gives a 0-4 "price_level" instead of a real cost. We convert that
# into a rough rupee estimate per person, per visit — good enough for the
# optimizer to reason about relative cost, even if not perfectly accurate.
PRICE_LEVEL_TO_COST = {
    0: 200,
    1: 500,
    2: 1000,
    3: 2000,
    4: 4000,
}
DEFAULT_COST_WHEN_UNKNOWN = 500


def _price_level_to_cost(price_level) -> float:
    if price_level is None:
        return DEFAULT_COST_WHEN_UNKNOWN
    return PRICE_LEVEL_TO_COST.get(price_level, DEFAULT_COST_WHEN_UNKNOWN)


def fetch_and_cache_places(destination: str, db: Session) -> dict:
    """
    Calls Google Places for each category, and inserts any place we don't
    already have (matched by google_place_id) into our `places` table.
    Returns a small summary of what happened.
    """
    if not GOOGLE_PLACES_API_KEY:
        raise RuntimeError(
            "GOOGLE_PLACES_API_KEY is not set in your .env file. "
            "Get a free key from Google Cloud Console and add it there."
        )

    created_count = 0
    skipped_count = 0

    for category, query_template in CATEGORY_QUERIES.items():
        query = query_template.format(destination=destination)
        response = requests.get(
            TEXT_SEARCH_URL,
            params={"query": query, "key": GOOGLE_PLACES_API_KEY},
            timeout=10,
        )
        data = response.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            # Surface Google's own error message (e.g. bad API key, billing not enabled)
            raise RuntimeError(f"Google Places error for '{query}': {data.get('status')} - {data.get('error_message', '')}")

        for result in data.get("results", []):
            google_place_id = result.get("place_id")

            existing = (
                db.query(models.Place)
                .filter(models.Place.google_place_id == google_place_id)
                .first()
            )
            if existing:
                skipped_count += 1
                continue

            location = result.get("geometry", {}).get("location", {})
            new_place = models.Place(
                google_place_id=google_place_id,
                name=result.get("name"),
                category=category,
                latitude=location.get("lat"),
                longitude=location.get("lng"),
                estimated_cost=_price_level_to_cost(result.get("price_level")),
                rating=result.get("rating"),
                destination=destination,
            )
            db.add(new_place)
            created_count += 1

    db.commit()
    return {"created": created_count, "already_cached": skipped_count}
