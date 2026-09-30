"""Small helpers shared by the route modules."""
from datetime import date, timedelta

from flask import abort, g, redirect, session, url_for

from . import models

RANGE_PRESETS = {"7": 7, "30": 30, "90": 90, "all": None}


MIN_YEAR, MAX_YEAR = 1900, 2100


def parse_date(raw: str | None) -> date | None:
    """ISO date within 1900..2100, else None (dates near the calendar's edges
    overflow the date arithmetic used all over the app)."""
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw.strip())
    except ValueError:
        return None
    return parsed if MIN_YEAR <= parsed.year <= MAX_YEAR else None


def animal_or_404(animal_id: int) -> models.Animal:
    animal = models.get_animal(animal_id)
    if animal is None:
        abort(404)
    return animal


def resolve_range(preset: str | None, start_raw: str | None, end_raw: str | None,
                  today: date | None = None, default: str = "90"):
    """(start, end, preset_name). Start is None for 'all'."""
    today = today or date.today()
    start = parse_date(start_raw)
    end = parse_date(end_raw) or today
    if start is not None:
        if start > end:
            start, end = end, start
        return start, end, "custom"
    preset = preset if preset in RANGE_PRESETS else default
    days = RANGE_PRESETS[preset]
    if days is None:
        return None, end, "all"
    return end - timedelta(days=days - 1), end, preset


def current_or_choose():
    """Redirect helper for the shortcut routes (/today, /trends, ...)."""
    if g.current_animal:
        return g.current_animal
    active = models.list_animals()
    if len(active) == 1:
        session["current_animal_id"] = active[0].id
        return active[0]
    return None


def redirect_to_pet(endpoint: str, **kwargs):
    animal = current_or_choose()
    if animal is None:
        return redirect(url_for("dashboard"))
    return redirect(url_for(endpoint, animal_id=animal.id, **kwargs))
