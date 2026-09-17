"""Application factory for the Pet Quality-of-Life Tracker."""
from pathlib import Path

from flask import Flask, render_template

from . import db

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
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app
