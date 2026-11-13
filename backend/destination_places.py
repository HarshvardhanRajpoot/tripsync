"""
Places for ANY destination, with no API key.

The planner needs rows in the `places` table. Without a Google key, the only
places were the Jaipur sample data. This module fills the table for a new
destination from free sources:

  1. Nominatim (OpenStreetMap)  -> where is the destination?
  2. Overpass (OpenStreetMap)   -> attractions, plus restaurants/cafes, around it
  3. Nominatim search           -> "temple in X", "restaurant in X"... if Overpass is
                                   blocked or down (it is on some networks)
  4. Wikipedia                  -> notable attractions around it (5 search points)
Each later source is only used while we still have fewer than MIN_PLACES places.

Reuses the OSM/Wikipedia helpers already written for the Explore page.
Costs are ROUGH ESTIMATES per person (OpenStreetMap has no prices) and ratings
are left empty, so the optimizer treats every place as neutral on rating.
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from sqlalchemy.orm import Session

import explore_service as ex
import models

ATTRACTION_RADIUS_M = 15_000
FOOD_RADIUS_M = 8_000
OVERPASS_TIMEOUT = (5, 20)     # (connect, read) seconds per server: a blocked server fails in 5s
MIN_PLACES = 8                 # below this we also try the next source
NOMINATIM_RADIUS_KM = 40       # ignore search hits farther than this from the destination
NOMINATIM_PHRASES = ["tourist attraction", "temple", "waterfall", "viewpoint", "park", "fort",
                     "museum", "restaurant", "cafe"]
LIMITS = {"sightseeing": 18, "adventure": 6, "food": 8}


class PlacesUnavailable(Exception):
    """No source could provide places (network blocked, destination not found...)."""


# ---- Classification + rough costs (pure, unit-tested) -------------------------
_ADVENTURE_KINDS = {"Theme park", "Waterfall", "Peak", "Cave", "Nature reserve", "Water park"}
_COSTS = {
    "Restaurant": 400, "Cafe": 300, "Fast food": 150, "Food court": 250, "Ice cream": 100,
    "Museum": 100, "Gallery": 100, "Fort": 200, "Palace": 300, "Zoo": 200, "Aquarium": 300,
    "Monument": 50, "Memorial": 0, "Tomb": 50, "Heritage site": 50, "Ruins": 50, "Gate": 0,
    "Temple": 0, "Mosque": 0, "Church": 0, "Gurdwara": 0, "Monastery": 0, "Jain temple": 0,
    "Park": 50, "Viewpoint": 0, "Beach": 0, "Hot spring": 100,
    "Theme park": 1000, "Water park": 800, "Waterfall": 0, "Peak": 0, "Cave": 100, "Nature reserve": 200,
    "Attraction": 100,
}
_FOOD_LABELS = {"restaurant": "Restaurant", "cafe": "Cafe", "fast_food": "Fast food",
                "food_court": "Food court", "ice_cream": "Ice cream"}
DEFAULT_COST = {"sightseeing": 100, "adventure": 300, "food": 300}


def classify(tags: dict) -> tuple[str | None, str | None]:
    """OSM tags -> (category, kind label); category is food / adventure / sightseeing."""
    amenity = tags.get("amenity")
    if amenity in _FOOD_LABELS:
        return "food", _FOOD_LABELS[amenity]
    if tags.get("leisure") == "water_park":
        return "adventure", "Water park"
    kind = ex._kind(tags)
    if not kind:
        return None, None
    return ("adventure" if kind in _ADVENTURE_KINDS else "sightseeing"), kind


def estimate_cost(category: str, kind: str | None) -> float:
    return float(_COSTS.get(kind or "", DEFAULT_COST.get(category, 100)))


def _richness(tags: dict) -> float:
    """Tags that famous / well-kept places tend to have; used to rank OSM results."""
    return (3 * bool(tags.get("wikipedia")) + 2 * bool(tags.get("wikidata")) + bool(tags.get("heritage"))
            + bool(tags.get("website")) + bool(tags.get("cuisine")) + bool(tags.get("opening_hours"))
            + 0.5 * bool(tags.get("name:en")))


def parse_elements(elements: list[dict]) -> list[dict]:
    """Overpass elements -> place dicts, best first within each category, capped by LIMITS."""
    found, seen = [], set()
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        category, kind = classify(tags)
        loc = el if "lat" in el else el.get("center", {})
        if not name or not category or name.lower() in seen or loc.get("lat") is None:
            continue
        seen.add(name.lower())
        found.append({"name": name, "category": category, "kind": kind or "",
                      "lat": loc["lat"], "lng": loc["lon"],
                      "cost": estimate_cost(category, kind), "score": _richness(tags)})
    out = []
    for category, limit in LIMITS.items():
        group = sorted((p for p in found if p["category"] == category), key=lambda p: p["score"], reverse=True)
        out += group[:limit]
    return out


# ---- Network (OpenStreetMap + Wikipedia) ---------------------------------------
def _geocode(destination: str) -> tuple[float, float]:
    r = requests.get(ex.OSM_NOMINATIM_URL,
                     params={"q": f"{destination}, India", "format": "json", "limit": 1},
                     headers={"User-Agent": ex.OSM_USER_AGENT}, timeout=12)
    data = r.json()
    if not data:
        raise PlacesUnavailable(f"could not find '{destination}' on the map")
    return float(data[0]["lat"]), float(data[0]["lon"])


def _overpass(query: str) -> list[dict]:
    errors = []
    for url in ex.OSM_OVERPASS_URLS:
        host = url.split("/")[2]
        try:
            r = requests.post(url, data={"data": query}, headers={"User-Agent": ex.OSM_USER_AGENT},
                              timeout=OVERPASS_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("elements", [])
            errors.append(f"{host} HTTP {r.status_code}")
        except (requests.RequestException, ValueError):
            errors.append(f"{host} unreachable")
    raise PlacesUnavailable("; ".join(errors))


_FOOD_QUERY = """
[out:json][timeout:25];
nwr["amenity"~"^(restaurant|cafe|fast_food|food_court|ice_cream)$"]["name"]["cuisine"](around:{r},{lat},{lon});
out center 150;
"""


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371 * math.hypot(x, math.radians(lat2 - lat1))


def parse_nominatim(results: list[dict], lat: float, lon: float) -> list[dict]:
    """Nominatim search hits -> place dicts (same shape as parse_elements)."""
    out = []
    for r in results:
        tags = {r.get("category") or r.get("class", ""): r.get("type", ""), **(r.get("extratags") or {})}
        if r.get("type") == "place_of_worship" or tags.get("amenity") == "place_of_worship":
            tags["amenity"] = "place_of_worship"
        category, kind = classify(tags)
        name = (r.get("name") or (r.get("display_name") or "").split(",")[0]).strip()
        try:
            plat, plon = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not name or not category or _km(lat, lon, plat, plon) > NOMINATIM_RADIUS_KM:
            continue
        out.append({"name": name, "category": category, "kind": kind or "", "lat": plat, "lng": plon,
                    "cost": estimate_cost(category, kind), "score": float(r.get("importance") or 0)})
    return out


def _nominatim_places(destination: str, lat: float, lon: float) -> list[dict]:
    """Searches like 'temple in Pachmarhi'. Slow on purpose: Nominatim allows 1 request per second."""
    hits, failed = [], 0
    for phrase in NOMINATIM_PHRASES:
        try:
            r = requests.get(ex.OSM_NOMINATIM_URL,
                             params={"q": f"{phrase} in {destination}", "format": "jsonv2", "limit": 20,
                                     "extratags": 1, "countrycodes": "in"},
                             headers={"User-Agent": ex.OSM_USER_AGENT}, timeout=12)
            if r.status_code == 200:
                hits += r.json()
            else:
                failed += 1
        except (requests.RequestException, ValueError):
            failed += 1
        time.sleep(1.1)
    if failed == len(NOMINATIM_PHRASES):
        raise PlacesUnavailable("OpenStreetMap search unreachable")
    return parse_nominatim(hits, lat, lon)


def _wiki_pages(lat: float, lon: float) -> list[dict]:
    """Wikipedia geosearch allows at most 10 km, so search around 5 points to cover ~20 km."""
    d = 0.07                                       # ~8 km in degrees
    points = [(lat, lon), (lat + d, lon), (lat - d, lon), (lat, lon + d), (lat, lon - d)]

    def one(p):
        try:
            return ex._wiki_fetch(*p)
        except (requests.RequestException, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(one, points))
    if all(r is None for r in results):
        raise PlacesUnavailable("Wikipedia unreachable")
    seen, pages = set(), []
    for res in results:
        for pg in res or []:
            if pg.get("pageid") not in seen:
                seen.add(pg.get("pageid"))
                pages.append(pg)
    return pages


def _merge(places: list[dict], more: list[dict]) -> list[dict]:
    names = {p["name"].lower() for p in places}
    return places + [p for p in more if p["name"].lower() not in names]


def _cap(places: list[dict]) -> list[dict]:
    out = []
    for category, limit in LIMITS.items():
        group = sorted((p for p in places if p["category"] == category), key=lambda p: p["score"], reverse=True)
        out += group[:limit]
    return out


def fetch_destination_places(destination: str) -> dict:
    """{"places": [...], "source": "openstreetmap + wikipedia", "notes": [...]}"""
    try:
        lat, lon = _geocode(destination)
    except requests.RequestException as e:
        raise PlacesUnavailable(f"location lookup failed ({type(e).__name__})") from e

    notes: list[str] = []
    places: list[dict] = []
    sources: list[str] = []

    # 1. Overpass: the best source (attractions + restaurants in one place)
    try:
        elements = _overpass(ex._OVERPASS_QUERY.format(r=ATTRACTION_RADIUS_M, lat=lat, lon=lon))
        try:   # food is a bonus: a failure here must not lose the attractions
            elements += _overpass(_FOOD_QUERY.format(r=FOOD_RADIUS_M, lat=lat, lon=lon))
        except PlacesUnavailable:
            notes.append("restaurants could not be loaded from Overpass")
        places = parse_elements(elements)
        if places:
            sources.append("openstreetmap")
    except PlacesUnavailable as e:
        notes.append(f"OpenStreetMap Overpass: {e}")

    # 2. Nominatim searches: works on networks where Overpass is blocked
    if len(places) < MIN_PLACES:
        try:
            merged = _merge(places, _nominatim_places(destination, lat, lon))
            if len(merged) > len(places):        # only credit a source that added something new
                places = merged
                sources.append("openstreetmap search")
        except PlacesUnavailable as e:
            notes.append(str(e))

    # 3. Wikipedia: attractions only
    if len(places) < MIN_PLACES:
        try:
            parsed = ex._parse_wiki(_wiki_pages(lat, lon), destination, "")
            wiki = [{"name": p["name"], "category": "sightseeing", "kind": p.get("kind") or "",
                     "lat": p["lat"], "lng": p["lng"], "cost": estimate_cost("sightseeing", p.get("kind")),
                     "score": 0} for p in parsed if p.get("lat") is not None]
            merged = _merge(places, wiki)
            if len(merged) > len(places):
                places = merged
                sources.append("wikipedia")
        except PlacesUnavailable as e:
            notes.append(str(e))

    places = _cap(places)
    if not places:
        raise PlacesUnavailable("; ".join(notes) or "nothing found")
    if not any(p["category"] == "food" for p in places):
        notes.append("no restaurants were found, so food preferences can't be matched")
    return {"places": places, "source": " + ".join(sources), "notes": notes}


# ---- Database --------------------------------------------------------------------
def ensure_places(db: Session, destination: str) -> dict:
    """
    If the destination has no places yet, fetch some and save them. Safe to call
    repeatedly: it never duplicates a place name for the same destination.
    """
    existing = {n.lower() for (n,) in db.query(models.Place.name).filter(models.Place.destination == destination)}
    if existing:
        return {"created": 0, "source": "cache", "notes": []}
    info = fetch_destination_places(destination)
    created = 0
    for p in info["places"]:
        if p["name"].lower() in existing:
            continue
        existing.add(p["name"].lower())
        db.add(models.Place(name=p["name"], category=p["category"], latitude=p["lat"], longitude=p["lng"],
                            estimated_cost=p["cost"], rating=None, destination=destination,
                            description=p["kind"] or ""))
        created += 1
    db.commit()
    return {"created": created, "source": info["source"], "notes": info["notes"]}
