"""Backup, restore, and about."""
import io

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from .. import backup, db, safety, scoring

bp = Blueprint("settings", __name__)


@bp.route("/settings")
def settings():
    return render_template("settings.html", attribution=scoring.ATTRIBUTION, disclaimer=safety.DISCLAIMER)


@bp.get("/settings/backup.zip")
def download_backup():
    data, filename = backup.make_backup()
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True, download_name=filename)


@bp.post("/settings/restore")
def restore():
    if request.form.get("confirm") != "yes":
        flash("Please tick the box to confirm you want to replace your current data.")
        return redirect(url_for("settings.settings"))
    try:
        db.close_db()
        count = backup.restore_backup(request.files.get("backup"))
    except backup.InvalidBackup as exc:
        flash(str(exc))
        return redirect(url_for("settings.settings"))
    session.pop("current_animal_id", None)
    flash(f"Backup restored. {count} {'pet' if count == 1 else 'pets'} loaded.")
    return redirect(url_for("dashboard.home"))
