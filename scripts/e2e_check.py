"""Walk every user flow in a real browser and report problems (developer tool).

    CHROME_PATH=/path/to/chrome python scripts/e2e_check.py

Starts the app on its own port with a temporary data folder, so it never
touches your real data. Exit code 1 if anything failed.
"""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("E2E_PORT", "5077"))
BASE = f"http://127.0.0.1:{PORT}"
problems: list[str] = []


def check(cond, msg):
    if not cond:
        problems.append(msg)
        print("  FAIL", msg)
    else:
        print("  ok  ", msg)


def wait_for_server(proc):
    for _ in range(40):
        try:
            urllib.request.urlopen(BASE + "/", timeout=1)
            return
        except Exception:
            if proc.poll() is not None:
                raise SystemExit("server exited early")
            time.sleep(0.5)
    raise SystemExit("server did not start")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="qol-e2e-")
    env = {**os.environ, "PET_QOL_DATA_DIR": tmp, "PET_QOL_PORT": str(PORT), "PET_QOL_NO_BROWSER": "1"}
    proc = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        wait_for_server(proc)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
            ctx = browser.new_context(viewport={"width": 1100, "height": 800}, accept_downloads=True)
            page = ctx.new_page()
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            # 4xx responses are provoked on purpose (validation checks); only script and server errors count.
            page.on("console", lambda m: problems.append(f"console error: {m.text}")
                    if m.type == "error" and "status of 4" not in m.text else None)
            page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 500 else None)

            print("Onboarding")
            page.goto(BASE + "/")
            check("See the pattern" in page.content(), "landing shows for a fresh install")
            page.click("text=Start tracking")
            page.fill("input[name=name]", "Pepper")
            page.check("input[name=species][value=dog]")
            page.fill("input[name=breed]", "Beagle")
            page.fill("input[name=birth_date]", "2013-04-02")
            page.fill("textarea[name=diagnoses]", "Arthritis")
            page.click("button:has-text('Continue')")
            check("What does a good day look like for Pepper?" in page.content(), "marker setup after pet form")
            page.click("button:has-text('Continue')")
            check("at least 3" in page.content(), "marker setup rejects fewer than 3")
            boxes = page.locator("input[type=checkbox][name=labels]")
            for i in range(2):
                boxes.nth(i).check()
            page.locator("input[type=text][name=labels]").first.fill("Walks to the barn gate")
            page.click("button:has-text('Continue')")
            check("A reference point from before" in page.content(), "baseline after markers")
            page.check("input[name=good_day_pattern][value=mostly_good]")
            page.evaluate("document.getElementById('base-mobility').value=8; document.getElementById('base-mobility').dispatchEvent(new Event('input'))")
            page.check("input.unsure[data-for=base-hunger]")
            page.click("button:has-text('Save and finish')")
            check("You're ready." in page.content(), "ready page after baseline")
            page.click("text=Start tracking")

            print("Guided full check-in")
            check(page.locator("#step-nav").is_visible(), "guided mode on for a new entry")
            check(page.locator("#final-actions").is_hidden(), "save button hidden until review")
            page.click("label.day-option.good")
            page.click("#step-next")
            page.locator("input[name=markers]").nth(0).check()
            page.locator("input[name=markers]").nth(2).check()
            page.click("#step-next")
            check("How comfortable did Pepper seem today?" in page.inner_text("form"), "first score question shown")
            page.evaluate("var r=document.getElementById('score-hurt'); r.value=7; r.dispatchEvent(new Event('input'))")
            page.click("#step-next")
            page.evaluate("var r=document.getElementById('score-hunger'); r.value=9; r.dispatchEvent(new Event('input'))")
            for _ in range(6):
                page.click("#step-next")
            page.fill("textarea[name=notes]", "Slow on the stairs.")
            page.click("#step-next")
            review = page.inner_text("#review-list")
            check("Good day" in review and "7" in review and "Walks to the barn gate" in review, "review lists answers")
            check("–" in review, "untouched sliders show as unset in review")
            page.click("#final-actions button[type=submit]")
            check("Saved Pepper's check-in" in page.content(), "check-in saved")
            body = page.inner_text("body")
            check("Good day" in body and "2 of 3 good-day behaviors" in body and "8.0 / 10" in body, "dashboard reflects today (mean of the 2 scored)")
            check("Owner-estimated baseline" in body, "baseline mentioned on dashboard")
            if "Owner-estimated baseline" not in body:
                print("    dashboard text:", body[:600].replace("\n", " | "))

            print("Editing and quick check-in")
            page.goto(BASE + "/animals/1/checkin")
            check(page.locator("#final-actions").is_visible(), "editing an existing day opens the one-page form")
            check(page.locator("#score-hydration").evaluate("el => el.classList.contains('unset')"), "unscored slider still unset when editing")
            page.evaluate("var r=document.getElementById('score-hydration'); r.value=6; r.dispatchEvent(new Event('input'))")
            page.click("#final-actions button[type=submit]")
            check("7.3 / 10" in page.inner_text("body"), "third score added, mean updates")
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            page.goto(BASE + f"/animals/1/checkin/quick?date={yesterday}")
            page.click("label.day-option.bad")
            page.click("button:has-text('Done')")
            check("Done" in page.inner_text("h1"), "quick check-in done page")
            page.click("text=Back to today")
            check("Bad day" in page.inner_text("body"), "yesterday shows in recent list")

            print("Events, caregiver, calendar, trends, vet")
            page.goto(BASE + "/animals/1/events/new")
            page.fill("input[name=event_date]", yesterday)
            page.select_option("select[name=type]", "pain_medication_started")
            page.fill("input[name=title]", "Started gabapentin")
            page.click("button:has-text('Add')")
            check("Started gabapentin" in page.content(), "event listed")
            page.goto(BASE + "/animals/1/today")
            check("How are you doing?" in page.content(), "caregiver prompt after entries exist")
            page.click("text=Answer")
            page.check("input[name=status][value=harder]")
            page.click("button:has-text('Save')")
            check("Thank you" in page.content(), "caregiver saved")
            check("How are you doing?" not in page.inner_text("main") or "caregiver-card" not in page.content(), "prompt hidden for a week")
            page.goto(BASE + "/animals/1/calendar")
            check(page.locator(".glyph.good").count() >= 1 and page.locator(".glyph.bad").count() >= 1, "calendar glyphs")
            page.click("a[aria-label='Previous month']")
            check(page.url.endswith(f"month={(date.today().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')}"), "calendar previous month")
            page.goto(BASE + "/animals/1/trends?range=30")
            check(page.locator("canvas#chart-overall").count() == 1, "trend chart present")
            check(page.evaluate("Chart.getChart(document.getElementById('chart-overall')) !== undefined"), "trend chart rendered")
            check("Limited data" in page.inner_text("body"), "limited data stated honestly")
            page.goto(BASE + "/animals/1/trends/mobility")
            check("Mobility" in page.inner_text("h1"), "category page")
            page.goto(BASE + "/animals/1/vet")
            check("Prepare for my vet visit" in page.content(), "vet page")
            with page.expect_download() as dl:
                page.click("text=Download PDF")
            path = dl.value.path()
            check(Path(path).read_bytes()[:5] == b"%PDF-", "PDF downloads")
            page.goto(BASE + "/animals/1/behaviors")
            check("Walks to the barn gate" in page.content(), "behaviors page")

            print("Settings, backup, passing flow")
            page.goto(BASE + "/animals/1/settings")
            page.check("input[name=reminder][value=off]")
            page.click("button:has-text('Save')")
            check("Reminder setting saved" in page.content(), "reminder saved")
            page.goto(BASE + "/settings")
            with page.expect_download() as dl:
                page.click("text=Download backup")
            check(Path(dl.value.path()).stat().st_size > 1000, "backup downloads")
            page.goto(BASE + "/animals/1/passed")
            check("sorry you're saying goodbye" in page.content(), "passing page copy")
            page.click("button:has-text('Continue')")
            check("In memory of Pepper" in page.content(), "after-passing options")
            page.click("button:has-text('Keep')")
            body = page.inner_text("body")
            check("In memory of Pepper" in body and "No check-in recorded" not in body, "kept profile, no prompts")
            check("Check in" not in page.inner_text(".topbar"), "no check-in button for a remembered pet")
            page.goto(BASE + "/animals/1/trends")
            check(page.locator("canvas#chart-overall").count() == 1, "trends still available after passing")
            page.goto(BASE + "/animals/1/remove")
            page.fill("input[name=confirm_name]", "wrong")
            page.click("button:has-text('Remove permanently')")
            check("type the name exactly" in page.content(), "remove rejects wrong name")
            page.fill("input[name=confirm_name]", "pepper")
            page.click("button:has-text('Remove permanently')")
            check("have been removed" in page.content() and "See the pattern" in page.content(), "removed, back to landing")

            print("Second pet, mobile")
            page.goto(BASE + "/animals/new")
            page.fill("input[name=name]", "Mochi"); page.check("input[name=species][value=cat]")
            page.click("button:has-text('Continue')")
            for i in range(3):
                page.locator("input[type=checkbox][name=labels]").nth(i).check()
            page.click("button:has-text('Continue')")
            page.click("button:has-text('Skip for now')")
            check("You're ready." in page.content(), "skip baseline works")
            mobile = ctx.new_page()
            mobile.set_viewport_size({"width": 390, "height": 800})
            mobile.on("pageerror", lambda e: problems.append(f"mobile pageerror: {e}"))
            mobile.goto(BASE + "/animals/2/today")
            check(mobile.locator(".nav").bounding_box()["y"] > 600, "bottom navigation on phones")
            check(mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll on phone dashboard")
            mobile.goto(BASE + "/animals/2/checkin")
            check(mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll on phone check-in")
            browser.close()
    finally:
        proc.terminate()
        try:
            err = proc.communicate(timeout=5)[1]
        except subprocess.TimeoutExpired:
            proc.kill(); err = ""
        tracebacks = [line for line in err.splitlines() if "Traceback" in line or "Error" in line and "WARNING" not in line]
        if tracebacks:
            problems.append("server log: " + "; ".join(tracebacks[:5]))
    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for pr in problems:
            print(" -", pr)
        return 1
    print("All flows passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
