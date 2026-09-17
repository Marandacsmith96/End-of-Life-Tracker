"""Application factory for the Pet Quality-of-Life Tracker."""
import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, g, redirect, request, session, url_for

from . import db, entries, models, safety, scoring

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    data_dir = Path(os.environ.get("PET_QOL_DATA_DIR", PROJECT_ROOT / "data"))
    app.config.from_mapping(
        SECRET_KEY=None,
        DATA_DIR=data_dir,
        DATABASE=data_dir / "tracker.sqlite",
        PHOTO_DIR=data_dir / "photos",
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _load_or_create_secret(Path(app.config["DATA_DIR"]))

    from .routes import animals, baseline, caregiver, dashboard, export, markers, settings, trends
    from .routes import entries as entry_routes
    from .routes import events as event_routes

    for module in (dashboard, animals, entry_routes, markers, baseline, trends, event_routes,
                   caregiver, export, settings):
        app.register_blueprint(module.bp)

    @app.route("/animals/<int:animal_id>/history")
    def history_redirect(animal_id: int):
        """Old URL kept so bookmarks keep working."""
        return redirect(url_for("trends.trends", animal_id=animal_id))

    @app.before_request
    def load_current_animal():
        if request.endpoint in ("static", "animals.serve_photo"):
            g.current_animal = None
            return
        # A page about a specific pet makes that pet current, so the navigation
        # always matches the page even when it was reached by a direct link.
        animal_id = (request.view_args or {}).get("animal_id") or session.get("current_animal_id")
        g.current_animal = models.get_animal(animal_id) if animal_id else None
        if g.current_animal is not None:
            session["current_animal_id"] = g.current_animal.id
        elif animal_id:
            session.pop("current_animal_id", None)
        g.today_logged = None
        g.checkin_prompt = False
        if g.current_animal and not g.current_animal.archived:
            today = date.today()
            latest = entries.list_entries(g.current_animal.id, limit=1)
            g.today_logged = bool(latest) and latest[0].entry_date == today
            interval = models.REMINDER_DAYS.get(g.current_animal.reminder)
            if interval and not g.today_logged:
                last = latest[0].entry_date if latest else None
                g.checkin_prompt = last is None or (today - last) >= timedelta(days=interval)

    @app.context_processor
    def inject_globals():
        return {"disclaimer": safety.DISCLAIMER, "attribution": scoring.ATTRIBUTION,
                "emergency": safety.EMERGENCY}

    return app


def _load_or_create_secret(data_dir: Path) -> str:
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
