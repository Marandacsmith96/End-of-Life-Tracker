from datetime import date, timedelta

from app import insights, safety
from app.baseline import Baseline
from app.entries import Entry
from app.events import Event

KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")
END = date(2026, 9, 17)


def _entry(days_ago, each=6, status="good", **scores):
    values = {k: each for k in KEYS}
    values.update(scores)
    return Entry(id=1000 - days_ago, animal_id=1, entry_date=END - timedelta(days=days_ago),
                 day_status=status, weight=None, weight_unit=None, appetite=None, notes=None, **values)


def _all_safe(items):
    for i in items:
        assert safety.is_safe(i.text), i.text


def test_insufficient_data_is_the_only_insight_when_sparse():
    items = insights.generate([_entry(0), _entry(1)], END, "Maggie")
    assert items[0].kind == "trend"
    assert "enough information" in items[0].text
    _all_safe(items)


def test_decline_produces_attention_and_guidance_only():
    entries = [_entry(d, 7, "good") for d in range(7, 30)] + [_entry(d, 5, "bad", mobility=3, hunger=7) for d in range(0, 7)]
    items = insights.generate(entries, END, "Maggie")
    kinds = {i.kind for i in items}
    assert "trend" in kinds and "days" in kinds and "category" in kinds
    assert items[-1].text == safety.MAX_GUIDANCE
    assert any("Mobility scores have been lower" in i.text for i in items)
    assert any("Appetite scores have remained relatively stable" in i.text for i in items)
    _all_safe(items)


def test_baseline_and_event_insights():
    entries = [_entry(d, 6, mobility=4, hurt=3 if d >= 14 else 6) for d in range(0, 30)]
    baseline = Baseline(1, None, 8, 8, 8, 8, 8, 8, 8, None, None, None)
    ev = Event(1, 1, END - timedelta(days=13), "pain_medication_started", "Started gabapentin", None)
    items = insights.generate(entries, END, "Maggie", baseline=baseline, events=[ev])
    assert any(i.kind == "baseline" and "Mobility has been below Maggie's earlier baseline" in i.text for i in items)
    assert any(i.kind == "event" and "Comfort scores improved" in i.text for i in items)
    _all_safe(items)


def test_marker_insights():
    class M:
        def __init__(self, id, label): self.id, self.label = id, label
    entries = [_entry(d) for d in range(0, 60)]
    responses = {}
    for e in entries:
        days_ago = (END - e.entry_date).days
        responses[e.id] = {1: days_ago >= 30 or days_ago % 4 == 0}  # ~100% last month, ~25% this month
    items = insights.generate(entries, END, "Maggie", markers=[M(1, "Gets onto the couch herself")],
                              responses=responses, today_entry=entries[0])
    assert any("decreased from 100% of logged days last month to 27% this month" in i.text for i in items)
    assert any("did 1 of 1 of their usual good-day behaviors today" in i.text for i in items)
    _all_safe(items)


def test_discussion_points_are_safe_and_specific():
    entries = [_entry(d, 7) for d in range(7, 30)] + [_entry(d, 5, "bad") for d in range(0, 7)]
    points = insights.discussion_points(entries, END, "Maggie")
    assert points
    for p in points:
        assert safety.is_safe(p)
