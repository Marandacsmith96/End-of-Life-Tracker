"""Daily check-in (full and quick), medications, and entry photos."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from .. import entries, markers, photos, scoring
from ..helpers import animal_or_404, parse_date

bp = Blueprint("entries", __name__)


def _entry_or_404(entry_id: int) -> entries.Entry:
    entry = entries.get_entry(entry_id)
    if entry is None:
        abort(404)
    return entry


def _parse_common(form) -> tuple[dict, list[str]]:
    errors: list[str] = []
    entry_date = parse_date(form.get("entry_date"))
    if entry_date is None:
        errors.append("Please choose a valid date.")
    elif entry_date > date.today():
        errors.append("You can't record a day that hasn't happened yet.")
    day_status = form.get("day_status") or None
    if day_status is not None and day_status not in entries.DAY_STATUS_LABELS:
        errors.append("Please choose good, bad, or mixed.")
    return {"entry_date": entry_date, "day_status": day_status}, errors


def _parse_scores(form) -> tuple[dict, list[str]]:
    """Scores are optional as a block: either all seven are given, or none."""
    errors: list[str] = []
    if form.get("scores_included") != "1":
        return {}, errors
    scores: dict[str, int | None] = {}
    for key in scoring.CATEGORY_KEYS:
        raw = form.get(key)
        if not scoring.is_valid_score(raw):
            errors.append(f"{scoring.CATEGORY_LABELS[key]} must be a whole number from 0 to 10.")
        else:
            scores[key] = int(raw)
    return scores, errors


def _parse_extras(form) -> tuple[dict, list[str]]:
    errors: list[str] = []
    weight = None
    weight_unit = form.get("weight_unit", "kg")
    raw_weight = form.get("weight", "").strip()
    if raw_weight:
        try:
            weight = float(raw_weight)
        except ValueError:
            errors.append("Weight must be a number.")
        else:
            if weight <= 0 or weight > 500:
                errors.append("Weight looks wrong. Please check it.")
        if weight_unit not in scoring.WEIGHT_UNITS:
            errors.append("Weight unit must be kg or lb.")
    else:
        weight_unit = None
    appetite = form.get("appetite") or None
    if appetite is not None and appetite not in scoring.APPETITE_LABELS:
        errors.append("Please choose a valid appetite option.")
    notes = form.get("notes", "").strip() or None
    if notes and len(notes) > 5000:
        errors.append("Notes must be 5000 characters or fewer.")
    return {"weight": weight, "weight_unit": weight_unit, "appetite": appetite, "notes": notes}, errors


def _save_markers_and_meds(animal_id: int, entry_id: int, form) -> None:
    offered_markers = {m.id for m in markers.list_markers(animal_id)}
    if form.get("markers_included") == "1":
        done = {int(x) for x in form.getlist("markers") if x.isdigit()} & offered_markers
        markers.set_responses(entry_id, done, offered_markers)
    if form.get("meds_included") == "1":
        offered = {m.id for m in entries.list_medications(animal_id, active_only=True)}
        given = {int(x) for x in form.getlist("given") if x.isdigit()} & offered
        entries.set_entry_medications(entry_id, given, offered)


def _save_photos(entry_id: int, files) -> int:
    saved = 0
    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        try:
            relative = photos.save_entry_photo(file_storage, entry_id)
        except photos.InvalidImage as exc:
            flash(f"{file_storage.filename}: {exc}")
            continue
        entries.add_entry_photo(entry_id, relative)
        saved += 1
    return saved


def _form_values(entry: entries.Entry | None, entry_date: date) -> dict:
    values = {key: 5 for key in scoring.CATEGORY_KEYS}
    values.update(entry_date=entry_date.isoformat(), day_status="", weight="", weight_unit="kg",
                  appetite="", notes="")
    if entry is None:
        return values
    for key, v in entry.scores.items():
        if v is not None:
            values[key] = v
    values.update(
        day_status=entry.day_status or "",
        weight="" if entry.weight is None else f"{entry.weight:g}",
        weight_unit=entry.weight_unit or "kg",
        appetite=entry.appetite or "",
        notes=entry.notes or "",
    )
    return values


def _render_checkin(animal, entry, values, quick: bool, status=200, start_step=None):
    marker_list = markers.list_markers(animal.id)
    answers = markers.responses_for_entry(entry.id) if entry else {}
    return (
        render_template(
            "checkin_quick.html" if quick else "checkin.html",
            animal=animal, entry=entry, values=values,
            categories=scoring.CATEGORIES, questions=scoring.QUESTIONS, anchors=scoring.CATEGORY_ANCHORS,
            day_statuses=entries.DAY_STATUSES, markers=marker_list, answers=answers,
            appetite_options=scoring.APPETITE_OPTIONS,
            medications=entries.list_medications(animal.id, active_only=True),
            given=entries.medications_given(entry.id) if entry else set(),
            photos=entries.list_entry_photos(entry.id) if entry else [],
            today=date.today().isoformat(), start_step=start_step,
            has_scores=entry.has_scores if entry else False,
        ),
        status,
    )


@bp.route("/animals/<int:animal_id>/checkin", methods=("GET", "POST"))
@bp.route("/animals/<int:animal_id>/log", methods=("GET", "POST"))
def checkin(animal_id: int):
    """Full check-in: good/bad day, behaviors, HHHHHMM scores, optional extras."""
    animal = animal_or_404(animal_id)
    if animal.archived:
        flash(f"{animal.name}'s profile is archived. Restore it to add new check-ins.")
        return redirect(url_for("dashboard.today", animal_id=animal_id))

    if request.method == "POST":
        common, errors = _parse_common(request.form)
        scores, score_errors = _parse_scores(request.form)
        extras, extra_errors = _parse_extras(request.form)
        errors += score_errors + extra_errors
        if errors:
            for message in errors:
                flash(message)
            existing = entries.get_entry_for_date(animal_id, common["entry_date"]) if common["entry_date"] else None
            return _render_checkin(animal, existing, request.form, quick=False, status=400)
        entry_id = entries.save_entry(animal_id, common["entry_date"], common["day_status"], scores, **extras)
        _save_markers_and_meds(animal_id, entry_id, request.form)
        saved_photos = _save_photos(entry_id, request.files.getlist("photos"))
        session["current_animal_id"] = animal_id
        message = f"Saved {animal.name}'s check-in for {common['entry_date']:%B} {common['entry_date'].day}."
        if saved_photos:
            message += f" {saved_photos} photo{'s' if saved_photos != 1 else ''} added."
        flash(message)
        return redirect(url_for("dashboard.today", animal_id=animal_id))

    entry_date = parse_date(request.args.get("date")) or date.today()
    entry = entries.get_entry_for_date(animal_id, entry_date)
    return _render_checkin(animal, entry, _form_values(entry, entry_date), quick=False,
                           start_step=request.args.get("step"))


@bp.route("/animals/<int:animal_id>/checkin/quick", methods=("GET", "POST"))
def quick_checkin(animal_id: int):
    """Quick check-in: good/bad day and behaviors only. Under ten seconds."""
    animal = animal_or_404(animal_id)
    if animal.archived:
        flash(f"{animal.name}'s profile is archived. Restore it to add new check-ins.")
        return redirect(url_for("dashboard.today", animal_id=animal_id))
    if request.method == "POST":
        common, errors = _parse_common(request.form)
        if not common["day_status"]:
            errors.append("Please choose good, bad, or mixed.")
        if errors:
            for message in errors:
                flash(message)
            existing = entries.get_entry_for_date(animal_id, common["entry_date"]) if common["entry_date"] else None
            return _render_checkin(animal, existing, request.form, quick=True, status=400)
        entry_id = entries.save_entry(animal_id, common["entry_date"], common["day_status"])
        _save_markers_and_meds(animal_id, entry_id, request.form)
        session["current_animal_id"] = animal_id
        entry = entries.get_entry(entry_id)
        return render_template("checkin_done.html", animal=animal, entry=entry)
    entry_date = parse_date(request.args.get("date")) or date.today()
    entry = entries.get_entry_for_date(animal_id, entry_date)
    return _render_checkin(animal, entry, _form_values(entry, entry_date), quick=True)


@bp.post("/entries/<int:entry_id>/delete")
def delete_entry(entry_id: int):
    entry = _entry_or_404(entry_id)
    for photo in entries.list_entry_photos(entry_id):
        photos.delete_photo_file(photo.file_path)
    entries.delete_entry(entry_id)
    flash("Check-in removed.")
    return redirect(url_for("dashboard.today", animal_id=entry.animal_id))


@bp.post("/entries/photos/<int:photo_id>/delete")
def delete_entry_photo(photo_id: int):
    photo = entries.get_entry_photo(photo_id)
    if photo is None:
        abort(404)
    entry = _entry_or_404(photo.entry_id)
    photos.delete_photo_file(photo.file_path)
    entries.delete_entry_photo(photo_id)
    flash("Photo removed.")
    return redirect(url_for("entries.checkin", animal_id=entry.animal_id, date=entry.entry_date.isoformat()))


# --- medications -------------------------------------------------------------

@bp.route("/animals/<int:animal_id>/medications", methods=("GET", "POST"))
def medications(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        dose = request.form.get("dose", "").strip() or None
        schedule = request.form.get("schedule", "").strip() or None
        start = parse_date(request.form.get("start_date"))
        if not name:
            flash("Please enter the medication's name.")
            return render_template("medications.html", animal=animal,
                                   medications=entries.list_medications(animal_id), values=request.form,
                                   today=date.today().isoformat()), 400
        entries.create_medication(animal_id, name, dose, schedule, start)
        flash(f"{name} added.")
        return redirect(url_for("entries.medications", animal_id=animal_id))
    return render_template("medications.html", animal=animal, medications=entries.list_medications(animal_id),
                           values={}, today=date.today().isoformat())


@bp.post("/medications/<int:medication_id>/toggle")
def toggle_medication(medication_id: int):
    med = entries.get_medication(medication_id)
    if med is None:
        abort(404)
    entries.set_medication_active(medication_id, not med.active)
    flash(f"{med.name} marked {'active' if not med.active else 'stopped'}.")
    return redirect(url_for("entries.medications", animal_id=med.animal_id))


@bp.post("/medications/<int:medication_id>/delete")
def delete_medication(medication_id: int):
    med = entries.get_medication(medication_id)
    if med is None:
        abort(404)
    entries.delete_medication(medication_id)
    flash(f"{med.name} removed.")
    return redirect(url_for("entries.medications", animal_id=med.animal_id))
