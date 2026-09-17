"""Optional passcode. Only active when PET_QOL_PASSCODE is set, which is what a
hosted copy needs so that only the owner can open it."""
import hmac

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

bp = Blueprint("auth", __name__)
OPEN_ENDPOINTS = {"static", "auth.login", "auth.logout"}


def passcode_required() -> bool:
    return bool(current_app.config.get("PASSCODE"))


def is_unlocked() -> bool:
    return session.get("unlocked") is True


@bp.route("/unlock", methods=("GET", "POST"))
def login():
    if not passcode_required():
        return redirect(url_for("dashboard.home"))
    if request.method == "POST":
        given = request.form.get("passcode", "")
        if hmac.compare_digest(given, current_app.config["PASSCODE"]):
            session["unlocked"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("dashboard.home"))
        flash("That passcode isn't right.")
        return render_template("unlock.html"), 401
    return render_template("unlock.html")


@bp.post("/lock")
def logout():
    session.clear()
    flash("Locked.")
    return redirect(url_for("auth.login"))
