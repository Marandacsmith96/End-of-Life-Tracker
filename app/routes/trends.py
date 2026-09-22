"""Trends, individual category views, and the good/bad day calendar."""
import calendar as cal
from datetime import date, timedelta

from flask import Blueprint, abort, render_template, request

from .. import analytics as an
from .. import baseline as bl
from .. import charts, entries, events, insights, markers, scoring
from ..helpers import animal_or_404, parse_date, resolve_range

bp = Blueprint("trends", __name__)


@bp.route("/animals/<int:animal_id>/trends")
def trends(animal_id: int):
    animal = animal_or_404(animal_id)
    end_default = animal.passed_date or date.today()
    start, end, preset = resolve_range(request.args.get("range"), request.args.get("start"),
                                       request.args.get("end"), today=end_default, default="90")
    all_entries = entries.list_entries(animal_id)
    rows = [e for e in all_entries if (start is None or e.entry_date >= start) and e.entry_date <= end]
    base = bl.get_baseline(animal_id)
    event_list = events.list_events(animal_id, start=start, end=end, newest_first=False)
    marker_list = markers.list_markers(animal_id)
    responses = markers.responses_for_animal(animal_id)
    classification, trend_text = insights.trend_summary(all_entries, end, animal.name)
    cat_summaries = []
    for key, label, *_ in scoring.CATEGORIES:
        pts = an.category_points(rows, key)
        comp = an.period_comparison(an.category_points(all_entries, key), end)
        cat_summaries.append({"key": key, "label": label, "n": len(pts),
                              "latest": pts[-1].value if pts else None, "comparison": comp,
                              "baseline": getattr(base, key) if base else None})
    counts = an.day_counts(rows, start or (rows[-1].entry_date if rows else end), end)
    rates = an.marker_rates(all_entries, responses, marker_list, end - timedelta(days=29), end)
    return render_template(
        "trends.html", animal=animal, start=start, end=end, preset=preset,
        series=charts.build_series(rows, start, end, base, event_list),
        weekly=charts.weekly_day_counts(rows, start or (rows[-1].entry_date if rows else end), end),
        classification=classification, trend_text=trend_text, categories=cat_summaries,
        counts=counts, rates=rates, event_list=event_list, baseline=base,
        med_names=entries.medications_given_names_for_animal(animal_id),
        rows=rows, day_labels=entries.DAY_STATUS_LABELS, appetite_labels=scoring.APPETITE_LABELS,
    )


@bp.route("/animals/<int:animal_id>/trends/<key>")
def category(animal_id: int, key: str):
    animal = animal_or_404(animal_id)
    if key not in scoring.CATEGORY_KEYS:
        abort(404)
    end_default = animal.passed_date or date.today()
    start, end, preset = resolve_range(request.args.get("range"), None, None, today=end_default, default="90")
    all_entries = entries.list_entries(animal_id)
    rows = [e for e in all_entries if (start is None or e.entry_date >= start) and e.entry_date <= end]
    base = bl.get_baseline(animal_id)
    pts = an.category_points(rows, key)
    all_pts = an.category_points(all_entries, key)
    classification = an.classify(all_pts, end)
    text = insights.TREND_TEXT[classification.kind].replace("Scores", f"{scoring.CATEGORY_LABELS[key]} scores")
    baseline_value = getattr(base, key) if base else None
    below = an.below_baseline(all_pts, baseline_value) if baseline_value is not None else None
    idx = scoring.CATEGORY_KEYS.index(key)
    return render_template(
        "category.html", animal=animal, key=key, label=scoring.CATEGORY_LABELS[key],
        guidance=scoring.CATEGORY_GUIDANCE[key], anchors=scoring.CATEGORY_ANCHORS[key],
        start=start, end=end, preset=preset,
        series={"dates": [p.day.isoformat() for p in pts], "values": [p.value for p in pts],
                "smoothed": an.rolling_mean(pts), "baseline": baseline_value,
                "events": [{"date": e.event_date.isoformat(), "title": e.title}
                           for e in events.list_events(animal_id, start=start, end=end)],
                "start": (start or (pts[0].day if pts else end)).isoformat(), "end": end.isoformat(),
                "sufficiency": an.sufficiency(all_pts, end).level},
        classification=classification, text=text, below=below, baseline=base,
        prev_key=scoring.CATEGORY_KEYS[idx - 1] if idx > 0 else None,
        next_key=scoring.CATEGORY_KEYS[idx + 1] if idx < len(scoring.CATEGORY_KEYS) - 1 else None,
        labels=scoring.CATEGORY_LABELS, points=list(reversed(pts))[:60],
    )


@bp.route("/animals/<int:animal_id>/calendar")
def calendar(animal_id: int):
    animal = animal_or_404(animal_id)
    today = animal.passed_date or date.today()
    month_raw = request.args.get("month")
    try:
        year, month = (int(x) for x in month_raw.split("-")) if month_raw else (today.year, today.month)
        first = date(year, month, 1)
    except (ValueError, AttributeError):
        first = date(today.year, today.month, 1)
    last = date(first.year, first.month, cal.monthrange(first.year, first.month)[1])
    rows = entries.list_entries(animal_id, start=first - timedelta(days=7), end=last)
    by_date = {e.entry_date: e for e in rows}
    weeks = []
    for week in cal.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month):
        weeks.append([{"date": d, "in_month": d.month == first.month, "entry": by_date.get(d),
                       "future": d > date.today()} for d in week])
    all_entries = entries.list_entries(animal_id)
    this_month = an.day_counts(all_entries, first, last)
    prev_first = (first - timedelta(days=1)).replace(day=1)
    prev_last = first - timedelta(days=1)
    prev_month = an.day_counts(all_entries, prev_first, prev_last)
    last30 = an.day_counts(all_entries, today - timedelta(days=29), today)
    prev30 = an.day_counts(all_entries, today - timedelta(days=59), today - timedelta(days=30))
    event_days = {e.event_date for e in events.list_events(animal_id, start=first, end=last)}
    return render_template(
        "calendar.html", animal=animal, first=first, weeks=weeks, this_month=this_month,
        prev_month=prev_month, prev_first=prev_first, last30=last30, prev30=prev30,
        prev_link=prev_first.strftime("%Y-%m"),
        next_link=(last + timedelta(days=1)).strftime("%Y-%m") if last < date.today() else None,
        month_name=first.strftime("%B %Y"), event_days=event_days, day_labels=entries.DAY_STATUS_LABELS,
    )
