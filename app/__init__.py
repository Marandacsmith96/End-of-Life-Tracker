"""Application factory for the Pet Quality-of-Life Tracker."""
import ipaddress
import os
import secrets
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from werkzeug.routing import IntegerConverter, ValidationError

from . import db, entries, models, phone, safety, scoring, version

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_ID = 2**63 - 1  # largest SQLite INTEGER


class IdConverter(IntegerConverter):
    """An <int:...> that cannot exceed what SQLite can store (else 404, not 500)."""

    def to_python(self, value: str) -> int:
        number = super().to_python(value)
        if number > MAX_ID:
            raise ValidationError()
        return number


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.url_map.converters["int"] = IdConverter

    data_dir = Path(os.environ.get("PET_QOL_DATA_DIR", PROJECT_ROOT / "data"))
    app.config.from_mapping(
        SECRET_KEY=None,
        DATA_DIR=data_dir,
        DATABASE=data_dir / "tracker.sqlite",
        PHOTO_DIR=data_dir / "photos",
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,  # a check-in with several phone photos
        PASSCODE=os.environ.get("PET_QOL_PASSCODE") or None,  # set this on a hosted copy
        TRUSTED_HOSTS=[h.strip() for h in os.environ.get("PET_QOL_TRUSTED_HOSTS", "").split(",") if h.strip()] or None,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _load_or_create_secret(Path(app.config["DATA_DIR"]))

    from .routes import animals, auth, baseline, caregiver, dashboard, demo, export, markers, settings, trends
    from .routes import entries as entry_routes
    from .routes import events as event_routes
    from .routes import phone as phone_routes

    for module in (auth, dashboard, animals, entry_routes, markers, baseline, trends, event_routes,
                   caregiver, export, settings, demo, phone_routes):
        app.register_blueprint(module.bp)

    @app.before_request
    def refuse_foreign_host_names():
        """A page on another website can point a domain name it owns at this
        computer (DNS rebinding) and then post here as if it were the app.
        A local copy is only ever opened by address, so a domain name in the
        Host header is refused. A hosted copy (which has a passcode) is
        reached by its real name and sets TRUSTED_HOSTS itself if needed."""
        if app.config.get("PASSCODE") or app.config.get("TRUSTED_HOSTS"):
            return None
        host = request.host.rsplit(":", 1)[0] if not request.host.startswith("[") else request.host.split("]")[0][1:]
        if host == "localhost" or host.endswith(".localhost"):
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            abort(403)
        return None

    @app.before_request
    def allow_large_restores():
        """A backup can be far bigger than a check-in's photos."""
        if request.endpoint == "settings.restore":
            from . import backup
            request.max_content_length = backup.MAX_RESTORE_BYTES

    @app.before_request
    def only_while_phone_access_is_on():
        """A request from another device is only served while phone access is
        switched on (the listener is stopped when it is switched off; this
        covers the moment in between)."""
        if phone.is_remote_request() and not phone.is_enabled():
            abort(403)

    @app.before_request
    def block_cross_site_posts():
        """Another website open in the same browser must not be able to post
        to the tracker (which would let it wipe or alter the data). Modern
        browsers label every request with Sec-Fetch-Site; older ones send
        Origin. Requests with neither (command-line tools, tests) are allowed."""
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        site = request.headers.get("Sec-Fetch-Site")
        if site and site not in ("same-origin", "none"):
            abort(403)
        origin = request.headers.get("Origin")
        # Compare hosts only: behind a hosting provider's HTTPS proxy the app
        # itself may see plain http, and the scheme would never match.
        if origin and urlsplit(origin).netloc.lower() != request.host.lower():
            abort(403)
        return None

    @app.before_request
    def require_passcode():
        if auth.passcode_required() and request.endpoint not in auth.OPEN_ENDPOINTS and not auth.is_unlocked():
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?") if request.method == "GET" else None))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", title="That page isn't here",
                               message="The link may be old, or the pet it belonged to may have been removed."), 404

    @app.errorhandler(405)
    def wrong_method(_error):
        return render_template("error.html", title="That didn't work",
                               message="The page was asked for in a way it doesn't support. Try again from the app."), 405

    @app.errorhandler(413)
    def too_large(_error):
        from . import backup
        limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return render_template("error.html", title="That was too much to upload at once",
                               message=f"Photos can add up to {limit} MB per check-in, and a backup can be up to "
                                       f"{backup.MAX_RESTORE_BYTES // (1024 * 1024)} MB. Try fewer or smaller files."), 413

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
                g.checkin_prompt = last is not None and (today - last) >= timedelta(days=interval)

    @app.context_processor
    def inject_globals():
        return {"disclaimer": safety.DISCLAIMER, "attribution": scoring.ATTRIBUTION,
                "emergency": safety.EMERGENCY, "switcher_pets": _switcher_pets, "switch_url": _switch_url,
                "build_label": version.build_label(), "can_lock": auth.can_lock,
                "from_phone": phone.is_remote_request}

    if not app.config.get("TESTING"):
        phone.autostart(app)
    return app


def _switcher_pets() -> list:
    """Pets shown in the switcher bar: every active pet (plus the current one if
    it is archived or remembered), when there is more than one."""
    pets = models.list_animals()
    current = getattr(g, "current_animal", None)
    if current is not None and all(p.id != current.id for p in pets):
        pets = [current, *pets]
    return pets if len(pets) > 1 else []


def _switch_url(animal) -> str:
    """The same page for another pet when the page is about a pet, else their Today page."""
    args = dict(request.view_args or {})
    if request.endpoint and "animal_id" in args and request.method == "GET":
        try:
            return url_for(request.endpoint, **{**args, "animal_id": animal.id})
        except Exception:  # noqa: BLE001 - a page that cannot be rebuilt for another pet
            pass
    return url_for("dashboard.today", animal_id=animal.id)


def _load_or_create_secret(data_dir: Path) -> str:
    path = data_dir / "secret_key"
    try:
        return path.read_text(encoding="utf-8").strip() or _write_secret(path)
    except FileNotFoundError:
        return _write_secret(path)


def _write_secret(path: Path) -> str:
    """Create the key file atomically; if another process got there first
    (two server workers starting together), use its key so sessions agree."""
    key = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key)
        return key
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip() or key
