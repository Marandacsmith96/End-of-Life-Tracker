"""Start the Pet Quality-of-Life Tracker on your own computer.

Usage:
    python run.py

Your browser opens at http://127.0.0.1:5000 automatically. Everything stays
on this machine; no internet connection is needed. Press Ctrl+C to stop.

Set FLASK_DEBUG=1 to get auto-reload and tracebacks while developing.
"""
import os
import threading
import webbrowser

from app import create_app

HOST = "127.0.0.1"
PORT = int(os.environ.get("PET_QOL_PORT", "5000"))

app = create_app()


def _open_browser() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}/")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    # With the debug reloader the script runs twice; only open a tab once.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        if os.environ.get("PET_QOL_NO_BROWSER") != "1":
            threading.Timer(1.0, _open_browser).start()
    app.run(host=HOST, port=PORT, debug=debug)
