from datetime import date, timedelta

from app import analytics as an
from app.entries import Entry

KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")
END = date(2026, 9, 17)


def _entry(days_ago, each=None, status=None, **scores):
    values = {k: each for k in KEYS}
    values.update(scores)
    return Entry(id=1000 - days_ago, animal_id=1, entry_date=END - timedelta(days=days_ago),
                 day_status=status, weight=None, weight_unit=None, appetite=None, notes=None, **values)


def _pts(values_by_days_ago):
    return sorted((an.Point(END - timedelta(days=d), v) for d, v in values_by_days_ago.items()), key=lambda p: p.day)


def test_overall_points_skip_unscored_entries():
    entries = [_entry(0, 6), _entry(1), _entry(2, 4, hurt=None)]
    pts = an.overall_points(entries)
    assert [p.value for p in pts] == [4.0, 6.0]  # oldest first; the all-None entry is skipped


def test_rolling_mean_uses_calendar_window_and_min_points():
    pts = _pts({10: 8, 9: 8, 8: 8, 2: 4, 1: 4, 0: 4})
    smoothed = an.rolling_mean(pts, window_days=7, min_points=3)
    assert smoothed[2] == 8.0            # three points within 7 days
    assert smoothed[3] is None           # day -2: only one point in its 7-day window
    assert smoothed[5] == 4.0            # last three days


def test_ewma_decays_by_elapsed_time():
    pts = _pts({20: 8, 0: 2})
    assert an.ewma(pts, halflife_days=5)[-1] < 3.0   # 20 days later the old value barely counts
    pts2 = _pts({1: 8, 0: 2})
    assert an.ewma(pts2, halflife_days=5)[-1] > 6.0  # one day later it still dominates


def test_sufficiency_levels():
    assert an.sufficiency([], END).level == "none"
    few = _pts({0: 5, 1: 5, 2: 5})
    assert an.sufficiency(few, END).level == "limited"
    many = _pts({d: 5 for d in range(0, 24, 2)})
    assert an.sufficiency(many, END).level == "adequate"


def test_missing_days_are_not_interpolated():
    pts = _pts({0: 2, 14: 8})
    comp = an.period_comparison(pts, END)
    assert comp.recent_n == 1 and comp.previous_n == 1
    assert not comp.usable


def test_classify_insufficient_with_sparse_data():
    pts = _pts({0: 3, 1: 3, 2: 3})
    assert an.classify(pts, END).kind == "insufficient_data"


def test_single_bad_day_is_not_a_decline():
    values = {d: 7.0 for d in range(0, 30)}
    values[0] = 2.0
    cls = an.classify(_pts(values), END)
    assert cls.kind == "temporary_fluctuation"


def test_sustained_lower_scores_are_a_gradual_decline():
    values = {d: 7.0 for d in range(7, 30)}
    values.update({d: 5.5 for d in range(0, 7)})
    cls = an.classify(_pts(values), END)
    assert cls.kind == "gradual_down"
    assert cls.comparison.delta == -1.5


def test_sustained_higher_scores_are_a_gradual_improvement():
    values = {d: 4.0 for d in range(7, 30)}
    values.update({d: 6.0 for d in range(0, 7)})
    assert an.classify(_pts(values), END).kind == "gradual_up"


def test_direction_must_be_consistent():
    # Mean drops mainly because of two very bad days; most recent days match the old level.
    values = {d: 7.0 for d in range(7, 30)}
    values.update({0: 7, 1: 7, 2: 0, 3: 7, 4: 0, 5: 7, 6: 7})
    cls = an.classify(_pts(values), END)
    assert cls.kind != "gradual_down"


def test_increased_variability():
    values = {d: 6.0 for d in range(7, 30)}
    values.update({0: 9, 1: 3, 2: 9, 3: 3, 4: 9, 5: 3, 6: 9})
    assert an.classify(_pts(values), END).kind == "increased_variability"


def test_stable():
    values = {d: 6.0 + (0.2 if d % 2 else -0.2) for d in range(0, 30)}
    assert an.classify(_pts(values), END).kind == "stable"


def test_day_counts_and_not_logged():
    entries = [_entry(0, status="good"), _entry(1, status="bad"), _entry(3, status="mixed"), _entry(40, status="good")]
    counts = an.day_counts(entries, END - timedelta(days=29), END)
    assert (counts.good, counts.mixed, counts.bad) == (1, 1, 1)
    assert counts.logged == 3
    assert counts.not_logged == 27


class _M:
    def __init__(self, id, label): self.id, self.label = id, label


def test_marker_rates_only_count_answered_days():
    entries = [_entry(0), _entry(1), _entry(2)]
    responses = {1000: {1: True, 2: False}, 999: {1: False, 2: False}}  # day -2 has no answers
    rates = an.marker_rates(entries, responses, [_M(1, "Greets me"), _M(2, "Finishes dinner")],
                            END - timedelta(days=29), END)
    assert rates[0].completed == 1 and rates[0].logged == 2 and rates[0].pct == 50
    assert rates[1].pct == 0


def test_below_baseline_and_event_effect():
    pts = _pts({d: 4.0 for d in range(0, 12)})
    assert an.below_baseline(pts, 7.0) == (12, 12)
    comfort = _pts({**{d: 3.0 for d in range(14, 28)}, **{d: 6.0 for d in range(0, 14)}})
    eff = an.event_effect(comfort, END - timedelta(days=13))
    assert eff.usable and eff.delta == 3.0
