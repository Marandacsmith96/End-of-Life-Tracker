"""Example pets: add the three built-in demo pets to the app, or remove them."""
from flask import Blueprint, flash, redirect, url_for

from .. import models

bp = Blueprint("demo", __name__)


@bp.post("/examples/add")
def add():
    from scripts.seed_demo import add_examples  # lives with the seed data

    added = add_examples()
    if added:
        word = "an example pet" if len(added) == 1 else "example pets"
        flash(f"Meet {', '.join(added)}: {word}. Everything you see for them is made up.")
    else:
        flash("The example pets are already here.")
    demo = models.list_demo_animals()
    landing = next((a for a in demo if a.name in added), demo[0] if demo else None)
    return redirect(url_for("dashboard.today", animal_id=landing.id) if landing else url_for("dashboard.pets"))


@bp.post("/examples/remove")
def remove():
    from scripts.seed_demo import remove_examples

    count = remove_examples()
    flash("Example pets removed." if count else "There were no example pets to remove.")
    return redirect(url_for("dashboard.landing"))
