"""Tests for the AI planner helpers. Run: pytest test_ai.py -v   (no network, no API key needed)"""
import json
import math
import pytest

import ai_planner as ap

ITEMS = [
    {"place_id": 1, "name": "Fort", "category": "sightseeing", "day": 1, "order": 0, "cost": 600, "reason": "liked by 2/2 members"},
    {"place_id": 2, "name": "Street Food Lane", "category": "food", "day": 1, "order": 1, "cost": 400, "reason": "liked by 1/2 members, rated 4.2"},
    {"place_id": 3, "name": "Museum", "category": "sightseeing", "day": 2, "order": 0, "cost": 200, "reason": "must-see"},
]


def test_normalize_gives_unit_length():
    v = ap.normalize([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0)
    assert ap.normalize([0.0, 0.0]) == [0.0, 0.0]


def test_place_text_includes_available_fields_only():
    t = ap.place_text("Amer Fort", "sightseeing", "Jaipur", "A hill fort.", 4.6)
    assert "Amer Fort in Jaipur" in t and "A hill fort." in t and "4.6" in t
    assert ap.place_text("Cafe", None, "Jaipur", None, None) == "Cafe in Jaipur"


def test_query_text_merges_group_interests_and_request():
    q = ap.build_query_text("Goa", [{"tags": ["food"], "pace": "relaxed"}, {"tags": ["beach", "food"], "pace": "packed"}],
                            "quiet beaches")
    assert "Goa" in q and "beach, food" in q and "quiet beaches" in q


def test_query_text_truncates_long_requests():
    q = ap.build_query_text("Goa", [], "x" * 5000)
    assert len(q) < ap.MAX_REQUEST_CHARS + 100


def test_prompt_lists_every_place_id_and_forbids_changes():
    system, user = ap.build_prompt("Trip", "Jaipur", 2, 5000, 1200,
                                   [{"name": "A", "tags": ["food"], "pace": "relaxed"}], "history", ITEMS)
    for pid in (1, 2, 3):
        assert f"place_id={pid}" in user
    assert "FIXED" in system and "ONLY the place_ids" in system
    assert "history" in user


def test_parse_narrative_accepts_code_fences():
    raw = "```json\n" + json.dumps({"summary": "s", "stops": [{"place_id": 1, "why": "w"}]}) + "\n```"
    n = ap.parse_narrative(raw)
    assert n.summary == "s" and n.stops[0].place_id == 1 and n.stops[0].time_of_day == "afternoon"


@pytest.mark.parametrize("bad", ["", "not json", "[]", json.dumps({"stops": [{"place_id": "x"}]})])
def test_parse_narrative_rejects_garbage(bad):
    with pytest.raises(ap.AIUnavailable):
        ap.parse_narrative(bad)


def test_assemble_uses_llm_text_but_optimizer_structure():
    n = ap.Narrative(
        summary="s",
        day_titles=[ap.DayTitle(day=1, title="Old city")],
        stops=[ap.StopNote(place_id=1, time_of_day="morning", why="Great views", tip="Go early"),
               ap.StopNote(place_id=999, why="hallucinated place")],   # not in the plan -> ignored
    )
    days = ap.assemble_days(ITEMS, n)
    assert [d["day"] for d in days] == [1, 2]
    assert days[0]["title"] == "Old city" and days[1]["title"] == "Day 2"
    assert [s["place_id"] for d in days for s in d["stops"]] == [1, 2, 3]   # nothing added or removed
    assert days[0]["stops"][0]["why"] == "Great views" and days[0]["stops"][0]["time_of_day"] == "morning"
    assert days[0]["stops"][0]["cost"] == 600                               # costs come from the optimizer


def test_assemble_falls_back_to_optimizer_reasons_without_llm():
    days = ap.assemble_days(ITEMS, None)
    assert days[0]["stops"][1]["why"] == "liked by 1/2 members, rated 4.2"
    assert days[0]["stops"][0]["time_of_day"] == "morning" and days[0]["stops"][1]["time_of_day"] == "afternoon"


class _FakeModels:
    def __init__(self, text=None, boom=False):
        self.text, self.boom = text, boom

    def generate_content(self, **kw):
        if self.boom:
            raise RuntimeError("quota exceeded")
        self.kw = kw
        return type("R", (), {"text": self.text})()

    def embed_content(self, **kw):
        if self.boom:
            raise RuntimeError("quota exceeded")
        n = len(kw["contents"])
        return type("R", (), {"embeddings": [type("E", (), {"values": [3.0, 4.0]})() for _ in range(n)]})()


class _FakeClient:
    def __init__(self, **kw):
        self.models = _FakeModels(**kw)


def test_generate_narrative_with_fake_client():
    c = _FakeClient(text=json.dumps({"summary": "ok", "stops": []}))
    n = ap.generate_narrative("sys", "user", client=c)
    assert n.summary == "ok"
    assert c.models.kw["config"].response_mime_type == "application/json"


def test_llm_errors_become_ai_unavailable():
    with pytest.raises(ap.AIUnavailable):
        ap.generate_narrative("s", "u", client=_FakeClient(boom=True))
    with pytest.raises(ap.AIUnavailable):
        ap.embed_texts(["a"], "RETRIEVAL_QUERY", client=_FakeClient(boom=True))


def test_embed_texts_batches_and_normalizes():
    vecs = ap.embed_texts(["a"] * 120, "RETRIEVAL_DOCUMENT", client=_FakeClient())
    assert len(vecs) == 120
    assert math.isclose(math.sqrt(sum(x * x for x in vecs[0])), 1.0)


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ap.AIUnavailable, match="GEMINI_API_KEY"):
        ap.embed_texts(["a"], "RETRIEVAL_QUERY")


