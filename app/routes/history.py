"""History page: table of entries plus charts for a chosen date range."""
from flask import Blueprint, abort, render_template, request

from .. import charts, entries, models, scoring

bp = Blueprint("history", __name__)


@bp.route("/animals/<int:animal_id>/history")
def history(animal_id: int):
    animal = models.get_animal(animal_id)
    if animal is None:
        abort(404)
    start, end, preset = charts.resolve_range(
        request.args.get("range"), request.args.get("start"), request.args.get("end")
    )
    rows = entries.list_entries(animal_id, start=start, end=end, newest_first=True)
    med_names = {e.id: entries.medications_given_names(e.id) for e in rows}
    return render_template(
        "history.html",
        animal=animal,
        rows=rows,
        med_names=med_names,
        series=charts.build_series(rows),
        summary=charts.summarize(rows),
        start=start,
        end=end,
        preset=preset,
        presets=charts.RANGE_PRESETS,
        categories=scoring.CATEGORIES,
        appetite_labels=scoring.APPETITE_LABELS,
        max_total=scoring.MAX_TOTAL,
        threshold=scoring.ACCEPTABLE_TOTAL,
        describe_total=scoring.describe_total,
    )
