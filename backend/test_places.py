"""Tests for destination_places (no network, no database). Run: pytest test_places.py -v"""
import pytest
import requests

import destination_places as dp


def el(i, lat, lon, **tags):
    return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}


def test_classify_categories():
    assert dp.classify({"amenity": "restaurant"}) == ("food", "Restaurant")
    assert dp.classify({"historic": "fort"}) == ("sightseeing", "Fort")
    assert dp.classify({"natural": "waterfall"}) == ("adventure", "Waterfall")
    assert dp.classify({"leisure": "water_park"}) == ("adventure", "Water park")
    assert dp.classify({"amenity": "bank"}) == (None, None)


def test_cost_estimates():
    assert dp.estimate_cost("sightseeing", "Temple") == 0
    assert dp.estimate_cost("food", "Restaurant") == 400
    assert dp.estimate_cost("adventure", "Mystery") == 300      # unknown kind -> category default


def test_parse_dedupes_ranks_and_caps():
    elements = [el(1, 1, 1, name="Old Fort", historic="fort", wikidata="Q1"),
                el(2, 1, 1, name="Old Fort", historic="fort"),               # duplicate name
                el(3, 1, 1, name="Plain Park", leisure="park", wikidata="Q3"),
                el(4, 1, 1, tourism="museum"),                               # no name -> skipped
                el(5, 1, 1, name="Bank", amenity="bank"),                    # not a tourist place
                {"type": "way", "id": 6, "center": {"lat": 2, "lon": 2}, "tags": {"name": "Cafe Z", "amenity": "cafe"}}]
    out = dp.parse_elements(elements)
    assert [p["name"] for p in out] == ["Old Fort", "Plain Park", "Cafe Z"]
    assert {p["category"] for p in out} == {"sightseeing", "food"}


def test_parse_respects_limits():
    elements = [el(i, 1, 1, name=f"R{i}", amenity="restaurant", cuisine="x") for i in range(30)]
    assert len(dp.parse_elements(elements)) == dp.LIMITS["food"]


class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d


def _no(*a, **k):
    return []


def _down(msg):
    def f(*a, **k):
        raise dp.PlacesUnavailable(msg)
    return f


def _many_osm(n=10):
    return [el(i, 26.9, 75.8, name=f"Fort {i}", historic="fort") for i in range(n)]


def test_overpass_alone_is_enough_when_it_finds_many(monkeypatch):
    monkeypatch.setattr(dp, "_geocode", lambda d: (26.9, 75.8))
    monkeypatch.setattr(dp, "_overpass", lambda q: _many_osm())
    monkeypatch.setattr(dp, "_nominatim_places", lambda *a: pytest.fail("should not be called"))
    monkeypatch.setattr(dp, "_wiki_pages", lambda *a: pytest.fail("should not be called"))
    info = dp.fetch_destination_places("Jaipur")
    assert info["source"] == "openstreetmap" and len(info["places"]) == 10


def test_keeps_attractions_if_only_food_query_fails(monkeypatch):
    monkeypatch.setattr(dp, "_geocode", lambda d: (26.9, 75.8))
    monkeypatch.setattr(dp, "_overpass", lambda q: (_ for _ in ()).throw(dp.PlacesUnavailable("busy"))
                        if "restaurant" in q else _many_osm())
    info = dp.fetch_destination_places("Jaipur")
    assert len(info["places"]) == 10 and any("restaurants" in n for n in info["notes"])


def test_blocked_overpass_falls_back_to_nominatim_search(monkeypatch):
    monkeypatch.setattr(dp, "_geocode", lambda d: (22.47, 78.43))
    monkeypatch.setattr(dp, "_overpass", _down("all servers unreachable"))
    found = [{"name": f"Falls {i}", "category": "adventure", "kind": "Waterfall", "lat": 22.4, "lng": 78.4,
              "cost": 0.0, "score": 0.5} for i in range(5)] + \
            [{"name": f"Cafe {i}", "category": "food", "kind": "Cafe", "lat": 22.4, "lng": 78.4,
              "cost": 300.0, "score": 0.1} for i in range(4)]
    monkeypatch.setattr(dp, "_nominatim_places", lambda *a: found)
    monkeypatch.setattr(dp, "_wiki_pages", lambda *a: pytest.fail("enough places already"))
    info = dp.fetch_destination_places("Pachmarhi")
    assert info["source"] == "openstreetmap search" and len(info["places"]) == 9
    assert any("Overpass" in n for n in info["notes"])


