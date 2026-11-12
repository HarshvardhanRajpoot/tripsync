"""
Explore: state -> district -> top places to visit, with Google Maps links.

States/districts come from data/india_states_districts.json (static).
Places come from Google Places text search ("top tourist attractions in
<district>, <state>"). It tries the newer Places API first and falls back to
the legacy Text Search your places_service.py already uses.

If Google is unavailable (no key, billing off, API not enabled, no results),
it falls back to OpenStreetMap (free, no key): Nominatim finds the district,
Overpass lists named attractions, forts, museums, temples, etc. around it.
Results are cached in memory for 24 hours.
"""
import json
import math
import os
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

DATA_FILE = Path(__file__).parent / "data" / "india_states_districts.json"
NEW_URL = "https://places.googleapis.com/v1/places:searchText"
LEGACY_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
CACHE_SECONDS = 24 * 60 * 60
OSM_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSM_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
WIKI_API = "https://en.wikipedia.org/w/api.php"
OSM_USER_AGENT = "TripSync-college-project/1.0 (student project)"
OSM_RADIUS_M = 20000
_cache: dict = {}


class ExploreError(Exception):
    """A problem we can show to the user (bad key, quota, no key set...)."""


def _clean(name: str) -> str:
    return name.replace(" (UT)", "").replace(" (NCT)", "").strip()


def _load() -> dict:
    with open(DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)["states"]
    return {_clean(s["state"]): sorted(s["districts"]) for s in raw}


STATES = _load()


def get_states() -> list[str]:
    return sorted(STATES)


def get_districts(state: str):
    return STATES.get(state)


def maps_search_url(district: str, state: str) -> str:
    q = quote_plus(f"top tourist places in {district} {state}")
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def _popularity(p: dict) -> float:
    # rating weighted by how many people rated it, so 4.8 from 3 reviews
    # doesn't beat 4.5 from 20,000 reviews
    return (p.get("rating") or 0) * math.log10(1 + (p.get("reviews") or 0))


def _search_new(query: str, key: str) -> list[dict]:
    resp = requests.post(
        NEW_URL,
        json={"textQuery": query, "pageSize": 20, "languageCode": "en", "regionCode": "IN"},
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,"
                                "places.rating,places.userRatingCount,places.location,places.googleMapsUri",
        },
        timeout=10,
    )
    data = resp.json()
    if resp.status_code != 200:
        raise ExploreError(data.get("error", {}).get("message", f"HTTP {resp.status_code}"))
    out = []
    for r in data.get("places", []):
        loc = r.get("location", {})
        out.append({
            "place_id": r.get("id"),
            "name": r.get("displayName", {}).get("text"),
            "address": r.get("formattedAddress"),
            "rating": r.get("rating"),
            "reviews": r.get("userRatingCount"),
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
            "maps_url": r.get("googleMapsUri"),
        })
    return out


def _search_legacy(query: str, key: str) -> list[dict]:
    resp = requests.get(LEGACY_URL, params={"query": query, "key": key}, timeout=10)
    data = resp.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        raise ExploreError(f"{data.get('status')} {data.get('error_message', '')}".strip())
    out = []
    for r in data.get("results", []):
        loc = r.get("geometry", {}).get("location", {})
        name = r.get("name")
        out.append({
            "place_id": r.get("place_id"),
            "name": name,
            "address": r.get("formatted_address"),
            "rating": r.get("rating"),
            "reviews": r.get("user_ratings_total"),
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "maps_url": "https://www.google.com/maps/search/?api=1"
                        f"&query={quote_plus(name or '')}&query_place_id={r.get('place_id')}",
        })
    return out


# ---- OpenStreetMap fallback (no API key needed) ---------------------------
_KIND_LABELS = {
    ("tourism", "museum"): "Museum", ("tourism", "viewpoint"): "Viewpoint",
    ("tourism", "zoo"): "Zoo", ("tourism", "theme_park"): "Theme park",
    ("tourism", "gallery"): "Gallery", ("tourism", "aquarium"): "Aquarium",
    ("tourism", "attraction"): "Attraction",
    ("historic", "fort"): "Fort", ("historic", "castle"): "Fort",
    ("historic", "palace"): "Palace", ("historic", "monument"): "Monument",
    ("historic", "memorial"): "Memorial", ("historic", "tomb"): "Tomb",
    ("historic", "archaeological_site"): "Heritage site", ("historic", "ruins"): "Ruins",
    ("historic", "temple"): "Temple", ("historic", "city_gate"): "Gate",
    ("natural", "waterfall"): "Waterfall", ("natural", "peak"): "Peak",
    ("natural", "beach"): "Beach", ("natural", "hot_spring"): "Hot spring",
    ("natural", "cave_entrance"): "Cave",
    ("leisure", "park"): "Park", ("leisure", "nature_reserve"): "Nature reserve",
}
_RELIGION_LABELS = {"hindu": "Temple", "muslim": "Mosque", "christian": "Church",
                    "sikh": "Gurdwara", "buddhist": "Monastery", "jain": "Jain temple"}

