"""Prepare for my vet visit, and the one-page vet summary PDF."""
import io
import re
from datetime import date, timedelta

from flask import Blueprint, render_template, request, send_file

from .. import analytics as an
from .. import baseline as bl
from .. import entries, events, insights, markers, pdf, safety, scoring
from ..helpers import animal_or_404, parse_date, resolve_range

bp = Blueprint("export", __name__)


def _prep(animal, since: date | None):
    """Comparison of the period since ``since`` against the same length before it."""
    end = animal.passed_date or date.today()
    all_entries = entries.list_entries(animal.id)
    last_visit = events.last_vet_visit(animal.id)
    if since is None:
        since = last_visit.event_date if last_visit and last_visit.event_date < end else end - timedelta(days=29)
    length = max((end - since).days + 1, 7)
    prev_start = since - timedelta(days=length)
    prev_end = since - timedelta(days=1)
    cats = []
    for key, label, *_ in scoring.CATEGORIES:
        pts = an.category_points(all_entries, key)
        recent, rn = an.window_mean(pts, since, end)
        previous, pn = an.window_mean(pts, prev_start, prev_end)
        delta = round(recent - previous, 1) if recent is not None and previous is not None else None
        if delta is None or rn < 3 or pn < 3:
            verdict = "Not enough entries to compare."
        elif abs(delta) < 0.5:
            verdict = "Relatively stable."
        elif delta < 0:
            verdict = f"Lower by {abs(delta):.1f}."
        else:
            verdict = f"Higher by {delta:.1f}."
        cats.append({"key": key, "label": label, "recent": recent, "previous": previous,
                     "recent_n": rn, "previous_n": pn, "text": safety.guard(verdict)})
    marker_list = markers.list_markers(animal.id)
    responses = markers.responses_for_animal(animal.id)
    recent_rates = an.marker_rates(all_entries, responses, marker_list, since, end)
    prev_rates = {r.marker_id: r for r in an.marker_rates(all_entries, responses, marker_list, prev_start, prev_end)}
    recent_days = an.day_counts(all_entries, since, end)
    prev_days = an.day_counts(all_entries, prev_start, prev_end)
    points = insights.discussion_points(all_entries, end, animal.name, marker_list, responses,
                                        bl.get_baseline(animal.id), events.list_events(animal.id))
    return {
        "since": since, "end": end, "prev_start": prev_start, "prev_end": prev_end, "cats": cats,
        "recent_rates": recent_rates, "prev_rates": prev_rates, "recent_days": recent_days,
        "prev_days": prev_days, "points": points, "last_visit": last_visit,
        "events": events.list_events(animal.id, start=since, end=end),
    }


@bp.route("/animals/<int:animal_id>/vet")
def vet(animal_id: int):
    animal = animal_or_404(animal_id)
    since = parse_date(request.args.get("since"))
    prep = _prep(animal, since)
    start, end, preset = resolve_range(request.args.get("range"), None, None,
                                       today=animal.passed_date or date.today(), default="90")
    count = len(entries.list_entries(animal_id, start=start, end=end))
    return render_template("vet.html", animal=animal, prep=prep, preset=preset, start=start, end=end,
                           count=count, report_note=safety.REPORT_NOTE, guidance=safety.MAX_GUIDANCE)


@bp.route("/animals/<int:animal_id>/export.pdf")
def export_pdf(animal_id: int):
    animal = animal_or_404(animal_id)
    end_default = animal.passed_date or date.today()
    start, end, _ = resolve_range(request.args.get("range"), request.args.get("start"),
                                  request.args.get("end"), today=end_default, default="90")
    all_entries = entries.list_entries(animal_id)
    rows = [e for e in all_entries if (start is None or e.entry_date >= start) and e.entry_date <= end]
    marker_list = markers.list_markers(animal_id)
    responses = markers.responses_for_animal(animal_id)
    data = pdf.build_pdf(
        animal=animal, entries=rows, all_entries=all_entries, medications=entries.list_medications(animal_id),
        markers=marker_list, responses=responses, baseline=bl.get_baseline(animal_id),
        events=events.list_events(animal_id, start=start, end=end, newest_first=False),
        start=start, end=end, include_appendix=request.args.get("appendix") == "1",
    )
    safe_name = re.sub(r"[^A-Za-z0-9]+", "-", animal.name).strip("-") or "pet"
    filename = f"{safe_name}-quality-of-life-{end.isoformat()}.pdf"
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     as_attachment=request.args.get("download") == "1", download_name=filename)
