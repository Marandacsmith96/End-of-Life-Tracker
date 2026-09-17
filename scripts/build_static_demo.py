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
PETS = {1: "", 2: "bruno-"}   # animal id -> file prefix (the first pet owns the plain names)
MAX_PAGES = 220

BANNER = (
    '<aside class="notice demo-notice" aria-label="Demo">'
    '<span><strong>Read-only demo</strong> with sample data for two fictional dogs. Saving is switched off here; '
    'run the app on your own computer to track a real pet.</span>'
    '<span class="presets"><a class="chip" href="index.html">Maggie · stable, then declining</a>'
    '<a class="chip" href="bruno-index.html">Bruno · steady decline</a>'
    '<a class="chip quiet" href="how-it-works.html">How it works</a></span></aside>'
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
    m = re.match(r"^/animals/(\d+)/(.*)$", path)
    if m and int(m.group(1)) in PETS:
        pet, rest = int(m.group(1)), m.group(2)
        pre = PETS[pet]
        if rest == "export.pdf":
            return pre + "summary.pdf"
        if rest in ("select", "archive", "unarchive", "keep", "photo", "reminder", "passed", "remove",
                    "checkin/quick") or rest.startswith("photo/"):
            target = {"passed": "passed.html", "remove": "remove.html", "checkin/quick": "quick.html"}.get(rest)
            return pre + target if target else None
        if rest == "today":
            return pre + (f"today-range-{query['range'][0]}.html" if "range" in query else "index.html")
        if rest == "checkin":
            return pre + "checkin.html"  # every date links to the same sample check-in
        if rest == "calendar" and "month" in query:
            year, month = (int(x) for x in query["month"][0].split("-"))
            from datetime import date
            today = date.today()
            if (today.year - year) * 12 + today.month - month > 4:
                return None  # only the last few months are worth snapshotting
        keep = "".join(f"-{k}-{query[k][0]}" for k in sorted(query) if k in KEEP_QUERY)
        return pre + re.sub(r"[^a-z0-9._-]+", "-", (rest + keep).lower()) + ".html"
    if path == "/animals/new":
        return "add-pet.html"
    return None


def rewrite(page: str, seen: set, queue: deque) -> str:
    # "Open" / pet-switch forms post to /select; in the snapshot they become plain links.
    page = re.sub(
        r'<form method="post" action="/animals/(\d+)/select"[^>]*>\s*<button class="([^"]*)" type="submit">([^<]*)</button>\s*</form>',
        lambda m: f'<a class="{m.group(2)}" href="{PETS.get(int(m.group(1)), "")}index.html">{m.group(3)}</a>'
        if int(m.group(1)) in PETS else m.group(0), page)

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
        s["current_animal_id"] = 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ROOT / "app" / "static", OUT / "static")
    for pet, pre in PETS.items():
        (OUT / f"{pre}summary.pdf").write_bytes(client.get(f"/animals/{pet}/export.pdf?range=90").data)

    seen = {"index.html"}
    queue = deque([("/how-it-works", "how-it-works.html"), ("/more", "more.html"), ("/settings", "settings.html"),
                   ("/pets", "pets.html"), ("/animals/new", "add-pet.html")])
    for pet, pre in PETS.items():
        queue += [(f"/animals/{pet}/today", f"{pre}index.html"), (f"/animals/{pet}/checkin", f"{pre}checkin.html"),
                  (f"/animals/{pet}/checkin/quick", f"{pre}quick.html")]
    seen.update(t for _, t in queue)
    written = 0
    while queue and written < MAX_PAGES:
        url, target = queue.popleft()
        pet_match = re.match(r"^/animals/(\d+)/", url)
        with client.session_transaction() as sess:   # navigation reflects the pet being crawled
            sess["current_animal_id"] = int(pet_match.group(1)) if pet_match else 1
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
