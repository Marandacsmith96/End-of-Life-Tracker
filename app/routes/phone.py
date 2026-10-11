"""The "Use on your phone" page: switch phone access on or off."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import phone

bp = Blueprint("phone", __name__)


@bp.route("/settings/phone", methods=("GET", "POST"))
def settings():
    if request.method == "POST":
        if phone.is_remote_request():
            abort(403)  # only the computer itself may change this
        action = request.form.get("action")
        if action == "enable":
            passcode = request.form.get("passcode", "")
            confirm = request.form.get("passcode_confirm", "")
            if len(passcode) < phone.MIN_PASSCODE:
                flash(f"Please choose a passcode of at least {phone.MIN_PASSCODE} characters.")
                return render_template("phone.html", **_context()), 400
            if passcode != confirm:
                flash("The two passcodes don't match.")
                return render_template("phone.html", **_context()), 400
            phone.enable(passcode)
            if phone.listener_running():
                flash("Phone access is on. Scan the code or type the address on your phone.")
            else:
                flash("Phone access is saved, but the listener could not start on port "
                      f"{phone.port()}. Restart the app to try again.")
        elif action == "disable":
            phone.disable()
            flash("Phone access is off. Phones on your Wi-Fi can no longer open the app.")
        return redirect(url_for("phone.settings"))
    return render_template("phone.html", **_context())


def _context() -> dict:
    address = phone.url() if phone.is_enabled() else None
    return {
        "enabled": phone.is_enabled(),
        "running": phone.listener_running(),
        "address": address,
        "qr": phone.qr_svg(address) if address else None,
        "port": phone.port(),
        "min_passcode": phone.MIN_PASSCODE,
        "remote": phone.is_remote_request(),
    }
