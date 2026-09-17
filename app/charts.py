"""Series for the on-screen charts and the PDF, built from the analytics module."""
from datetime import date, timedelta

from . import analytics as an
from .baseline import Baseline
from .entries import Entry
from .events import Event
from .scoring import CATEGORIES

KG_PER_LB = 0.45359237


def to_unit(value: float, from_unit: str, to_unit_: str) -> float:
    if from_unit == to_unit_:
        return value
    if from_unit == "lb" and to_unit_ == "kg":
        return value * KG_PER_LB
    if from_unit == "kg" and to_unit_ == "lb":
        return value / KG_PER_LB
    raise ValueError(f"Unknown units {from_unit!r} -> {to_unit_!r}")


def weight_unit_for(entries: list[Entry]) -> str | None:
    for entry in sorted(entries, key=lambda e: e.entry_date, reverse=True):
        if entry.weight is not None and entry.weight_unit:
            return entry.weight_unit
    return None


def build_series(entries: list[Entry], start: date | None, end: date,
                 baseline: Baseline | None = None, events: list[Event] = ()) -> dict:
    """Everything the trend chart needs, JSON-serialisable.

    Raw points and the smoothed line are separate so the chart can always
    show the observations; the smoothed line is None where the window holds
    too few points (visible uncertainty).
    """
    ordered = sorted(entries, key=lambda e: e.entry_date)
    overall = an.overall_points(ordered)
    smoothed = an.rolling_mean(overall)
    suff = an.sufficiency(overall, end)
    unit = weight_unit_for(ordered)
    weighed = [(e.entry_date, round(to_unit(e.weight, e.weight_unit or unit, unit), 2))
               for e in ordered if e.weight is not None and unit]
    return {
        "start": (start or (overall[0].day if overall else end)).isoformat(),
        "end": end.isoformat(),
        "overall": {
            "dates": [p.day.isoformat() for p in overall],
            "values": [p.value for p in overall],
            "smoothed": smoothed,
            "sufficiency": suff.level,
        },
        "categories": [
            {
                "key": key, "label": label,
                "dates": [p.day.isoformat() for p in an.category_points(ordered, key)],
                "values": [p.value for p in an.category_points(ordered, key)],
                "smoothed": an.rolling_mean(an.category_points(ordered, key)),
                "baseline": getattr(baseline, key) if baseline else None,
            }
            for key, label, *_ in CATEGORIES
        ],
        "days": [{"date": d.isoformat(), "status": s} for d, s in an.day_status_points(ordered)],
        "baseline": {"value": baseline.mean, "label": baseline.label} if baseline and baseline.mean is not None else None,
        "events": [{"date": e.event_date.isoformat(), "title": e.title, "type": e.type_label} for e in events],
        "weight": {"unit": unit, "dates": [d.isoformat() for d, _ in weighed], "values": [w for _, w in weighed]},
        "reference": 5.0,
    }


def weekly_day_counts(entries: list[Entry], start: date, end: date) -> list[dict]:
    """Good/mixed/bad counts per week, oldest first, for the stacked bar chart."""
    out = []
    week_start = start - timedelta(days=start.weekday())
    while week_start <= end:
        week_end = week_start + timedelta(days=6)
        c = an.day_counts(entries, max(week_start, start), min(week_end, end))
        out.append({"week": week_start.isoformat(), "good": c.good, "mixed": c.mixed, "bad": c.bad})
        week_start += timedelta(days=7)
    return out
