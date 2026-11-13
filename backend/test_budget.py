"""Tests for budget_breakdown. Run: pytest test_budget.py -v"""
import pytest

import budget_breakdown as bb


@pytest.mark.parametrize("total", [0, 999, 15000, 33333, 100001])
@pytest.mark.parametrize("style", ["budget", "balanced", "comfort"])
@pytest.mark.parametrize("days,people", [(1, 1), (3, 2), (5, 4), (2, 3)])
def test_parts_always_add_up_to_the_total(total, style, days, people):
    b = bb.compute_breakdown(total, days, people, style)
    assert sum(c["amount"] for c in b["categories"]) == total
    assert all(c["amount"] >= 0 for c in b["categories"])


def test_balanced_split_matches_the_percentages():
    b = bb.compute_breakdown(20000, 3, 2, "balanced")
    got = {c["key"]: c["amount"] for c in b["categories"]}
    assert got == {"travel": 5000, "stay": 6000, "food": 4000, "activities": 4000, "buffer": 1000}
    assert b["activities_amount"] == 4000


def test_styles_move_money_between_categories():
    stay = lambda s: next(c["amount"] for c in bb.compute_breakdown(20000, 3, 2, s)["categories"] if c["key"] == "stay")
    assert stay("budget") < stay("balanced") < stay("comfort")


def test_unknown_style_falls_back_to_balanced():
    assert bb.compute_breakdown(10000, 2, 2, "luxury")["style"] == "balanced"


def test_day_trip_has_no_stay_and_money_is_redistributed():
    b = bb.compute_breakdown(10000, 1, 2)
    got = {c["key"]: c["amount"] for c in b["categories"]}
    assert got["stay"] == 0 and sum(got.values()) == 10000 and got["activities"] > 2000
    assert "day trip" in next(c["detail"] for c in b["categories"] if c["key"] == "stay")


def test_details_use_people_days_and_rooms():
    b = bb.compute_breakdown(24000, 4, 3, "balanced")        # 3 people -> 2 rooms, 3 nights
    d = {c["key"]: c["detail"] for c in b["categories"]}
    assert "2 rooms, 3 nights" in d["stay"]
    assert "₹400 per person per day" in d["food"]            # 24000*20% = 4800 / (4 days * 3 people)


def test_warns_when_food_or_stay_is_very_low():
    b = bb.compute_breakdown(6000, 4, 3, "balanced")
    assert any("Food budget" in w for w in b["warnings"]) and any("Stay budget" in w for w in b["warnings"])
    assert bb.compute_breakdown(60000, 3, 2)["warnings"] == []


def test_indian_number_grouping():
    assert bb.inr(950) == "₹950" and bb.inr(12345) == "₹12,345" and bb.inr(1234567) == "₹12,34,567"


def test_tiny_or_odd_inputs_do_not_crash():
    b = bb.compute_breakdown(5, 0, 0)
    assert b["days"] == 1 and b["people"] == 1 and sum(c["amount"] for c in b["categories"]) == 5
