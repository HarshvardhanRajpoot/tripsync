import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./t.db")
from unittest.mock import patch
import explore_service as ex

GOOGLE = [
    {"place_id": "a", "name": "Tiny", "rating": 4.9, "reviews": 3},
    {"place_id": "b", "name": "Famous", "rating": 4.5, "reviews": 20000},
]
OVERPASS = [
    {"type": "node", "id": 1, "lat": 26.98, "lon": 75.85,
     "tags": {"name": "Amber Fort", "historic": "fort", "wikipedia": "en:Amer Fort", "wikidata": "Q1"}},
    {"type": "way", "id": 2, "center": {"lat": 26.92, "lon": 75.82},
     "tags": {"name": "Small Shrine", "amenity": "place_of_worship", "religion": "hindu", "wikidata": "Q2"}},
    {"type": "node", "id": 3, "lat": 26.9, "lon": 75.8, "tags": {"name": "Albert Hall Museum", "tourism": "museum", "name:en": "Albert Hall Museum", "wikidata": "Q3", "wikipedia": "en:Albert Hall"}},
    {"type": "node", "id": 4, "lat": 26.9, "lon": 75.8, "tags": {"name": "amber fort", "historic": "fort"}},   # duplicate name
    {"type": "node", "id": 5, "lat": 26.9, "lon": 75.8, "tags": {"tourism": "attraction"}},                  # no name
]

WIKI_PAGES = [
    {"pageid": 1, "title": "Hawa Mahal", "description": "Palace in Jaipur, India", "coordinates": [{"lat": 26.92, "lon": 75.82}],
     "pageviews": {"2026-10-01": 500, "2026-10-02": 700, "2026-10-03": None}},
    {"pageid": 2, "title": "Jal Mahal", "description": "Palace in Jaipur, Rajasthan", "pageviews": {"2026-10-01": 100}},
    {"pageid": 3, "title": "Some Village", "description": "Village in Rajasthan, India", "pageviews": {"2026-10-01": 9999}},
    {"pageid": 4, "title": "City School", "description": "School in Jaipur", "pageviews": {"2026-10-01": 9999}},
    {"pageid": 5, "title": "Hawa Mahal", "description": "Palace in Jaipur", "pageviews": {}},
]


class FakeResp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def test_data_loaded():
    assert "Rajasthan" in ex.get_states() and "Chandigarh" in ex.get_states()
    assert "Jaipur" in ex.get_districts("Rajasthan")
    assert "Dhamtari" in ex.get_districts("Chhattisgarh")


def test_google_ranking_prefers_well_reviewed(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake")
    ex._cache.clear()
    with patch.object(ex, "_search_new", return_value=list(GOOGLE)):
        res = ex.top_places("Rajasthan", "Jaipur")
    assert res["source"] == "google" and res["note"] is None
    assert [p["name"] for p in res["places"]] == ["Famous", "Tiny"]


def test_google_legacy_fallback_and_cache(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake")
    ex._cache.clear()
    with patch.object(ex, "_search_new", side_effect=ex.ExploreError("denied")), \
         patch.object(ex, "_search_legacy", return_value=[{"place_id": "z", "name": "Fort", "rating": 4, "reviews": 10}]) as lg:
        ex.top_places("Goa", "North Goa")
        ex.top_places("Goa", "North Goa")
    assert lg.call_count == 1


def test_google_failure_falls_back_to_osm(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake")
    ex._cache.clear()
    with patch.object(ex, "_search_new", side_effect=ex.ExploreError("a")), \
         patch.object(ex, "_search_legacy", side_effect=ex.ExploreError("b")), \
         patch.object(ex, "_geocode", return_value=(26.9, 75.8)), \
         patch.object(ex, "_overpass", return_value=OVERPASS):
        res = ex.top_places("Rajasthan", "Jaipur")
    assert res["source"] == "openstreetmap"
    assert "Google:" in res["note"] and "Legacy API: b" in res["note"]
    assert len(res["places"]) > 0


def test_no_key_uses_osm(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    ex._cache.clear()
    with patch.object(ex, "_geocode", return_value=(26.9, 75.8)), patch.object(ex, "_overpass", return_value=OVERPASS):
        res = ex.top_places("Rajasthan", "Jaipur")
    assert res["source"] == "openstreetmap" and "no Google key" in res["note"]


def test_osm_parsing_and_ranking():
    places = ex._parse_osm(OVERPASS, "Jaipur", "Rajasthan")
    names = [p["name"] for p in places]
    assert names == ["Amber Fort", "Albert Hall Museum", "Small Shrine"]   # dupes/unnamed dropped, ranked by notability
    amber = places[0]
    assert amber["kind"] == "Fort" and amber["lat"] == 26.98
    assert places[2]["kind"] == "Temple" and places[2]["lat"] == 26.92     # way uses its center
    assert amber["maps_url"].startswith("https://www.google.com/maps/search/?api=1&query=Amber+Fort")


def test_everything_fails_gives_readable_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    ex._cache.clear()
    with patch.object(ex, "_geocode", side_effect=ex.ExploreError("could not locate X")):
        try:
            ex.top_places("Goa", "South Goa")
            assert False
        except ex.ExploreError as e:
            assert "No places source worked" in str(e) and "could not locate X" in str(e)


def test_maps_link():
    assert ex.maps_search_url("Jaipur", "Rajasthan").startswith("https://www.google.com/maps/search/?api=1&query=")


def test_osm_failure_falls_back_to_wikipedia(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    ex._cache.clear()
    with patch.object(ex, "_geocode", return_value=(26.9, 75.8)), \
         patch.object(ex, "_overpass", side_effect=ex.ExploreError("all servers busy")), \
         patch.object(ex, "_wiki_fetch", return_value=WIKI_PAGES):
        res = ex.top_places("Rajasthan", "Jaipur")
    assert res["source"] == "wikipedia"
    assert "openstreetmap: all servers busy" in res["note"]
    assert [p["name"] for p in res["places"]] == ["Hawa Mahal", "Jal Mahal"]


def test_wiki_parsing_filters_and_ranks():
    places = ex._parse_wiki(WIKI_PAGES, "Jaipur", "Rajasthan")
    assert [p["name"] for p in places] == ["Hawa Mahal", "Jal Mahal"]      # village/school/duplicate dropped, by views
    assert places[0]["kind"] == "Palace" and places[0]["lat"] == 26.92


def test_overpass_tries_next_server(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            return FakeResp(504, {})
        return FakeResp(200, {"elements": OVERPASS})

    monkeypatch.setattr(ex.requests, "post", fake_post)
    assert ex._overpass(26.9, 75.8) == OVERPASS
    assert len(calls) == 2 and calls[0] != calls[1]


def test_overpass_all_servers_fail(monkeypatch):
    monkeypatch.setattr(ex.requests, "post", lambda url, **kw: FakeResp(429, {}))
    try:
        ex._overpass(1, 2)
        assert False
    except ex.ExploreError as e:
        assert "HTTP 429" in str(e)
