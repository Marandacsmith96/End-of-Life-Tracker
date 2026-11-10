"""Supplements: what is being given, which signs to watch, and how those signs
have moved. Mark stopped / remove reuse the medication routes."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import entries, meds, signs
from ..helpers import animal_or_404, parse_date

bp = Blueprint("supplements", __name__)


@bp.route("/animals/<int:animal_id>/supplements", methods=("GET", "POST"))
def supplements(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        dose = request.form.get("dose", "").strip()[:80] or None
        schedule = request.form.get("schedule", "").strip()[:80] or None
        start = parse_date(request.form.get("start_date"))
        chosen = [k for k in request.form.getlist("signs") if k in signs.SIGN_BY_KEY]
        errors = []
        if not name:
            errors.append("Please enter the supplement's name.")
        if not chosen:
            errors.append("Pick at least one sign to watch, so there is something to compare.")
        if errors:
            for message in errors:
                flash(message)
            return render_template("supplements.html", **_context(animal, values=request.form)), 400
        entries.create_medication(animal_id, name, dose, schedule, start, kind="supplement", signs=chosen)
        flash(f"{name} added. Its signs now appear in the daily check-in under \"More details\".")
        return redirect(url_for("supplements.supplements", animal_id=animal_id))
    return render_template("supplements.html", **_context(animal))


@bp.post("/animals/<int:animal_id>/supplements/signs")
def log_signs(animal_id: int):
    """Score today's (or a chosen day's) signs straight from the supplements page."""
    animal = animal_or_404(animal_id)
    if animal.archived:
        flash("This profile is no longer taking new entries.")
        return redirect(url_for("supplements.supplements", animal_id=animal_id))
    day = parse_date(request.form.get("entry_date")) or date.today()
    if day > date.today():
        day = date.today()
    values, errors = signs.parse_form(request.form)
    for message in errors:
        flash(message)
    if values:
        signs.save_signs(animal_id, day, values)
        flash(f"Signs saved for {day:%B} {day.day}.")
    elif not errors:
        flash("Move a slider to score a sign; untouched ones are not saved.")
    return redirect(url_for("supplements.supplements", animal_id=animal_id))


def _context(animal, values=None) -> dict:
    sups = entries.list_medications(animal.id, kind="supplement")
    all_entries = entries.list_entries(animal.id)
    end = animal.passed_date or date.today()
    today = date.today()
    return {
        "animal": animal,
        "supplements": sups,
        "views": signs.summarize(sups, all_entries, end),
        "given": {s.medication.id: s for s in meds.summarize(sups, all_entries, entries.given_days_for_animal(animal.id), end)},
        "signs": signs.SIGNS,
        "watched": signs.watched_signs(sups),
        "today_values": signs.signs_on(animal.id, today),
        "values": values or {},
        "chosen_signs": values.getlist("signs") if values is not None and hasattr(values, "getlist") else [],
        "today": today.isoformat(),
        "window_days": signs.WINDOW_DAYS,
    }
