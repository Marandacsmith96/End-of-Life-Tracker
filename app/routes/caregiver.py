"""Weekly caregiver check-in, kept separate from the animal's data."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import caregiver
from ..helpers import animal_or_404

bp = Blueprint("caregiver", __name__)


@bp.route("/animals/<int:animal_id>/caregiver", methods=("GET", "POST"))
def checkin(animal_id: int):
    animal = animal_or_404(animal_id)
    if request.method == "POST":
        status = request.form.get("status", "")
        if status not in caregiver.STATUS_LABELS:
            flash("Please choose one of the options.")
            return render_template("caregiver.html", animal=animal, statuses=caregiver.STATUSES,
                                   intro=caregiver.INTRO, history=caregiver.list_checkins(animal_id, 12),
                                   values=request.form), 400
        note = request.form.get("note", "").strip() or None
        caregiver.save_checkin(animal_id, date.today(), status, note)
        flash("Thank you. Your check-in is saved, separately from the notes about " + animal.name + ".")
        return redirect(url_for("dashboard.today", animal_id=animal_id))
    return render_template("caregiver.html", animal=animal, statuses=caregiver.STATUSES,
                           intro=caregiver.INTRO, history=caregiver.list_checkins(animal_id, 12), values={})


@bp.post("/caregiver/<int:checkin_id>/delete")
def delete(checkin_id: int):
    animal_id = request.form.get("animal_id")
    caregiver.delete_checkin(checkin_id)
    flash("Removed.")
    if animal_id and animal_id.isdigit():
        return redirect(url_for("caregiver.checkin", animal_id=int(animal_id)))
    abort(404)