class _FlakyModels:
    """Fails with the given errors first, then succeeds."""
    def __init__(self, errors, text):
        self.errors, self.text, self.calls = list(errors), text, []

    def generate_content(self, **kw):
        self.calls.append(kw["model"])
        if self.errors:
            raise RuntimeError(self.errors.pop(0))
        return type("R", (), {"text": self.text})()


def _flaky(errors):
    c = type("C", (), {})()
    c.models = _FlakyModels(errors, json.dumps({"summary": "ok"}))
    return c


def test_retries_temporary_503_then_succeeds():
    c, waits = _flaky(["503 UNAVAILABLE", "503 UNAVAILABLE"]), []
    n = ap.generate_narrative("s", "u", client=c, sleep=waits.append)
    assert n.summary == "ok" and len(c.models.calls) == 3 and waits == [2, 4]


def test_does_not_retry_permanent_errors():
    c, waits = _flaky(["404 NOT_FOUND model gone"]), []
    with pytest.raises(ap.AIUnavailable, match="404"):
        ap.generate_narrative("s", "u", client=c, sleep=waits.append)
    assert len(c.models.calls) == 1 and waits == []


def test_gives_up_after_all_retries(monkeypatch):
    monkeypatch.setattr(ap, "FALLBACK_MODEL", "")   # don't depend on the backup model set in .env
    c = _flaky(["503 UNAVAILABLE"] * 10)
    with pytest.raises(ap.AIUnavailable, match="after retries"):
        ap.generate_narrative("s", "u", client=c, sleep=lambda s: None)
    assert len(c.models.calls) == 3


def test_falls_back_to_second_model(monkeypatch):
    monkeypatch.setattr(ap, "FALLBACK_MODEL", "backup-model")
    c = _flaky(["503 UNAVAILABLE"] * 3)       # primary model fails all 3 tries, backup works
    n = ap.generate_narrative("s", "u", client=c, sleep=lambda s: None)
    assert n.summary == "ok" and c.models.calls[-1] == "backup-model"
