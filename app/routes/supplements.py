"""Supplements: what is being given, which signs to watch, and how those signs
have moved. Mark stopped / remove reuse the medication routes."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import entries, meds, signs
from ..helpers import animal_or_404, parse_date

bp = Blueprint("supplements", __name__)


def _details(form) -> tuple[dict, list[str]]:
    """The fields an owner records about a supplement, with their problems."""
    source = form.get("source", "").strip() or None
    details = {
        "name": form.get("name", "").strip()[:80],
        "dose": form.get("dose", "").strip()[:80] or None,
        "schedule": form.get("schedule", "").strip()[:80] or None,
        "start_date": parse_date(form.get("start_date")),
        "purpose": form.get("purpose", "").strip()[:200] or None,
        "source": source if source in entries.SUPPLEMENT_SOURCE_LABELS else None,
        "notes": form.get("notes", "").strip()[:1000] or None,
        "signs": [k for k in form.getlist("signs") if k in signs.SIGN_BY_KEY],
    }
    errors = []
    if not details["name"]:
        errors.append("Please enter the supplement's name.")
    if not details["signs"]:
        errors.append("Pick at least one sign to watch, so there is something to compare.")
    if details["start_date"] and details["start_date"] > date.today():
        errors.append("The start date can't be in the future.")
    return details, errors


@bp.route("/animals/<int:animal_id>/supplements", methods=("GET", "POST"))
def supplements(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        details, errors = _details(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("supplements.html", **_context(animal, values=request.form)), 400
        entries.create_medication(animal_id, details["name"], details["dose"], details["schedule"],
                                  details["start_date"], kind="supplement", signs=details["signs"])
        entries.update_supplement_details(_last_supplement_id(animal_id), **details)
        flash(f"{details['name']} added. Its signs now appear in the daily check-in under \"More details\".")
        return redirect(url_for("supplements.supplements", animal_id=animal_id))
    return render_template("supplements.html", **_context(animal))


def _last_supplement_id(animal_id: int) -> int:
    from ..db import get_db
    return get_db().execute("SELECT MAX(id) FROM medications WHERE animal_id = ? AND kind = 'supplement'",
                            (animal_id,)).fetchone()[0]


def _supplement_or_404(medication_id: int) -> entries.Medication:
    med = entries.get_medication(medication_id)
    if med is None or not med.is_supplement:
        abort(404)
    return med


@bp.post("/supplements/<int:medication_id>/edit")
def edit(medication_id: int):
    """Change anything about a supplement: name, dose, purpose, who recommended it, notes, signs."""
    sup = _supplement_or_404(medication_id)
    details, errors = _details(request.form)
    if errors:
        for message in errors:
            flash(message)
    else:
        entries.update_supplement_details(sup.id, **details)
        flash(f"{details['name']} updated.")
    return redirect(url_for("supplements.supplements", animal_id=sup.animal_id) + f"#supplement-{sup.id}")


@bp.post("/supplements/<int:medication_id>/impression")
def impression(medication_id: int):
    """The owner's own answer to "is it helping?", dated, kept next to the numbers."""
    sup = _supplement_or_404(medication_id)
    choice = request.form.get("impression", "")
    if choice not in entries.IMPRESSION_LABELS:
        flash("Pick how it seems to be going.")
        return redirect(url_for("supplements.supplements", animal_id=sup.animal_id) + f"#supplement-{sup.id}")
    day = parse_date(request.form.get("note_date")) or date.today()
    if day > date.today():
        day = date.today()
    note = request.form.get("note", "").strip()[:500] or None
    entries.add_supplement_note(sup.id, day, choice, note)
    flash(f"Noted: {entries.IMPRESSION_LABELS[choice].lower()} ({day:%b} {day.day}).")
    return redirect(url_for("supplements.supplements", animal_id=sup.animal_id) + f"#supplement-{sup.id}")


@bp.post("/supplements/notes/<int:note_id>/delete")
def delete_impression(note_id: int):
    note = entries.delete_supplement_note(note_id)
    if note is None:
        abort(404)
    sup = _supplement_or_404(note.medication_id)
    flash("Note removed.")
    return redirect(url_for("supplements.supplements", animal_id=sup.animal_id) + f"#supplement-{sup.id}")


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
        "sources": entries.SUPPLEMENT_SOURCES,
        "impressions": entries.IMPRESSIONS,
        "notes": {sup.id: entries.list_supplement_notes(sup.id) for sup in sups},
    }
