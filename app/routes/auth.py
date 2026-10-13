"""Optional passcode. Active when PET_QOL_PASSCODE is set (a hosted copy), and
for requests that reach the app from another device through phone access."""
import hmac
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from .. import phone

bp = Blueprint("auth", __name__)
OPEN_ENDPOINTS = {"static", "auth.login", "auth.logout"}


def safe_next(target: str | None) -> str | None:
    """Only follow redirects to a path on this site, never to another host."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def passcode_required() -> bool:
    if phone.is_remote_request():
        return True  # phone access is on (the listener only runs then) and this is another device
    return bool(current_app.config.get("PASSCODE"))


def _accept(given: str) -> bool:
    if phone.is_remote_request():
        return phone.check_passcode(given)
    expected = current_app.config.get("PASSCODE") or ""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def is_unlocked() -> bool:
    if session.get("unlocked") is not True:
        return False
    if phone.is_remote_request():
        # A phone stays unlocked only while the passcode it unlocked under is current.
        return session.get("phone_generation") == phone.generation()
    return True


def can_lock() -> bool:
    """Whether a Lock button makes sense on this page."""
    return passcode_required() and is_unlocked()


@bp.route("/unlock", methods=("GET", "POST"))
def login():
    if not passcode_required():
        return redirect(url_for("dashboard.home"))
    if request.method == "POST":
        remote = phone.is_remote_request()
        addr = request.remote_addr or ""
        if remote and (wait := phone.seconds_to_wait(addr)):
            flash(f"Too many tries. Please wait {wait} seconds and try again.")
            return render_template("unlock.html", from_phone=True), 429
        given = request.form.get("passcode", "")
        if _accept(given):
            session["unlocked"] = True
            session.permanent = True
            if remote:
                session["phone_generation"] = phone.generation()
                phone.note_success(addr)
            return redirect(safe_next(request.args.get("next")) or url_for("dashboard.home"))
        if remote:
            phone.note_failure(addr)
        if not current_app.config.get("TESTING"):
            time.sleep(0.5)  # slows down guessing from another device
        flash("That passcode isn't right.")
        return render_template("unlock.html", from_phone=remote), 401
    return render_template("unlock.html", from_phone=phone.is_remote_request())


@bp.post("/lock")
def logout():
    session.clear()
    flash("Locked.")
    return redirect(url_for("auth.login"))
