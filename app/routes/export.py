"""PDF export for the vet."""
import io
import re
from datetime import date

from flask import Blueprint, abort, render_template, request, send_file

from .. import charts, entries, flags, models, pdf

bp = Blueprint("export", __name__)


@bp.route("/animals/<int:animal_id>/export")
def export_page(animal_id: int):
    animal = models.get_animal(animal_id)
    if animal is None:
        abort(404)
    start, end, preset = charts.resolve_range(
        request.args.get("range"), request.args.get("start"), request.args.get("end")
    )
    count = len(entries.list_entries(animal_id, start=start, end=end))
    return render_template(
        "export.html", animal=animal, start=start, end=end, preset=preset,
        presets=charts.RANGE_PRESETS, count=count,
    )


@bp.route("/animals/<int:animal_id>/export.pdf")
def export_pdf(animal_id: int):
    animal = models.get_animal(animal_id)
    if animal is None:
        abort(404)
    start, end, _ = charts.resolve_range(
        request.args.get("range"), request.args.get("start"), request.args.get("end")
    )
    rows = entries.list_entries(animal_id, start=start, end=end)
    med_names = {e.id: entries.medications_given_names(e.id) for e in rows}
    data = pdf.build_pdf(
        animal=animal,
        entries=rows,
        medications=entries.list_medications(animal_id),
        flags=[f for f in flags.for_animal(animal_id) if f.is_health],
        med_names=med_names,
        start=start,
        end=end,
    )
    safe_name = re.sub(r"[^A-Za-z0-9]+", "-", animal.name).strip("-") or "pet"
    filename = f"{safe_name}-quality-of-life-{end.isoformat()}.pdf"
    return send_file(
        io.BytesIO(data), mimetype="application/pdf",
        as_attachment=request.args.get("download") == "1", download_name=filename,
    )
