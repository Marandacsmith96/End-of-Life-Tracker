"""Run the tracker in its own desktop window (optional).

Requires the optional dependency:
    pip install pywebview

Then:
    python desktop.py

If pywebview is not installed this falls back to run.py's behaviour and
opens the app in your default browser instead.
"""
import os
import sys
import threading
from pathlib import Path

from app import create_app

HOST = "127.0.0.1"
PORT = int(os.environ.get("PET_QOL_PORT", "5000"))


def main() -> None:
    app = create_app()
    server = threading.Thread(
        target=lambda: app.run(host=HOST, port=PORT, debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    url = f"http://{HOST}:{PORT}/"
    try:
        import webview  # pywebview
    except ImportError:
        import webbrowser
        print("pywebview is not installed; opening in your browser instead.")
        print("Install it with: pip install pywebview")
        webbrowser.open(url)
        server.join()
        return
    webview.create_window("Pet Quality-of-Life Tracker", url, width=1100, height=800, min_size=(700, 500))
    webview.start()


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        # Packaged build: keep data next to the executable, not in a temp folder.
        os.environ.setdefault("PET_QOL_DATA_DIR", str(Path(sys.executable).resolve().parent / "data"))
    main()
