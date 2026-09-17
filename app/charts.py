"""Turn a list of entries into series the charts and PDF can draw.

Pure functions only: no Flask, no database, so they are easy to test.
"""
from datetime import date, timedelta

from .entries import Entry
from .scoring import CATEGORIES

KG_PER_LB = 0.45359237

RANGE_PRESETS = {
    "14": 14,
    "30": 30,
    "90": 90,
    "all": None,
}


def resolve_range(preset: str | None, start_raw: str | None, end_raw: str | None,
                  today: date | None = None) -> tuple[date | None, date, str]:
    """Work out the start/end dates from a preset ('30') or custom start/end.

    Returns (start, end, preset_name). Start is None for 'all'.
    """
    today = today or date.today()
    start = _parse(start_raw)
    end = _parse(end_raw) or today
    if start is not None:
        if start > end:
            start, end = end, start
        return start, end, "custom"
    preset = preset if preset in RANGE_PRESETS else "30"
    days = RANGE_PRESETS[preset]
    if days is None:
        return None, end, "all"
    return end - timedelta(days=days - 1), end, preset


def _parse(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def to_unit(value: float, from_unit: str, to_unit_: str) -> float:
    if from_unit == to_unit_:
        return value
    if from_unit == "lb" and to_unit_ == "kg":
        return value * KG_PER_LB
    if from_unit == "kg" and to_unit_ == "lb":
        return value / KG_PER_LB
    raise ValueError(f"Unknown units {from_unit!r} -> {to_unit_!r}")


def weight_unit_for(entries: list[Entry]) -> str | None:
    """The unit used on the most recent entry that has a weight."""
    for entry in sorted(entries, key=lambda e: e.entry_date, reverse=True):
        if entry.weight is not None and entry.weight_unit:
            return entry.weight_unit
    return None


def build_series(entries: list[Entry]) -> dict:
    """Series for the charts. Entries may be in any order; output is oldest first."""
    ordered = sorted(entries, key=lambda e: e.entry_date)
    labels = [e.entry_date.isoformat() for e in ordered]
    unit = weight_unit_for(ordered)
    weights = [
        None if e.weight is None else round(to_unit(e.weight, e.weight_unit or unit, unit), 2)
        for e in ordered
    ] if unit else [None for _ in ordered]
    return {
        "labels": labels,
        "total": [e.total for e in ordered],
        "categories": [
            {"key": key, "label": label, "values": [getattr(e, key) for e in ordered]}
            for key, label, _ in CATEGORIES
        ],
        "weight": {"unit": unit, "values": weights},
    }


def summarize(entries: list[Entry]) -> dict:
    """Headline numbers for the history page."""
    if not entries:
        return {"count": 0}
    ordered = sorted(entries, key=lambda e: e.entry_date)
    totals = [e.total for e in ordered]
    latest = ordered[-1]
    first_week = totals[:7]
    last_week = totals[-7:]
    return {
        "count": len(ordered),
        "latest_total": latest.total,
        "latest_date": latest.entry_date,
        "average": round(sum(totals) / len(totals), 1),
        "lowest": min(totals),
        "highest": max(totals),
        "trend": round(sum(last_week) / len(last_week) - sum(first_week) / len(first_week), 1)
        if len(ordered) >= 2 else 0.0,
    }
