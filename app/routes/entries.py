"""Routes for daily entries, medications, and entry photos."""
from datetime import date

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .. import entries, models, photos, scoring

bp = Blueprint("entries", __name__)


def _animal_or_404(animal_id: int) -> models.Animal:
    animal = models.get_animal(animal_id)
    if animal is None:
        abort(404)
    return animal


def _entry_or_404(entry_id: int) -> entries.Entry:
    entry = entries.get_entry(entry_id)
    if entry is None:
        abort(404)
    return entry


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_entry_form(form) -> tuple[dict, list[str]]:
    errors: list[str] = []

    entry_date = _parse_date(form.get("entry_date", "").strip())
    if entry_date is None:
        errors.append("Please choose a valid date.")
    elif entry_date > date.today():
        errors.append("You cannot log a day that has not happened yet.")

    scores: dict[str, int] = {}
    for key in scoring.CATEGORY_KEYS:
        raw = form.get(key)
        if not scoring.is_valid_score(raw):
            errors.append(f"{scoring.CATEGORY_LABELS[key]} must be a whole number from 0 to 10.")
        else:
            scores[key] = int(raw)

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

    return (
        {
            "entry_date": entry_date,
            "scores": scores,
            "weight": weight,
            "weight_unit": weight_unit,
            "appetite": appetite,
            "notes": notes,
        },
        errors,
    )


def _form_values_from_entry(entry: entries.Entry | None, entry_date: date) -> dict:
    if entry is None:
        values = {key: 5 for key in scoring.CATEGORY_KEYS}
        values.update(entry_date=entry_date.isoformat(), weight="", weight_unit="kg",
                      appetite="", notes="")
        return values
    values = dict(entry.scores)
    values.update(
        entry_date=entry.entry_date.isoformat(),
        weight="" if entry.weight is None else f"{entry.weight:g}",
        weight_unit=entry.weight_unit or "kg",
        appetite=entry.appetite or "",
        notes=entry.notes or "",
    )
    return values


def _render_form(animal, entry, values, status=200):
    medications = entries.list_medications(animal.id, active_only=True)
    given = entries.medications_given(entry.id) if entry else set()
    entry_photos = entries.list_entry_photos(entry.id) if entry else []
    return (
        render_template(
            "entry_form.html",
            animal=animal,
            entry=entry,
            values=values,
            categories=scoring.CATEGORIES,
            appetite_options=scoring.APPETITE_OPTIONS,
            medications=medications,
            given=given,
            photos=entry_photos,
            today=date.today().isoformat(),
        ),
        status,
    )


@bp.route("/animals/<int:animal_id>/log", methods=("GET", "POST"))
def log_entry(animal_id: int):
    """Show or save the entry for one day (today by default)."""
    animal = _animal_or_404(animal_id)
    if animal.archived:
        flash(f"{animal.name} is archived. Restore them to add new entries.")
        return redirect(url_for("animals.show_animal", animal_id=animal_id))

    if request.method == "POST":
        values, errors = _parse_entry_form(request.form)
        if errors:
            for message in errors:
                flash(message)
            existing = (
                entries.get_entry_for_date(animal_id, values["entry_date"])
                if values["entry_date"]
                else None
            )
            return _render_form(animal, existing, request.form, status=400)

        entry_id = entries.save_entry(animal_id, **values)

        offered = {m.id for m in entries.list_medications(animal_id, active_only=True)}
        given = {int(x) for x in request.form.getlist("given") if x.isdigit()} & offered
        entries.set_entry_medications(entry_id, given, offered)

        saved_photos = 0
        for file_storage in request.files.getlist("photos"):
            if not file_storage or not file_storage.filename:
                continue
            try:
                relative = photos.save_entry_photo(file_storage, entry_id)
            except photos.InvalidImage as exc:
                flash(f"{file_storage.filename}: {exc}")
                continue
            entries.add_entry_photo(entry_id, relative)
            saved_photos += 1

        session["current_animal_id"] = animal_id
        message = f"Saved {animal.name}'s entry for {values['entry_date']:%B} {values['entry_date'].day}."
        if saved_photos:
            message += f" {saved_photos} photo{'s' if saved_photos != 1 else ''} added."
        flash(message)
        return redirect(url_for("animals.show_animal", animal_id=animal_id))

    entry_date = _parse_date(request.args.get("date")) or date.today()
    entry = entries.get_entry_for_date(animal_id, entry_date)
    return _render_form(animal, entry, _form_values_from_entry(entry, entry_date))


@bp.post("/entries/<int:entry_id>/delete")
def delete_entry(entry_id: int):
    entry = _entry_or_404(entry_id)
    for photo in entries.list_entry_photos(entry_id):
        photos.delete_photo_file(photo.file_path)
    entries.delete_entry(entry_id)
    flash("Entry deleted.")
    return redirect(url_for("animals.show_animal", animal_id=entry.animal_id))


@bp.post("/entries/photos/<int:photo_id>/delete")
def delete_entry_photo(photo_id: int):
    photo = entries.get_entry_photo(photo_id)
    if photo is None:
        abort(404)
    entry = _entry_or_404(photo.entry_id)
    photos.delete_photo_file(photo.file_path)
    entries.delete_entry_photo(photo_id)
    flash("Photo removed.")
    return redirect(
        url_for("entries.log_entry", animal_id=entry.animal_id, date=entry.entry_date.isoformat())
    )


# --- medications -------------------------------------------------------------

@bp.route("/animals/<int:animal_id>/medications", methods=("GET", "POST"))
def medications(animal_id: int):
    animal = _animal_or_404(animal_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        dose = request.form.get("dose", "").strip() or None
        schedule = request.form.get("schedule", "").strip() or None
        if not name:
            flash("Please enter the medication's name.")
            return render_template(
                "medications.html", animal=animal,
                medications=entries.list_medications(animal_id), values=request.form,
            ), 400
        entries.create_medication(animal_id, name, dose, schedule)
        flash(f"{name} added.")
        return redirect(url_for("entries.medications", animal_id=animal_id))
    return render_template(
        "medications.html", animal=animal,
        medications=entries.list_medications(animal_id), values={},
    )


@bp.post("/medications/<int:medication_id>/toggle")
def toggle_medication(medication_id: int):
    med = entries.get_medication(medication_id)
    if med is None:
        abort(404)
    entries.set_medication_active(medication_id, not med.active)
    flash(f"{med.name} is now {'active' if not med.active else 'inactive'}.")
    return redirect(url_for("entries.medications", animal_id=med.animal_id))


@bp.post("/medications/<int:medication_id>/delete")
def delete_medication(medication_id: int):
    med = entries.get_medication(medication_id)
    if med is None:
        abort(404)
    entries.delete_medication(medication_id)
    flash(f"{med.name} removed.")
    return redirect(url_for("entries.medications", animal_id=med.animal_id))
