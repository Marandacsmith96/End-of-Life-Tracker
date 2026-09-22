"""Optional passcode. Only active when PET_QOL_PASSCODE is set, which is what a
hosted copy needs so that only the owner can open it."""
import hmac

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

bp = Blueprint("auth", __name__)
OPEN_ENDPOINTS = {"static", "auth.login", "auth.logout"}


def safe_next(target: str | None) -> str | None:
    """Only follow redirects to a path on this site, never to another host."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


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
        if hmac.compare_digest(given.encode("utf-8"), current_app.config["PASSCODE"].encode("utf-8")):
            session["unlocked"] = True
            session.permanent = True
            return redirect(safe_next(request.args.get("next")) or url_for("dashboard.home"))
        flash("That passcode isn't right.")
        return render_template("unlock.html"), 401
    return render_template("unlock.html")


@bp.post("/lock")
def logout():
    session.clear()
    flash("Locked.")
    return redirect(url_for("auth.login"))
