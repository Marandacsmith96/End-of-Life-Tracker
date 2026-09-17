"""Pets: add, edit, photo, choose, settings, archive, and the passing flow."""
from datetime import date

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request,
    send_from_directory, session, url_for,
)

from .. import baseline, models, photos
from ..helpers import animal_or_404, parse_date

bp = Blueprint("animals", __name__)


def _parse_form(form) -> tuple[dict, list[str]]:
    errors: list[str] = []
    name = form.get("name", "").strip()
    species = form.get("species", "").strip().lower()
    breed = form.get("breed", "").strip() or None
    sex = form.get("sex", "").strip() or None
    diagnoses = form.get("diagnoses", "").strip() or None
    birth_raw = form.get("birth_date", "").strip()

    if not name:
        errors.append("Please enter your pet's name.")
    elif len(name) > 60:
        errors.append("Names must be 60 characters or fewer.")
    if species not in models.SPECIES:
        errors.append("Please choose cat or dog.")
    if sex is not None and sex not in dict(models.SEXES):
        errors.append("Please choose a valid option for sex.")

    birth_date = None
    if birth_raw:
        birth_date = parse_date(birth_raw)
        if birth_date is None:
            errors.append("Birth date must be a real date.")
        elif birth_date > date.today():
            errors.append("Birth date cannot be in the future.")

    return {"name": name, "species": species, "breed": breed, "birth_date": birth_date,
            "sex": sex, "diagnoses": diagnoses}, errors


@bp.route("/animals/new", methods=("GET", "POST"))
def new_animal():
    onboarding = request.args.get("onboarding") == "1" or not models.list_animals(include_archived=True)
    if request.method == "POST":
        values, errors = _parse_form(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("animal_form.html", animal=None, values=request.form,
                                   sexes=models.SEXES, onboarding=onboarding), 400
        animal_id = models.create_animal(**values)
        session["current_animal_id"] = animal_id
        return redirect(url_for("markers.setup", animal_id=animal_id, onboarding=1))
    return render_template("animal_form.html", animal=None, values={}, sexes=models.SEXES,
                           onboarding=onboarding)


@bp.route("/animals/<int:animal_id>")
def show_animal(animal_id: int):
    session["current_animal_id"] = animal_id
    return redirect(url_for("dashboard.today", animal_id=animal_id))


@bp.route("/animals/<int:animal_id>/edit", methods=("GET", "POST"))
def edit_animal(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        values, errors = _parse_form(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("animal_form.html", animal=animal, values=request.form,
                                   sexes=models.SEXES, onboarding=False), 400
        models.update_animal(animal_id, **values)
        flash("Saved.")
        return redirect(url_for("animals.settings", animal_id=animal_id))
    values = {
        "name": animal.name, "species": animal.species, "breed": animal.breed or "",
        "sex": animal.sex or "", "diagnoses": animal.diagnoses or "",
        "birth_date": animal.birth_date.isoformat() if animal.birth_date else "",
    }
    return render_template("animal_form.html", animal=animal, values=values, sexes=models.SEXES,
                           onboarding=False)


@bp.route("/animals/<int:animal_id>/ready")
def ready(animal_id: int):
    animal = animal_or_404(animal_id)
    session["current_animal_id"] = animal_id
    return render_template("ready.html", animal=animal, has_baseline=baseline.get_baseline(animal_id) is not None)


@bp.route("/animals/<int:animal_id>/settings")
def settings(animal_id: int):
    animal = animal_or_404(animal_id)
    return render_template("animal_settings.html", animal=animal, reminders=models.REMINDERS)


@bp.post("/animals/<int:animal_id>/reminder")
def set_reminder(animal_id: int):
    animal_or_404(animal_id)
    choice = request.form.get("reminder", "off")
    if choice not in dict(models.REMINDERS):
        choice = "off"
    models.set_reminder(animal_id, choice)
    flash("Reminder setting saved.")
    return redirect(url_for("animals.settings", animal_id=animal_id))


@bp.post("/animals/<int:animal_id>/archive")
def archive_animal(animal_id: int):
    animal = animal_or_404(animal_id)
    models.set_status(animal_id, "archived")
    if session.get("current_animal_id") == animal_id:
        session.pop("current_animal_id")
    flash(f"{animal.name}'s profile has been archived. Their history is kept.")
    return redirect(url_for("dashboard.home"))


@bp.post("/animals/<int:animal_id>/unarchive")
def unarchive_animal(animal_id: int):
    animal = animal_or_404(animal_id)
    models.set_status(animal_id, "active")
    session["current_animal_id"] = animal_id
    flash(f"{animal.name}'s profile is active again.")
    return redirect(url_for("dashboard.today", animal_id=animal_id))


@bp.route("/animals/<int:animal_id>/passed", methods=("GET", "POST"))
def passed(animal_id: int):
    """The gentle flow for when the animal has died."""
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        passed_date = parse_date(request.form.get("passed_date")) or date.today()
        if passed_date > date.today():
            passed_date = date.today()
        models.set_status(animal_id, "passed", passed_date)
        return redirect(url_for("animals.after_passing", animal_id=animal_id))
    return render_template("passed.html", animal=animal, today=date.today().isoformat())


@bp.route("/animals/<int:animal_id>/after")
def after_passing(animal_id: int):
    animal = animal_or_404(animal_id)
    return render_template("after_passing.html", animal=animal)


@bp.post("/animals/<int:animal_id>/keep")
def keep_profile(animal_id: int):
    """Keep the profile visible (status stays 'passed'; nothing is removed)."""
    animal = animal_or_404(animal_id)
    session["current_animal_id"] = animal_id
    return redirect(url_for("dashboard.today", animal_id=animal.id))


@bp.route("/animals/<int:animal_id>/remove", methods=("GET", "POST"))
def remove_animal(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        if request.form.get("confirm_name", "").strip().lower() != animal.name.strip().lower():
            flash("To remove the profile, type the name exactly as it appears.")
            return render_template("remove.html", animal=animal), 400
        photos.delete_photo_file(animal.photo_path)
        models.delete_animal(animal_id)
        if session.get("current_animal_id") == animal_id:
            session.pop("current_animal_id")
        flash(f"{animal.name}'s profile and records have been removed.")
        return redirect(url_for("dashboard.home"))
    return render_template("remove.html", animal=animal)


@bp.post("/animals/<int:animal_id>/select")
def select_animal(animal_id: int):
    animal = animal_or_404(animal_id)
    session["current_animal_id"] = animal_id
    return redirect(url_for("dashboard.today", animal_id=animal.id))


@bp.post("/animals/<int:animal_id>/photo")
def upload_photo(animal_id: int):
    animal_or_404(animal_id)
    try:
        relative = photos.save_animal_photo(request.files.get("photo"), animal_id)
    except photos.InvalidImage as exc:
        flash(str(exc))
        return redirect(request.referrer or url_for("animals.settings", animal_id=animal_id))
    models.set_photo_path(animal_id, relative)
    flash("Photo updated.")
    return redirect(request.referrer or url_for("animals.settings", animal_id=animal_id))


@bp.post("/animals/<int:animal_id>/photo/delete")
def delete_photo(animal_id: int):
    animal = animal_or_404(animal_id)
    photos.delete_photo_file(animal.photo_path)
    models.set_photo_path(animal_id, None)
    flash("Photo removed.")
    return redirect(url_for("animals.settings", animal_id=animal_id))


@bp.route("/photos/<path:filename>")
def serve_photo(filename: str):
    return send_from_directory(current_app.config["PHOTO_DIR"], filename)