_OVERPASS_QUERY = """
[out:json][timeout:25];
(
  nwr["tourism"~"^(attraction|museum|viewpoint|zoo|theme_park|gallery|aquarium)$"]["name"](around:{r},{lat},{lon});
  nwr["historic"~"^(fort|castle|palace|monument|memorial|archaeological_site|ruins|temple|city_gate|tomb)$"]["name"](around:{r},{lat},{lon});
  nwr["amenity"="place_of_worship"]["name"]["wikidata"](around:{r},{lat},{lon});
  nwr["natural"~"^(waterfall|peak|beach|hot_spring|cave_entrance)$"]["name"](around:{r},{lat},{lon});
  nwr["leisure"~"^(park|nature_reserve)$"]["name"]["wikidata"](around:{r},{lat},{lon});
);
out center 200;
"""


def _geocode(district: str, state: str) -> tuple[float, float]:
    resp = requests.get(
        OSM_NOMINATIM_URL,
        params={"q": f"{district}, {state}, India", "format": "json", "limit": 1},
        headers={"User-Agent": OSM_USER_AGENT},
        timeout=15,
    )
    data = resp.json()
    if not data:
        raise ExploreError(f"could not locate {district}")
    return float(data[0]["lat"]), float(data[0]["lon"])


def _overpass(lat: float, lon: float) -> list[dict]:
    """Tries each public Overpass server until one answers with results."""
    query = _OVERPASS_QUERY.format(r=OSM_RADIUS_M, lat=lat, lon=lon)
    errors = []
    for url in OSM_OVERPASS_URLS:
        host = url.split("/")[2]
        try:
            resp = requests.post(url, data={"data": query}, headers={"User-Agent": OSM_USER_AGENT}, timeout=30)
            if resp.status_code != 200:
                errors.append(f"{host} HTTP {resp.status_code}")
                continue
            data = resp.json()
            if data.get("elements"):
                return data["elements"]
            errors.append(f"{host} returned no places" + (f" ({data['remark'][:60]})" if data.get("remark") else ""))
        except (requests.RequestException, ValueError) as e:
            errors.append(f"{host} unreachable")
    raise ExploreError("; ".join(errors))


def _kind(tags: dict):
    for key in ("tourism", "historic", "natural", "leisure"):
        label = _KIND_LABELS.get((key, tags.get(key)))
        if label:
            return label
    if tags.get("amenity") == "place_of_worship":
        return _RELIGION_LABELS.get(tags.get("religion"), "Place of worship")
    return None


def _osm_score(tags: dict) -> float:
    # famous places tend to have Wikipedia/Wikidata entries and heritage tags
    score = 0.0
    if tags.get("wikipedia"):
        score += 3
    if tags.get("wikidata"):
        score += 2
    if tags.get("heritage"):
        score += 1
    if tags.get("name:en"):
        score += 0.5
    if tags.get("website") or tags.get("wikimedia_commons"):
        score += 0.5
    if tags.get("historic") in ("fort", "castle", "palace"):
        score += 1
    if tags.get("tourism") in ("attraction", "museum"):
        score += 0.5
    return score


def _parse_osm(elements: list[dict], district: str, state: str) -> list[dict]:
    out, seen = [], set()
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name:en") or tags.get("name")
        if not name or name.lower() in seen:
            continue
        loc = el if "lat" in el else el.get("center", {})
        seen.add(name.lower())
        query = quote_plus(f"{name}, {district}, {state}")
        out.append({
            "place_id": f"osm-{el.get('type')}-{el.get('id')}",
            "name": name,
            "address": f"{district}, {state}",
            "rating": None,
            "reviews": None,
            "kind": _kind(tags),
            "lat": loc.get("lat"),
            "lng": loc.get("lon"),
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={query}",
            "_score": _osm_score(tags),
        })
    out.sort(key=lambda p: p["_score"], reverse=True)
    for p in out:
        del p["_score"]
    return out


# ---- Wikipedia fallback (notable places near the district centre) ----------
_WIKI_KEEP = ("fort", "palace", "temple", "mosque", "church", "gurdwara", "monument", "museum", "lake",
              "garden", "park", "dam", "waterfall", "beach", "observatory", "tomb", "mausoleum", "heritage",
              "cave", "sanctuary", "ghat", "shrine", "stepwell", "baoli", "gate", "tower", "minar",
              "memorial", "zoo", "hill", "viewpoint", "reservoir", "barrage", "wildlife", "tourist", "math")
