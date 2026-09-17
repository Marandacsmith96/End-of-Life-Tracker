"""Owner-estimated baseline from about six months ago."""
from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import baseline as bl
from .. import scoring
from ..helpers import animal_or_404, parse_date

bp = Blueprint("baseline", __name__)


@bp.route("/animals/<int:animal_id>/baseline", methods=("GET", "POST"))
def edit(animal_id: int):
    animal = animal_or_404(animal_id)
    onboarding = request.args.get("onboarding") == "1"
    existing = bl.get_baseline(animal_id)
    if request.method == "POST":
        if request.form.get("skip") == "1":
            return redirect(url_for("animals.ready", animal_id=animal_id) if onboarding
                            else url_for("animals.settings", animal_id=animal_id))
        errors = []
        scores = {}
        for key in scoring.CATEGORY_KEYS:
            raw = request.form.get(key, "").strip()
            if raw == "":
                scores[key] = None
            elif scoring.is_valid_score(raw):
                scores[key] = int(raw)
            else:
                errors.append(f"{scoring.CATEGORY_LABELS[key]} must be a whole number from 0 to 10.")
        approx = parse_date(request.form.get("approximate_date"))
        pattern = request.form.get("good_day_pattern") or None
        freq = request.form.get("marker_frequency") or None
        if pattern and pattern not in dict(bl.GOOD_DAY_PATTERNS):
            errors.append("Please choose a valid good-day pattern.")
        if freq and freq not in dict(bl.MARKER_FREQUENCIES):
            errors.append("Please choose a valid frequency.")
        notes = request.form.get("notes", "").strip() or None
        if errors:
            for m in errors:
                flash(m)
            return _render(animal, request.form, onboarding), 400
        bl.save_baseline(animal_id, approx, scores, pattern, freq, notes)
        if onboarding:
            return redirect(url_for("animals.ready", animal_id=animal_id))
        flash("Baseline saved.")
        return redirect(url_for("animals.settings", animal_id=animal_id))
    values = {}
    if existing:
        values = {k: ("" if v is None else v) for k, v in existing.scores.items()}
        values.update(approximate_date=existing.approximate_date.isoformat() if existing.approximate_date else "",
                      good_day_pattern=existing.good_day_pattern or "",
                      marker_frequency=existing.marker_frequency or "", notes=existing.notes or "")
    else:
        values["approximate_date"] = (date.today() - timedelta(days=182)).isoformat()
    return _render(animal, values, onboarding)


def _render(animal, values, onboarding):
    return render_template(
        "baseline_form.html", animal=animal, values=values, onboarding=onboarding,
        has_baseline=bl.get_baseline(animal.id) is not None,
        categories=scoring.CATEGORIES, patterns=bl.GOOD_DAY_PATTERNS, frequencies=bl.MARKER_FREQUENCIES,
    )


@bp.post("/animals/<int:animal_id>/baseline/delete")
def delete(animal_id: int):
    animal_or_404(animal_id)
    bl.delete_baseline(animal_id)
    flash("Baseline removed.")
    return redirect(url_for("animals.settings", animal_id=animal_id))
