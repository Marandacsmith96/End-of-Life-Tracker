"""Routes for adding, editing, archiving, and choosing animals."""
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from .. import models, photos

bp = Blueprint("animals", __name__)


def _parse_form(form) -> tuple[dict, list[str]]:
    """Validate the animal form. Returns (clean_values, error_messages)."""
    errors: list[str] = []
    name = form.get("name", "").strip()
    species = form.get("species", "").strip().lower()
    breed = form.get("breed", "").strip() or None
    birth_raw = form.get("birth_date", "").strip()

    if not name:
        errors.append("Please give your pet a name.")
    elif len(name) > 60:
        errors.append("Names must be 60 characters or fewer.")
    if species not in models.SPECIES:
        errors.append("Please choose cat or dog.")

    birth_date = None
    if birth_raw:
        try:
            birth_date = date.fromisoformat(birth_raw)
        except ValueError:
            errors.append("Birth date must be a real date.")
        else:
            if birth_date > date.today():
                errors.append("Birth date cannot be in the future.")

    return {"name": name, "species": species, "breed": breed, "birth_date": birth_date}, errors


def _load_or_404(animal_id: int) -> models.Animal:
    animal = models.get_animal(animal_id)
    if animal is None:
        abort(404)
    return animal


@bp.route("/animals/new", methods=("GET", "POST"))
def new_animal():
    if request.method == "POST":
        values, errors = _parse_form(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("animal_form.html", animal=None, values=request.form), 400
        animal_id = models.create_animal(**values)
        session["current_animal_id"] = animal_id
        flash(f"{values['name']} added.")
        return redirect(url_for("animals.show_animal", animal_id=animal_id))
    return render_template("animal_form.html", animal=None, values={})


@bp.route("/animals/<int:animal_id>")
def show_animal(animal_id: int):
    animal = _load_or_404(animal_id)
    return render_template("animal_detail.html", animal=animal)


@bp.route("/animals/<int:animal_id>/edit", methods=("GET", "POST"))
def edit_animal(animal_id: int):
    animal = _load_or_404(animal_id)
    if request.method == "POST":
        values, errors = _parse_form(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("animal_form.html", animal=animal, values=request.form), 400
        models.update_animal(animal_id, **values)
        flash("Saved.")
        return redirect(url_for("animals.show_animal", animal_id=animal_id))
    values = {
        "name": animal.name,
        "species": animal.species,
        "breed": animal.breed or "",
        "birth_date": animal.birth_date.isoformat() if animal.birth_date else "",
    }
    return render_template("animal_form.html", animal=animal, values=values)


@bp.post("/animals/<int:animal_id>/archive")
def archive_animal(animal_id: int):
    animal = _load_or_404(animal_id)
    models.set_archived(animal_id, True)
    if session.get("current_animal_id") == animal_id:
        session.pop("current_animal_id")
    flash(f"{animal.name} has been archived. Their records are kept.")
    return redirect(url_for("dashboard"))


@bp.post("/animals/<int:animal_id>/unarchive")
def unarchive_animal(animal_id: int):
    animal = _load_or_404(animal_id)
    models.set_archived(animal_id, False)
    flash(f"{animal.name} is active again.")
    return redirect(url_for("animals.show_animal", animal_id=animal_id))


@bp.post("/animals/<int:animal_id>/select")
def select_animal(animal_id: int):
    animal = _load_or_404(animal_id)
    session["current_animal_id"] = animal_id
    flash(f"Now tracking {animal.name}.")
    return redirect(request.referrer or url_for("dashboard"))


@bp.post("/animals/<int:animal_id>/photo")
def upload_photo(animal_id: int):
    animal = _load_or_404(animal_id)
    try:
        relative = photos.save_animal_photo(request.files.get("photo"), animal_id)
    except photos.InvalidImage as exc:
        flash(str(exc))
        return redirect(url_for("animals.show_animal", animal_id=animal_id))
    models.set_photo_path(animal_id, relative)
    flash(f"Photo updated for {animal.name}.")
    return redirect(url_for("animals.show_animal", animal_id=animal_id))


@bp.post("/animals/<int:animal_id>/photo/delete")
def delete_photo(animal_id: int):
    animal = _load_or_404(animal_id)
    photos.delete_animal_photo(animal.photo_path)
    models.set_photo_path(animal_id, None)
    flash("Photo removed.")
    return redirect(url_for("animals.show_animal", animal_id=animal_id))


@bp.route("/photos/<path:filename>")
def serve_photo(filename: str):
    return send_from_directory(current_app.config["PHOTO_DIR"], filename)
