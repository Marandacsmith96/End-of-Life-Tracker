"""Phone access: let a phone or tablet on the same Wi-Fi open the app.

The app normally listens only on this computer (127.0.0.1). When phone
access is switched on, a second listener is started on every network
interface, on its own port, and every request that arrives from another
device must present the phone passcode first. Nothing leaves the home
network: there is no account, no cloud, and no internet exposure unless the
owner's router is deliberately set up to forward the port.
"""
import ipaddress
import re
import socket
import threading

from flask import current_app, request
from werkzeug.security import check_password_hash, generate_password_hash

from . import prefs

DEFAULT_PORT = 5100
MIN_PASSCODE = 6
ENVIRON_KEY = "pet_qol.phone_listener"  # set on every request the phone listener receives

_lock = threading.Lock()
_servers: dict[int, object] = {}  # port -> werkzeug server, one per process


# --- state -------------------------------------------------------------------

def is_enabled() -> bool:
    return bool(prefs.get("phone_access"))


def port() -> int:
    try:
        return int(prefs.get("phone_port", DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT


def enable(passcode: str) -> None:
    """Store the passcode (hashed) and switch phone access on."""
    prefs.update(phone_access=True, phone_passcode_hash=generate_password_hash(passcode),
                 phone_port=port())
    start_listener(current_app._get_current_object())


def disable() -> None:
    prefs.update(phone_access=False)
    stop_listener()


def check_passcode(given: str) -> bool:
    stored = prefs.get("phone_passcode_hash")
    return bool(stored) and check_password_hash(stored, given or "")


# --- which requests come from another device --------------------------------

def is_remote_request() -> bool:
    """True when the request arrived through the phone listener from another
    device. Requests on the normal (loopback-only) listener, and requests a
    hosted copy receives through its own web server, are never "remote" here:
    they are covered by the ordinary passcode setting instead."""
    if not request.environ.get(ENVIRON_KEY):
        return False
    addr = request.remote_addr or ""
    try:
        return not ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return True


# --- the listener ------------------------------------------------------------

def _tagged(app):
    """The app as seen by the phone listener: every request is marked so the
    passcode and the "only from this computer" rules know where it came from."""
    def wsgi(environ, start_response):
        environ[ENVIRON_KEY] = True
        return app(environ, start_response)
    return wsgi


def start_listener(app) -> bool:
    """Start the all-interfaces listener if it is not already running."""
    if app.config.get("TESTING"):
        return False
    import contextlib
    import io
    from werkzeug.serving import make_server

    p = port()
    with _lock:
        if p in _servers:
            return True
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # werkzeug prints, then exits, on a busy port
                httpd = make_server("0.0.0.0", p, _tagged(app), threaded=True)
        except (OSError, SystemExit):
            return False
        thread = threading.Thread(target=httpd.serve_forever, name="phone-access", daemon=True)
        thread.start()
        _servers[p] = httpd
        return True


def stop_listener() -> None:
    with _lock:
        for p, httpd in list(_servers.items()):
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            _servers.pop(p, None)


def listener_running() -> bool:
    return port() in _servers


def autostart(app) -> None:
    """Called once when the app starts: resume phone access if it was left on."""
    with app.app_context():
        if is_enabled():
            start_listener(app)


# --- addresses ---------------------------------------------------------------

def lan_ip() -> str | None:
    """This computer's address on the local network, or None if it has none."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the outbound interface
            ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def url() -> str | None:
    ip = lan_ip()
    return f"http://{ip}:{port()}/" if ip else None


def qr_svg(text: str) -> str:
    """A QR code for ``text`` as an inline SVG string."""
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    svg = img.to_string(encoding="unicode")
    # Drop the fixed millimetre size so the page's CSS decides how big it is.
    svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    return svg.replace("<svg ", '<svg class="qr-code" role="img" aria-label="QR code for the address" ', 1)
