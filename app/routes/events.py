"""Timeline events."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import events
from ..helpers import animal_or_404, parse_date
from .auth import safe_next

bp = Blueprint("events", __name__)


def _parse(form):
    errors = []
    when = parse_date(form.get("event_date"))
    if when is None:
        errors.append("Please choose a valid date.")
    elif when > date.today():
        errors.append("Events can't be in the future.")
    type_ = form.get("type", "other")
    if type_ not in events.EVENT_LABELS:
        errors.append("Please choose an event type.")
    title = form.get("title", "").strip()
    if not title:
        title = events.EVENT_LABELS.get(type_, "Event")
    if len(title) > 120:
        errors.append("Titles must be 120 characters or fewer.")
    note = form.get("note", "").strip() or None
    return {"event_date": when, "type_": type_, "title": title, "note": note}, errors


@bp.route("/animals/<int:animal_id>/events")
def timeline(animal_id: int):
    animal = animal_or_404(animal_id)
    return render_template("events.html", animal=animal, events=events.list_events(animal_id))


@bp.route("/animals/<int:animal_id>/events/new", methods=("GET", "POST"))
def new(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        values, errors = _parse(request.form)
        if errors:
            for m in errors:
                flash(m)
            return render_template("event_form.html", animal=animal, event=None, values=request.form,
                                   types=events.EVENT_TYPES, today=date.today().isoformat()), 400
        events.create_event(animal_id, **values)
        flash("Event added.")
        return redirect(safe_next(request.form.get("next")) or url_for("events.timeline", animal_id=animal_id))
    values = {"event_date": (parse_date(request.args.get("date")) or date.today()).isoformat(),
              "type": request.args.get("type", "vet_visit")}
    return render_template("event_form.html", animal=animal, event=None, values=values,
                           types=events.EVENT_TYPES, today=date.today().isoformat())


@bp.route("/events/<int:event_id>/edit", methods=("GET", "POST"))
def edit(event_id: int):
    ev = events.get_event(event_id)
    if ev is None:
        abort(404)
    animal = animal_or_404(ev.animal_id)
    if request.method == "POST":
        values, errors = _parse(request.form)
        if errors:
            for m in errors:
                flash(m)
            return render_template("event_form.html", animal=animal, event=ev, values=request.form,
                                   types=events.EVENT_TYPES, today=date.today().isoformat()), 400
        events.update_event(event_id, **values)
        flash("Event saved.")
        return redirect(url_for("events.timeline", animal_id=ev.animal_id))
    values = {"event_date": ev.event_date.isoformat(), "type": ev.type, "title": ev.title, "note": ev.note or ""}
    return render_template("event_form.html", animal=animal, event=ev, values=values,
                           types=events.EVENT_TYPES, today=date.today().isoformat())


@bp.post("/events/<int:event_id>/delete")
def delete(event_id: int):
    ev = events.get_event(event_id)
    if ev is None:
        abort(404)
    events.delete_event(event_id)
    flash("Event removed.")
    return redirect(url_for("events.timeline", animal_id=ev.animal_id))
