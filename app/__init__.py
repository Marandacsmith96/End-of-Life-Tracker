"""Application factory for the Pet Quality-of-Life Tracker."""
from pathlib import Path

from flask import Flask, g, render_template, session

from . import db, flags, models

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask app.

    Pass ``test_config`` to override settings (tests use this to point the
    database at a temporary folder).
    """
    app = Flask(__name__)

    data_dir = PROJECT_ROOT / "data"
    app.config.from_mapping(
        SECRET_KEY="dev",  # only used for flash messages; fine for a local app
        DATA_DIR=data_dir,
        DATABASE=data_dir / "tracker.sqlite",
        PHOTO_DIR=data_dir / "photos",
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB upload cap
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from .routes import animals, entries, export, history

    app.register_blueprint(animals.bp)
    app.register_blueprint(entries.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(export.bp)

    @app.before_request
    def load_current_animal():
        """Make the chosen animal available to every template as g.current_animal."""
        animal_id = session.get("current_animal_id")
        g.current_animal = models.get_animal(animal_id) if animal_id else None
        if animal_id and (g.current_animal is None or g.current_animal.archived):
            session.pop("current_animal_id", None)
            g.current_animal = None

    @app.route("/")
    def dashboard():
        active = models.list_animals()
        archived = [a for a in models.list_animals(include_archived=True) if a.archived]
        flag_counts = {
            a.id: sum(1 for f in flags.for_animal(a.id) if f.is_health) for a in active
        }
        return render_template(
            "dashboard.html", animals=active, archived=archived, flag_counts=flag_counts
        )

    return app
