"""Take screenshots of the running app for the README (developer tool).

    python run.py                      # in one terminal
    python scripts/screenshot.py       # in another; writes docs/screenshots/*.png
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    "dashboard": "/",
    "pet": "/animals/1",
    "log": "/animals/1/log",
    "history": "/animals/1/history?range=30",
    "medications": "/animals/1/medications",
    "export": "/animals/1/export",
    "settings": "/settings",
}

with sync_playwright() as p:
    # CHROME_PATH lets you point at an already-installed Chromium instead of
    # running "playwright install".
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
    page = browser.new_page(viewport={"width": 1100, "height": 800}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    for name, path in PAGES.items():
        page.goto(BASE + path, wait_until="networkidle")
        # Sticky bars render mid-page in full-page captures; pin them for the shot.
        page.add_style_tag(content=".sticky-actions, .topbar { position: static !important; }")
        page.screenshot(path=OUT / f"{name}.png", full_page=True)
        print("saved", name)
    browser.close()
    if errors:
        print("BROWSER ERRORS:", *errors, sep="\n  ")
        sys.exit(1)
