"""Application factory for the Pet Quality-of-Life Tracker."""
import os
import secrets
from pathlib import Path

from flask import Flask, g, render_template, session

from . import db, entries, flags, models

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask app.

    Pass ``test_config`` to override settings (tests use this to point the
    database at a temporary folder).
    """
    app = Flask(__name__)

    data_dir = Path(os.environ.get("PET_QOL_DATA_DIR", PROJECT_ROOT / "data"))
    app.config.from_mapping(
        SECRET_KEY=None,  # filled in below from data/secret_key
        DATA_DIR=data_dir,
        DATABASE=data_dir / "tracker.sqlite",
        PHOTO_DIR=data_dir / "photos",
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB upload cap
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _load_or_create_secret(Path(app.config["DATA_DIR"]))

    from .routes import animals, export, history, settings
    from .routes import entries as entry_routes

    app.register_blueprint(animals.bp)
    app.register_blueprint(entry_routes.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(export.bp)
    app.register_blueprint(settings.bp)

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
        latest = {a.id: entries.list_entries(a.id, limit=1) for a in active}
        latest = {k: v[0] if v else None for k, v in latest.items()}
        return render_template(
            "dashboard.html", animals=active, archived=archived,
            flag_counts=flag_counts, latest=latest,
        )

    return app


def _load_or_create_secret(data_dir: Path) -> str:
    """Sessions are signed with a random key saved next to the database."""
    path = data_dir / "secret_key"
    try:
        return path.read_text(encoding="utf-8").strip() or _write_secret(path)
    except FileNotFoundError:
        return _write_secret(path)


def _write_secret(path: Path) -> str:
    key = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key, encoding="utf-8")
    return key
