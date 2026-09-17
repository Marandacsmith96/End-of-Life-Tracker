"""Home, the Today dashboard, and the shortcut routes used by the navigation."""
from datetime import date, timedelta

from flask import Blueprint, g, redirect, render_template, request, session, url_for

from .. import analytics as an
from .. import baseline as bl
from .. import caregiver, charts, entries, events, insights, markers, models, scoring
from ..helpers import animal_or_404, current_or_choose, redirect_to_pet, resolve_range

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def home():
    active = models.list_animals()
    everyone = models.list_animals(include_archived=True)
    if not everyone:
        return render_template("landing.html", attribution=scoring.ATTRIBUTION)
    animal = current_or_choose()
    if animal and animal.status == "active":
        return redirect(url_for("dashboard.today", animal_id=animal.id))
    return render_template("pets.html", animals=active,
                           others=[a for a in everyone if a.status != "active"])


@bp.route("/pets")
def pets():
    everyone = models.list_animals(include_archived=True)
    return render_template("pets.html", animals=[a for a in everyone if a.status == "active"],
                           others=[a for a in everyone if a.status != "active"])


@bp.route("/how-it-works")
def landing():
    return render_template("landing.html", attribution=scoring.ATTRIBUTION)


@bp.route("/animals/<int:animal_id>/today")
def today(animal_id: int):
    animal = animal_or_404(animal_id)
    session["current_animal_id"] = animal_id
    g.current_animal = animal  # so this response's navigation already reflects the choice
    end = animal.passed_date or date.today()
    start, _, preset = resolve_range(request.args.get("range"), None, None, today=end, default="90")
    all_entries = entries.list_entries(animal_id)
    in_range = [e for e in all_entries if (start is None or e.entry_date >= start) and e.entry_date <= end]
    today_entry = entries.get_entry_for_date(animal_id, date.today()) if not animal.archived else None
    marker_list = markers.list_markers(animal_id)
    responses = markers.responses_for_animal(animal_id)
    base = bl.get_baseline(animal_id)
    event_list = events.list_events(animal_id, start=start, end=end, newest_first=False)
    month = an.day_counts(all_entries, end - timedelta(days=29), end)
    week = an.day_counts(all_entries, end - timedelta(days=6), end)
    classification, trend_text = insights.trend_summary(all_entries, end, animal.name)
    observations = insights.generate(all_entries, end, animal.name, marker_list, responses, base,
                                     events.list_events(animal_id), today_entry)
    rates = an.marker_rates(all_entries, responses, marker_list, end - timedelta(days=29), end)
    done_today, total_markers = an.markers_today(today_entry.id if today_entry else None, responses, marker_list)
    recent_mean, recent_n = an.window_mean(an.overall_points(all_entries), end - timedelta(days=6), end)
    return render_template(
        "dashboard.html", animal=animal, today_entry=today_entry, month=month, week=week,
        series=charts.build_series(in_range, start, end, base, event_list),
        classification=classification, trend_text=trend_text, observations=observations,
        rates=rates, done_today=done_today, total_markers=total_markers,
        recent_mean=recent_mean, recent_n=recent_n, baseline=base, preset=preset,
        recent_events=events.list_events(animal_id)[:3],
        caregiver_due=(not animal.archived and all_entries and caregiver.is_due(animal_id)),
        recent_entries=all_entries[:7], day_labels=entries.DAY_STATUS_LABELS,
        last_entry=all_entries[0] if all_entries else None, attribution=scoring.ATTRIBUTION,
    )


# Shortcuts used by the bottom navigation: they resolve the current pet.
@bp.route("/today")
def today_shortcut():
    return redirect_to_pet("dashboard.today")


@bp.route("/trends")
def trends_shortcut():
    return redirect_to_pet("trends.trends")


@bp.route("/calendar")
def calendar_shortcut():
    return redirect_to_pet("trends.calendar")


@bp.route("/vet")
def vet_shortcut():
    return redirect_to_pet("export.vet")


@bp.route("/more")
def more():
    animal = current_or_choose()
    return render_template("more.html", animal=animal, animals=models.list_animals(include_archived=True))
