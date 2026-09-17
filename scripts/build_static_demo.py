"""Build a read-only, browsable snapshot of the Maggie demo (developer tool).

    python scripts/build_static_demo.py [out_dir]

Runs the app against a temporary data folder seeded with Maggie, fetches the
pages, rewrites links to relative files, disables forms, and writes a static
site to dist/demo/ (index.html plus supporting files). Useful for hosting a
demo where a Python server isn't available.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "demo"
PET = 1
MAX_PAGES = 120

BANNER = (
    '<aside class="notice demo-notice" aria-label="Demo">'
    '<span><strong>Read-only demo</strong> with sample data for Maggie, a fictional 13-year-old Golden Retriever. '
    'Saving is switched off here. Run the app on your own computer to track a real pet.</span>'
    '<a class="button small secondary" href="how-it-works.html">How it works</a></aside>'
)
DEMO_SCRIPT = """<script>
(function () {
  document.querySelectorAll('form').forEach(function (f) {
    f.addEventListener('submit', function (e) { e.preventDefault(); alert('This is a read-only demo. Run the app locally to save a check-in.'); });
  });
})();
</script>"""

SHORTCUTS = {"/": "index.html", "/today": "index.html", "/trends": "trends.html", "/calendar": "calendar.html",
             "/vet": "vet.html", "/more": "more.html", "/settings": "settings.html", "/how-it-works": "how-it-works.html",
             "/pets": "pets.html"}
KEEP_QUERY = {"range", "month", "since"}


def to_file(url: str) -> str | None:
    """Map an app URL to a relative file name, or None if it has no static equivalent."""
    if url.startswith(("http", "mailto:", "#", "javascript:")):
        return None
    parts = urlsplit(url)
    path, query = parts.path, parse_qs(parts.query)
    if path.startswith("/static/"):
        return path[1:]
    if path in SHORTCUTS and not query:
        return SHORTCUTS[path]
    prefix = f"/animals/{PET}/"
    if path == prefix + "export.pdf":
        return "maggie-summary.pdf"
    if path.startswith(prefix):
        rest = path[len(prefix):]
        if rest in ("select", "archive", "unarchive", "keep", "photo", "reminder", "passed", "remove",
                    "checkin/quick") or rest.startswith("photo/"):
            return {"passed": "passed.html", "remove": "remove.html", "checkin/quick": "quick.html"}.get(rest)
        if rest == "today":
            return "index.html"
        if rest == "checkin":
            return "checkin.html"  # every date links to the same sample check-in
        if rest == "calendar" and "month" in query:
            year, month = (int(x) for x in query["month"][0].split("-"))
            from datetime import date
            today = date.today()
            if (today.year - year) * 12 + today.month - month > 4:
                return None  # only the last few months are worth snapshotting
        keep = "".join(f"-{k}-{query[k][0]}" for k in sorted(query) if k in KEEP_QUERY)
        return re.sub(r"[^a-z0-9._-]+", "-", (rest + keep).lower()) + ".html"
    if path == "/animals/new":
        return "add-pet.html"
    return None


def rewrite(page: str, seen: set, queue: deque) -> str:
    def sub(match):
        attr, url = match.group(1), html.unescape(match.group(2))
        target = to_file(url)
        if target is None:
            return f'{attr}="#"' if attr in ("href", "action") else match.group(0)
        if target.endswith(".html") and target not in seen and not url.startswith("/static/"):
            seen.add(target)
            queue.append((url, target))
        return f'{attr}="{target}"'
    page = re.sub(r'\b(href|action|src)="([^"]*)"', sub, page)
    page = page.replace('formaction="', 'data-formaction="')
    page = page.replace('<main class="content', BANNER + '\n  <main class="content', 1)
    return page.replace("</body>", DEMO_SCRIPT + "\n</body>")


def as_fragment(page: str) -> str:
    """The published index is wrapped in its own skeleton, so ship head tags plus body content."""
    head = re.search(r"<head>(.*?)</head>", page, re.S).group(1)
    body = re.search(r"<body[^>]*>(.*?)</body>", page, re.S).group(1)
    head = re.sub(r"<meta[^>]*>", "", head)
    head = re.sub(r"<title>.*?</title>", "<title>Quality-of-Life Tracker Demo</title>", head, flags=re.S)
    return head.strip() + "\n" + body.strip() + "\n" + DEMO_SCRIPT


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="qol-demo-")
    env = {**os.environ, "PET_QOL_DATA_DIR": tmp}
    subprocess.run([sys.executable, "scripts/seed_demo.py"], cwd=ROOT, env=env, check=True, capture_output=True)
    os.environ["PET_QOL_DATA_DIR"] = tmp
    from app import create_app  # noqa: E402  (after the env var is set)

    app = create_app()
    client = app.test_client()
    with client.session_transaction() as s:
        s["current_animal_id"] = PET

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ROOT / "app" / "static", OUT / "static")
    (OUT / "maggie-summary.pdf").write_bytes(client.get(f"/animals/{PET}/export.pdf?range=90").data)

    seen = {"index.html"}
    queue = deque([(f"/animals/{PET}/today", "index.html"), ("/how-it-works", "how-it-works.html"),
                   (f"/animals/{PET}/checkin", "checkin.html"), (f"/animals/{PET}/checkin/quick", "quick.html"),
                   ("/more", "more.html"), ("/settings", "settings.html"), ("/pets", "pets.html"),
                   ("/animals/new", "add-pet.html")])
    seen.update(t for _, t in queue)
    written = 0
    while queue and written < MAX_PAGES:
        url, target = queue.popleft()
        response = client.get(url, follow_redirects=True)
        if response.status_code != 200:
            print("skip", url, response.status_code)
            continue
        page = rewrite(response.data.decode(), seen, queue)
        if target == "index.html":
            page = as_fragment(page)
        (OUT / target).write_text(page, encoding="utf-8")
        written += 1
    (OUT / "static" / "style.css").open("a", encoding="utf-8").write(
        "\n.demo-notice { background: var(--accent-soft); border-color: var(--accent-soft); }\n")
    print(f"wrote {written} pages to {OUT}")


if __name__ == "__main__":
    main()