_WIKI_SKIP = ("village", "school", "college", "university", "railway", "station", "town in", "city in",
              "district", "tehsil", "hospital", "institute")


def _wiki_fetch(lat: float, lon: float) -> list[dict]:
    resp = requests.get(
        WIKI_API,
        params={"action": "query", "format": "json", "generator": "geosearch",
                "ggscoord": f"{lat}|{lon}", "ggsradius": 10000, "ggslimit": 50,
                "prop": "description|coordinates|pageviews", "pvipdays": 30, "colimit": 50},
        headers={"User-Agent": OSM_USER_AGENT},
        timeout=15,
    )
    return list(((resp.json().get("query") or {}).get("pages") or {}).values())


def _parse_wiki(pages: list[dict], district: str, state: str) -> list[dict]:
    out, seen = [], set()
    for pg in pages:
        title = pg.get("title")
        desc = (pg.get("description") or "").strip()
        low = desc.lower()
        if not title or title.lower() in seen:
            continue
        if not any(k in low for k in _WIKI_KEEP) or any(k in low for k in _WIKI_SKIP):
            continue
        seen.add(title.lower())
        views = sum(v for v in (pg.get("pageviews") or {}).values() if v)
        loc = (pg.get("coordinates") or [{}])[0]
        kind = desc.split(" in ")[0] if " in " in desc else desc
        out.append({
            "place_id": f"wiki-{pg.get('pageid')}",
            "name": title,
            "address": f"{district}, {state}",
            "rating": None,
            "reviews": None,
            "kind": (kind[:1].upper() + kind[1:]) if kind and len(kind) <= 30 else None,
            "lat": loc.get("lat"),
            "lng": loc.get("lon"),
            "maps_url": "https://www.google.com/maps/search/?api=1&query="
                        + quote_plus(f"{title}, {district}, {state}"),
            "_views": views,
        })
    out.sort(key=lambda p: p["_views"], reverse=True)
    for p in out:
        del p["_views"]
    return out


# ---- Public entry point ----------------------------------------------------
def _call_google(fn, query: str, key: str) -> list[dict]:
    try:
        return fn(query, key)
    except requests.RequestException:
        raise ExploreError("could not reach Google")
    except ValueError:
        raise ExploreError("unexpected reply from Google")


def _google_places(query: str, key: str) -> list[dict]:
    try:
        results = _call_google(_search_new, query, key)
    except ExploreError as new_err:
        try:
            results = _call_google(_search_legacy, query, key)
        except ExploreError as legacy_err:
            raise ExploreError(f"New API: {new_err}. Legacy API: {legacy_err}")
    results = [p for p in results if p.get("name")]
    if not results:
        raise ExploreError("Google returned no results")
    results.sort(key=_popularity, reverse=True)
    return results


def top_places(state: str, district: str, limit: int = 10) -> dict:
    """
    Tries Google, then OpenStreetMap, then Wikipedia. Returns
    {"places": [...], "source": "google"|"openstreetmap"|"wikipedia", "note": str|None}.
    """
    cache_key = (state.lower(), district.lower())
    hit = _cache.get(cache_key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return {**hit[1], "places": hit[1]["places"][:limit]}

    failures: list[str] = []
    result = None

    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if key:
        try:
            result = {"places": _google_places(f"top tourist attractions in {district}, {state}, India", key),
                      "source": "google"}
        except ExploreError as e:
            failures.append(f"Google: {str(e)[:150]}")
    else:
        failures.append("no Google key set")

    if result is None:
        coords = None
        try:
            coords = _geocode(district, state)
        except (ExploreError, requests.RequestException, ValueError) as e:
            failures.append(f"location lookup: {e}")
        if coords:
            lat, lon = coords
            sources = (
                ("openstreetmap", lambda: _parse_osm(_overpass(lat, lon), district, state)),
                ("wikipedia", lambda: _parse_wiki(_wiki_fetch(lat, lon), district, state)),
            )
            for name, fetch in sources:
                try:
                    places = fetch()
                    if not places:
                        raise ExploreError("no places found")
                    result = {"places": places, "source": name}
                    break
                except (ExploreError, requests.RequestException, ValueError) as e:
                    failures.append(f"{name}: {e}")

    if result is None:
        raise ExploreError("No places source worked. " + " | ".join(failures))

    result["note"] = None if not failures else "Skipped: " + " | ".join(failures)
    _cache[cache_key] = (time.time(), result)
    return {**result, "places": result["places"][:limit]}
