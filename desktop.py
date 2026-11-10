"""Start the tracker and open it in a browser (also the packaged build's entry point).

    python desktop.py

With the optional ``pywebview`` package installed the app opens in its own
window instead of a browser tab:

    pip install pywebview
"""
import contextlib
import io
import logging
import os
import secrets
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

from app import create_app

HOST = "127.0.0.1"
PREFERRED_PORT = int(os.environ.get("PET_QOL_PORT", "5000"))


def _answers_as_us(url: str, token: str) -> bool:
    """Fetch our liveness page and check it is really this app replying.

    On Windows another program can hold the same port and get the browser's
    requests instead of us (its reply is typically "404 page not found")."""
    import urllib.request

    try:
        with urllib.request.urlopen(url + "__alive", timeout=3) as resp:
            return resp.read().decode("utf-8", "replace").strip() == token
    except Exception:  # noqa: BLE001 - any failure means "not us"
        return False


def _start_server(app, start: int, token: str):
    """Bind the web server to the preferred port, or the next free one, and
    make sure the address really reaches this app before trusting it.

    Returns (port, server, thread) or (None, None, None)."""
    from werkzeug.serving import make_server

    from app.phone import port_is_free

    for port in range(start, start + 20):
        if not port_is_free(HOST, port):
            continue
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # werkzeug prints, then exits, on a busy port
                httpd = make_server(HOST, port, app, threaded=True)
        except (OSError, SystemExit):
            continue
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        if _answers_as_us(f"http://{HOST}:{port}/", token):
            return port, httpd, thread
        _say(f"  Port {port} is answered by another program on this computer; trying the next one.")
        httpd.shutdown()
        httpd.server_close()
    return None, None, None


def _write_shortcut(url: str) -> None:
    """Keep the "Open the app" shortcut next to the executable pointing at the real address."""
    if not getattr(sys, "frozen", False):
        return
    try:
        target = Path(sys.executable).resolve().parent / "Open the app.url"
        target.write_text(f"[InternetShortcut]\r\nURL={url}\r\n", encoding="utf-8")
    except OSError:
        pass


def _open_browser(url: str) -> bool:
    """Open the default browser, trying the OS's own opener if Python's helper fails."""
    try:
        if webbrowser.open(url):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            return subprocess.call(["open", url]) == 0
        return subprocess.call(["xdg-open", url]) == 0
    except Exception:  # noqa: BLE001
        return False


def _say(*lines: str) -> None:
    for line in lines:
        print(line)
    sys.stdout.flush()


def main() -> None:
    # Keep the window readable: no "development server" banner, no per-request lines.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    try:
        from flask import cli
        cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:  # noqa: BLE001
        pass
    app = create_app()
    from app.version import build_label
    _say("", f"Quality-of-Life Tracker ({build_label()}) is starting...")
    token = secrets.token_hex(8)
    app.add_url_rule("/__alive", "alive", lambda: token)  # lets the launcher check the port is really ours
    port, httpd, server = _start_server(app, PREFERRED_PORT, token)
    if httpd is None:
        _say(f"No free network port between {PREFERRED_PORT} and {PREFERRED_PORT + 19}. "
             "Close other copies of the app (or other programs) and try again.")
        return False
    url = f"http://{HOST}:{port}/"
    if port != PREFERRED_PORT:
        _say(f"  (Port {PREFERRED_PORT} was taken by another program, so the app is using port {port}.)")
    _write_shortcut(url)
    _say(
        "",
        "  The app is running. Open this address in your web browser:",
        "",
        f"      {url}",
        "",
    )
    with app.app_context():
        from app import phone
        if phone.is_enabled():
            phone_url = phone.url()
            if not phone.listener_running():
                _say(f"  Phone access is on, but port {phone.port()} could not be opened for phones.", "")
            elif phone_url:
                _say(f"  Phone access is on. On a phone on the same Wi-Fi, open: {phone_url}", "")
            else:
                _say("  Phone access is on, but this computer has no network address right now.", "")
    _say("  Leave this window open while you use the app. Close it to stop.", "")
    try:
        import webview  # pywebview (optional)
    except ImportError:
        webview = None
    if webview is None:
        if not _open_browser(url):
            _say("  (Your browser did not open by itself; please open the address above yourself.)")
        server.join()
        return True
    webview.create_window("Pet Quality-of-Life Tracker", url, width=1100, height=800, min_size=(700, 500))
    webview.start()
    return True


def _pause_if_frozen() -> None:
    """Keep the console window open so an error can be read before it closes."""
    if getattr(sys, "frozen", False):
        _say("", "Something went wrong. The details are above.")
        try:
            input("Press Enter to close this window.")
        except EOFError:
            pass


if __name__ == "__main__":
    frozen = getattr(sys, "frozen", False)
    if frozen:
        # Packaged build: keep data next to the executable, not in a temp folder.
        os.environ.setdefault("PET_QOL_DATA_DIR", str(Path(sys.executable).resolve().parent / "data"))
    if "--seed-demo" in sys.argv:
        from scripts.seed_demo import add_examples
        with create_app().app_context():
            added = add_examples()
        print(f"Added {', '.join(added)}. Start the app normally to see them." if added
              else "The example pets are already there.")
        sys.exit(0)
    try:
        ok = main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        _pause_if_frozen()
        raise
    if not ok:
        _pause_if_frozen()
        sys.exit(1)
