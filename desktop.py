"""Start the tracker and open it in a browser (also the packaged build's entry point).

    python desktop.py

With the optional ``pywebview`` package installed the app opens in its own
window instead of a browser tab:

    pip install pywebview
"""
import logging
import os
import socket
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


def _free_port(start: int) -> int:
    """The preferred port, or the next free one if something else is using it."""
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
                return port
            except OSError:
                continue
    return start


def _wait_until_listening(port: int, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(0.2)
    return False


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
    port = _free_port(PREFERRED_PORT)
    url = f"http://{HOST}:{port}/"
    server = threading.Thread(
        target=lambda: app.run(host=HOST, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    _say("", "Quality-of-Life Tracker is starting...")
    if not _wait_until_listening(port):
        _say("The app did not start. Please send the text in this window to whoever set it up.")
        return
    _say(
        "",
        "  The app is running. Open this address in your web browser:",
        "",
        f"      {url}",
        "",
        "  Leave this window open while you use the app. Close it to stop.",
        "",
    )
    try:
        import webview  # pywebview (optional)
    except ImportError:
        webview = None
    if webview is None:
        if not _open_browser(url):
            _say("  (Your browser did not open by itself; please open the address above yourself.)")
        server.join()
        return
    webview.create_window("Pet Quality-of-Life Tracker", url, width=1100, height=800, min_size=(700, 500))
    webview.start()


if __name__ == "__main__":
    frozen = getattr(sys, "frozen", False)
    if frozen:
        # Packaged build: keep data next to the executable, not in a temp folder.
        os.environ.setdefault("PET_QOL_DATA_DIR", str(Path(sys.executable).resolve().parent / "data"))
    if "--seed-demo" in sys.argv:
        from scripts.seed_demo import seed
        seed(reset=False)
        print("Demo pets added. Start the app normally to see them.")
        sys.exit(0)
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        if frozen:
            # Keep the window open so the error can be read (it would close instantly otherwise).
            _say("", "Something went wrong. The details are above.")
            try:
                input("Press Enter to close this window.")
            except EOFError:
                pass
        raise
