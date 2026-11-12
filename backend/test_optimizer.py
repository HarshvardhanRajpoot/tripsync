from optimizer import optimize, PlaceIn, MemberIn

PLACES = [
    PlaceIn(1, "Fort", "sightseeing", 300, 4.6, 26.92, 75.82),
    PlaceIn(2, "Palace", "sightseeing", 500, 4.5, 26.93, 75.82),
    PlaceIn(3, "Street Food Lane", "food", 200, 4.2, 26.92, 75.83),
    PlaceIn(4, "Fine Dining", "food", 3000, 4.8, 26.91, 75.80),
    PlaceIn(5, "Zipline Park", "adventure", 1500, 4.4, 26.99, 75.90),
    PlaceIn(6, "Museum", "sightseeing", 100, 4.0, 26.92, 75.81),
    PlaceIn(7, "Cafe Row", "food", 400, 4.1, 26.90, 75.79),
]

def test_respects_budget_and_slots():
    ms = [MemberIn("A", ["food"], "relaxed"), MemberIn("B", ["culture"], "relaxed")]
    plan = optimize(PLACES, ms, budget=4000, days=2)
    assert plan.total_cost <= 4000
    assert len(plan.items) <= 4                 # 2 days x 2 per day
    assert all(1 <= i.day <= 2 for i in plan.items)

def test_must_see_is_forced_in():
    ms = [MemberIn("A", ["food"], "relaxed", must_see=["zipline"])]
    plan = optimize(PLACES, ms, budget=3000, days=2)
    assert any(i.name == "Zipline Park" for i in plan.items)

def test_unmatched_must_see_reported():
    ms = [MemberIn("A", ["food"], must_see=["Eiffel Tower"])]
    plan = optimize(PLACES, ms, budget=3000, days=2)
    assert plan.unmatched_must_sees == ["Eiffel Tower"]

def test_replan_excludes_closed_place_and_uses_remaining_days():
    ms = [MemberIn("A", ["culture"], "moderate")]
    first = optimize(PLACES, ms, budget=3000, days=3)
    closed = first.items[0].place_id
    again = optimize(PLACES, ms, budget=2000, days=2, start_day=2, exclude_ids={closed})
    assert closed not in [i.place_id for i in again.items]
    assert all(i.day >= 2 for i in again.items)
    assert again.total_cost <= 2000

def test_group_cost_scales_with_members():
    solo = optimize(PLACES, [MemberIn("A", ["culture"])], budget=10000, days=1)
    duo = optimize(PLACES, [MemberIn("A", ["culture"]), MemberIn("B", ["culture"])], budget=10000, days=1)
    assert duo.items[0].group_cost == 2 * solo.items[0].group_cost or duo.items[0].place_id != solo.items[0].place_id

def test_tiny_budget_gives_empty_plan_not_crash():
    plan = optimize(PLACES, [MemberIn("A", ["food"])], budget=10, days=2)
    assert plan.items == []