def test_sources_are_merged_without_duplicates(monkeypatch):
    monkeypatch.setattr(dp, "_geocode", lambda d: (15.3, 74.0))
    monkeypatch.setattr(dp, "_overpass", lambda q: [el(1, 15.3, 74.0, name="Fort Aguada", historic="fort")])
    monkeypatch.setattr(dp, "_nominatim_places", lambda *a: [
        {"name": "fort aguada", "category": "sightseeing", "kind": "Fort", "lat": 1, "lng": 1, "cost": 200.0, "score": 0.9}])
    pages = [{"pageid": 1, "title": "Fort Aguada", "description": "fort in Goa", "coordinates": [{"lat": 15.5, "lon": 73.9}]},
             {"pageid": 2, "title": "Basilica of Bom Jesus", "description": "church in Goa, India",
              "coordinates": [{"lat": 15.5, "lon": 73.9}], "pageviews": {"d": 900}}]
    monkeypatch.setattr(dp, "_wiki_pages", lambda *a: pages)
    info = dp.fetch_destination_places("Goa")
    names = [p["name"].lower() for p in info["places"]]
    assert sorted(names) == ["basilica of bom jesus", "fort aguada"]
    assert info["source"] == "openstreetmap + wikipedia"


def test_nominatim_hits_are_classified_ranked_and_distance_filtered():
    hits = [
        {"name": "Bee Falls", "lat": "22.45", "lon": "78.40", "category": "natural", "type": "waterfall", "importance": 0.4},
        {"name": "Hotel Rock", "lat": "22.46", "lon": "78.41", "category": "amenity", "type": "restaurant", "importance": 0.1},
        {"name": "Far Away Fort", "lat": "28.6", "lon": "77.2", "category": "historic", "type": "fort", "importance": 0.9},
        {"name": "ATM", "lat": "22.46", "lon": "78.42", "category": "amenity", "type": "atm"},
        {"display_name": "Jata Shankar, Pachmarhi, MP", "lat": "22.47", "lon": "78.43", "category": "historic",
         "type": "temple", "importance": 0.3},
    ]
    out = dp.parse_nominatim(hits, 22.47, 78.43)
    got = {p["name"]: p["category"] for p in out}
    assert got == {"Bee Falls": "adventure", "Hotel Rock": "food", "Jata Shankar": "sightseeing"}


def test_nominatim_search_fails_cleanly_when_unreachable(monkeypatch):
    monkeypatch.setattr(dp.time, "sleep", lambda s: None)
    monkeypatch.setattr(dp.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    with pytest.raises(dp.PlacesUnavailable, match="search unreachable"):
        dp._nominatim_places("Pachmarhi", 22.4, 78.4)


def test_wikipedia_covers_five_points_and_dedupes(monkeypatch):
    seen_points = []

    def fake(lat, lon):
        seen_points.append((round(lat, 2), round(lon, 2)))
        return [{"pageid": 7, "title": "Same page"}, {"pageid": len(seen_points) + 100, "title": "Other"}]
    monkeypatch.setattr(dp.ex, "_wiki_fetch", fake)
    pages = dp._wiki_pages(22.4, 78.4)
    assert len(seen_points) == 5 and len({p["pageid"] for p in pages}) == len(pages) == 6


def test_everything_down_gives_clear_error(monkeypatch):
    monkeypatch.setattr(dp, "_geocode", lambda d: (1.0, 1.0))
    monkeypatch.setattr(dp, "_overpass", _down("down"))
    monkeypatch.setattr(dp, "_nominatim_places", _down("OpenStreetMap search unreachable"))
    monkeypatch.setattr(dp, "_wiki_pages", _down("Wikipedia unreachable"))
    with pytest.raises(dp.PlacesUnavailable, match="Wikipedia unreachable"):
        dp.fetch_destination_places("Nowhere")


def test_unknown_destination_is_reported(monkeypatch):
    monkeypatch.setattr(dp.requests, "get", lambda *a, **k: _Resp([]))
    with pytest.raises(dp.PlacesUnavailable, match="could not find"):
        dp.fetch_destination_places("Zzzzzz")
