"""Personalized good-day behaviors: setup and trends."""
from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import analytics as an
from .. import entries, markers
from ..helpers import animal_or_404, resolve_range

bp = Blueprint("markers", __name__)


@bp.route("/animals/<int:animal_id>/markers", methods=("GET", "POST"))
def setup(animal_id: int):
    animal = animal_or_404(animal_id)
    onboarding = request.args.get("onboarding") == "1"
    current = markers.list_markers(animal_id)
    if request.method == "POST":
        labels = [x.strip() for x in request.form.getlist("labels") if x.strip()]
        seen, unique = set(), []
        for label in labels:  # de-duplicate case-insensitively, keep order
            if label.lower() not in seen:
                seen.add(label.lower())
                unique.append(label)
        labels = unique
        if len(labels) < markers.MIN_MARKERS:
            flash(f"Please choose at least {markers.MIN_MARKERS} behaviors.")
            return render_template("markers_setup.html", animal=animal, labels=labels,
                                   suggestions=markers.SUGGESTIONS.get(animal.species, []),
                                   onboarding=onboarding, min=markers.MIN_MARKERS, max=markers.MAX_MARKERS), 400
        if len(labels) > markers.MAX_MARKERS:
            flash(f"Please keep it to {markers.MAX_MARKERS} behaviors so check-ins stay quick.")
            return render_template("markers_setup.html", animal=animal, labels=labels,
                                   suggestions=markers.SUGGESTIONS.get(animal.species, []),
                                   onboarding=onboarding, min=markers.MIN_MARKERS, max=markers.MAX_MARKERS), 400
        if any(len(x) > 80 for x in labels):
            flash("Each behavior should be 80 characters or fewer.")
            return render_template("markers_setup.html", animal=animal, labels=labels,
                                   suggestions=markers.SUGGESTIONS.get(animal.species, []),
                                   onboarding=onboarding, min=markers.MIN_MARKERS, max=markers.MAX_MARKERS), 400
        markers.replace_markers(animal_id, labels)
        if onboarding:
            return redirect(url_for("baseline.edit", animal_id=animal_id, onboarding=1))
        flash("Saved.")
        return redirect(url_for("markers.behaviors", animal_id=animal_id))
    return render_template("markers_setup.html", animal=animal, labels=[m.label for m in current],
                           suggestions=markers.SUGGESTIONS.get(animal.species, []),
                           onboarding=onboarding, min=markers.MIN_MARKERS, max=markers.MAX_MARKERS)


@bp.route("/animals/<int:animal_id>/behaviors")
def behaviors(animal_id: int):
    animal = animal_or_404(animal_id)
    start, end, preset = resolve_range(request.args.get("range"), None, None, default="30")
    all_markers = markers.list_markers(animal_id, active_only=False)
    active = [m for m in all_markers if m.active]
    rows = entries.list_entries(animal_id)
    responses = markers.responses_for_animal(animal_id)
    window = (end - start).days + 1 if start else 30
    recent = an.marker_rates(rows, responses, active, start or date.min, end)
    previous = an.marker_rates(rows, responses, active,
                               (start - timedelta(days=window)) if start else date.min,
                               (start - timedelta(days=1)) if start else date.min)
    prev_by_id = {r.marker_id: r for r in previous}
    # Weekly completion series for the chart: for each marker, % per ISO week.
    series = []
    by_week: dict = {}
    for e in sorted(rows, key=lambda e: e.entry_date):
        if start and e.entry_date < start or e.entry_date > end:
            continue
        answers = responses.get(e.id)
        if not answers:
            continue
        week = e.entry_date - timedelta(days=e.entry_date.weekday())
        slot = by_week.setdefault(week, {m.id: [0, 0] for m in active})
        for m in active:
            if m.id in answers:
                slot[m.id][1] += 1
                slot[m.id][0] += int(answers[m.id])
    weeks = sorted(by_week)
    for m in active:
        series.append({
            "label": m.label,
            "values": [round(100 * by_week[w][m.id][0] / by_week[w][m.id][1]) if by_week[w][m.id][1] else None
                       for w in weeks],
        })
    return render_template(
        "behaviors.html", animal=animal, recent=recent, prev_by_id=prev_by_id, start=start, end=end,
        preset=preset, window=window, weeks=[w.isoformat() for w in weeks], series=series,
        inactive=[m for m in all_markers if not m.active],
    )


@bp.post("/markers/<int:marker_id>/restore")
def restore(marker_id: int):
    m = markers.get_marker(marker_id)
    if m is None:
        return redirect(url_for("dashboard.home"))
    if len(markers.list_markers(m.animal_id)) >= markers.MAX_MARKERS:
        flash(f"You already have {markers.MAX_MARKERS} active behaviors. Remove one first.")
    else:
        markers.set_marker_active(marker_id, True)
        flash("Behavior restored.")
    return redirect(url_for("markers.behaviors", animal_id=m.animal_id))
