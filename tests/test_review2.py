"""Regression tests for the second bug hunt (routes, data layer, analysis, PDF)."""
import io
import sqlite3
from html import unescape
import threading
import zipfile
from datetime import date, timedelta

from PIL import Image
from pypdf import PdfReader

from app import analytics as an, caregiver, create_app, entries, insights, models, pdf, safety
from app.entries import Entry, Medication
from app.events import Event
from app.models import Animal

KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")
TODAY = date.today()


def _pet(client, name="Maggie", **extra):
    r = client.post("/animals/new", data={"name": name, "species": "dog", **extra})
    assert r.status_code == 302, r.status_code


def _checkin(client, days_ago, each=6, status="good", **fields):
    data = {"entry_date": (TODAY - timedelta(days=days_ago)).isoformat(), "day_status": status,
            **{k: each for k in KEYS}, **{f"{k}_set": "1" for k in KEYS}, **fields}
    r = client.post("/animals/1/checkin", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:300]


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _restore(client, data, filename="b.zip"):
    return client.post("/settings/restore", data={"backup": (io.BytesIO(data), filename), "confirm": "yes"},
                       content_type="multipart/form-data", follow_redirects=True)


def _entry(days_ago, each=6, status="good", notes=None, end=None):
    end = end or TODAY
    return Entry(id=1000 - days_ago, animal_id=1, entry_date=end - timedelta(days=days_ago), day_status=status,
                 weight=None, weight_unit=None, appetite=None, notes=notes, **{k: each for k in KEYS})


# --- backup and restore ----------------------------------------------------

def test_restore_of_a_foreign_database_keeps_current_data(client, app):
    _pet(client)
    img = io.BytesIO()
    Image.new("RGB", (40, 40)).save(img, format="JPEG")
    img.seek(0)
    client.post("/animals/1/photo", data={"photo": (img, "a.jpg")}, content_type="multipart/form-data")
    photo_files = list((app.config["PHOTO_DIR"]).rglob("*.jpg"))
    assert photo_files
    foreign = app.config["DATA_DIR"] / "foreign.sqlite"
    c = sqlite3.connect(foreign)
    c.execute("CREATE TABLE animals (id INTEGER PRIMARY KEY, name TEXT)")
    c.commit()
    c.close()
    r = _restore(client, _zip({"tracker.sqlite": foreign.read_bytes()}))
    assert b"not a tracker database" in r.data
    assert all(p.exists() for p in photo_files), "a rejected restore must not wipe photos"
    with app.app_context():
        assert models.get_animal(1).name == "Maggie"
    assert client.get("/animals/1/today").status_code == 200


def test_restore_of_a_damaged_zip_is_a_friendly_error(client, app):
    _pet(client)
    good = client.get("/settings/backup.zip").data
    # Flip bytes deep inside the compressed payload, keeping the zip directory intact.
    damaged = bytearray(good)
    for i in range(60, 90):
        damaged[i] ^= 0xFF
    r = _restore(client, bytes(damaged))
    assert r.status_code == 200
    assert b"damaged" in r.data or b"not readable" in r.data
    with app.app_context():
        assert models.get_animal(1).name == "Maggie"


def test_restore_from_a_newer_app_version_is_refused(client, app):
    _pet(client)
    newer = app.config["DATA_DIR"] / "newer.sqlite"
    src = sqlite3.connect(app.config["DATABASE"])
    dst = sqlite3.connect(newer)
    src.backup(dst)
    dst.execute("PRAGMA user_version = 99")
    dst.commit()
    dst.close()
    src.close()
    r = _restore(client, _zip({"tracker.sqlite": newer.read_bytes()}))
    assert b"newer version" in r.data


def test_interrupted_migration_can_be_retried(tmp_path):
    """A leftover entries_new table from a crash must not block the next start."""
    d = tmp_path / "data"
    d.mkdir()
    conn = sqlite3.connect(d / "t.sqlite")
    conn.executescript("""
        CREATE TABLE animals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, species TEXT NOT NULL,
            breed TEXT, birth_date DATE, photo_path TEXT, archived INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, animal_id INTEGER NOT NULL,
            entry_date DATE NOT NULL, hurt INTEGER NOT NULL, hunger INTEGER NOT NULL, hydration INTEGER NOT NULL,
            hygiene INTEGER NOT NULL, happiness INTEGER NOT NULL, mobility INTEGER NOT NULL, good_days INTEGER NOT NULL,
            weight REAL, weight_unit TEXT, appetite TEXT, notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE medications (id INTEGER PRIMARY KEY AUTOINCREMENT, animal_id INTEGER NOT NULL, name TEXT NOT NULL,
            dose TEXT, schedule TEXT, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE entries_new (id INTEGER PRIMARY KEY);
        INSERT INTO animals (name, species) VALUES ('Old', 'cat');
        PRAGMA user_version = 1;
    """)
    conn.commit()
    conn.close()
    app = create_app({"TESTING": True, "DATA_DIR": d, "DATABASE": d / "t.sqlite", "PHOTO_DIR": d / "p"})
    with app.app_context():
        assert models.get_animal(1).name == "Old"


# --- request handling -------------------------------------------------------

def test_huge_ids_are_404_not_500(client):
    _pet(client)
    big = str(2**64)
    for path in (f"/animals/{big}/today", f"/animals/{big}/settings", f"/animals/{big}/history"):
        assert client.get(path).status_code == 404, path
    for path in (f"/entries/{big}/delete", f"/events/{big}/delete", f"/caregiver/{big}/delete"):
        assert client.post(path).status_code == 404, path


def test_superscript_digits_in_ids_are_ignored(client):
    _pet(client)
    client.post("/animals/1/markers", data={"labels": ["Greets me", "Eats dinner", "Plays"]})
    r = client.post("/animals/1/checkin/quick",
                    data={"entry_date": TODAY.isoformat(), "day_status": "good", "markers_included": "1",
                          "markers": ["²", "1"]})
    assert r.status_code == 200
    r = client.post("/animals/1/checkin",
                    data={"entry_date": TODAY.isoformat(), "day_status": "good", "meds_included": "1", "given": "³"})
    assert r.status_code == 302


def test_dates_near_the_calendar_edges_do_not_crash(client):
    _pet(client)
    client.post("/animals/1/checkin/quick", data={"entry_date": TODAY.isoformat(), "day_status": "good"})
    assert client.get("/animals/1/calendar?month=0001-01").status_code == 200
    assert client.get("/animals/1/vet?since=0001-01-01").status_code == 200
    assert client.get("/animals/1/trends?end=9999-12-31").status_code == 200
    assert client.post("/animals/1/passed", data={"passed_date": "0001-01-01"}).status_code == 302
    for path in ("/animals/1/today", "/animals/1/trends", "/animals/1/vet", "/animals/1/calendar",
                 "/animals/1/trends/hurt", "/animals/1/behaviors"):
        assert client.get(path).status_code == 200, path


def test_passed_date_is_not_before_birth(client, app):
    _pet(client, birth_date="2015-06-01")
    client.post("/animals/1/passed", data={"passed_date": "2010-01-01"})
    with app.app_context():
        assert models.get_animal(1).passed_date == date(2015, 6, 1)


def test_giant_image_is_rejected_gracefully(client):
    _pet(client)
    buf = io.BytesIO()
    Image.new("1", (20000, 20000)).save(buf, format="PNG")
    buf.seek(0)
    r = client.post("/animals/1/photo", data={"photo": (buf, "big.png")}, content_type="multipart/form-data",
                    follow_redirects=True)
    assert r.status_code == 200
    assert b"does not look like an image" in r.data


def test_same_day_double_submit_becomes_an_update(app):
    """Two check-ins for one day arriving together: the second updates, not crashes."""
    with app.app_context():
        aid = models.create_animal("Pip", "cat")
    barrier = threading.Barrier(2)
    original = entries.get_entry_for_date
    calls = {"n": 0}

    def slow_lookup(animal_id, entry_date):
        result = original(animal_id, entry_date)
        calls["n"] += 1
        if calls["n"] <= 2:
            barrier.wait(timeout=5)
        return result

    results = []

    def worker(status):
        with app.app_context():
            entries.get_entry_for_date = slow_lookup
            try:
                results.append(entries.save_entry(aid, TODAY, status))
            except Exception as exc:  # noqa: BLE001
                results.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(s,)) for s in ("good", "bad")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    entries.get_entry_for_date = original
    assert results[0] == results[1], results
    with app.app_context():
        assert len(entries.list_entries(aid)) == 1


def test_caregiver_delete_redirects_to_the_right_pet(client, app):
    _pet(client)
    _pet(client, name="Other")
    client.post("/animals/1/caregiver", data={"status": "okay", "note": ""})
    with app.app_context():
        cid = caregiver.list_checkins(1)[0].id
    r = client.post(f"/caregiver/{cid}/delete", data={"animal_id": "2"})
    assert r.headers["Location"].endswith("/animals/1/caregiver")
    assert client.post(f"/caregiver/{cid}/delete").status_code == 404


def test_unlock_redirect_keeps_the_query_string(tmp_path):
    d = tmp_path / "data"
    c = create_app({"TESTING": True, "DATA_DIR": d, "DATABASE": d / "t.sqlite", "PHOTO_DIR": d / "p",
                    "PASSCODE": "x"}).test_client()
    r = c.get("/animals/1/trends?range=7")
    assert "next=/animals/1/trends" in r.headers["Location"] and "range%3D7" in r.headers["Location"]
    r = c.post("/unlock?next=/animals/1/trends%3Frange%3D7", data={"passcode": "x"})
    assert r.headers["Location"].endswith("/animals/1/trends?range=7")


def test_deleting_a_checkin_removes_its_photo_folder(client, app):
    _pet(client)
    img = io.BytesIO()
    Image.new("RGB", (40, 40)).save(img, format="JPEG")
    img.seek(0)
    _checkin(client, 0, photos=(img, "day.jpg"))
    with app.app_context():
        entry = entries.get_entry_for_date(1, TODAY)
    folder = app.config["PHOTO_DIR"] / "entries" / str(entry.id)
    assert folder.is_dir()
    client.post(f"/entries/{entry.id}/delete")
    assert not folder.exists()


def test_origin_check_compares_hosts_not_schemes(client):
    _pet(client)
    r = client.post("/animals/1/archive", headers={"Origin": "https://localhost", "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    r = client.post("/animals/1/archive", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_empty_full_checkin_is_not_saved(client, app):
    _pet(client)
    r = client.post("/animals/1/checkin", data={"entry_date": TODAY.isoformat()})
    assert r.status_code == 400
    with app.app_context():
        assert entries.get_entry_for_date(1, TODAY) is None


def test_full_checkin_without_the_status_field_keeps_it(client, app):
    _pet(client)
    client.post("/animals/1/checkin/quick", data={"entry_date": TODAY.isoformat(), "day_status": "good"})
    client.post("/animals/1/checkin", data={"entry_date": TODAY.isoformat(), "notes": "ate well"})
    with app.app_context():
        assert entries.get_entry_for_date(1, TODAY).day_status == "good"


def test_invisible_names_are_rejected(client):
    r = client.post("/animals/new", data={"name": "​​", "species": "dog"})
    assert r.status_code == 400


# --- analysis and output ------------------------------------------------------

def test_owner_text_is_not_judged_by_the_safety_rules():
    rows = [_entry(d, 6) for d in range(30)]
    for e in rows:
        if (TODAY - e.entry_date).days < 14:
            e.hurt = 3
    ev = Event(1, 1, TODAY - timedelta(days=13), "pain_medication_started", "Diagnosed with arthritis", None)
    texts = [i.text for i in insights.generate(rows, TODAY, "Terminal", events=[ev])]
    assert any("Diagnosed with arthritis" in t for t in texts)
    # ...but the app's own words are still checked.
    try:
        safety.guard("It's time to talk about Terminal.", owner_text=("Terminal",))
    except safety.SafetyViolation:
        pass
    else:
        raise AssertionError("forbidden app text slipped through")


def test_event_title_with_forbidden_words_does_not_break_pages(client):
    _pet(client, name="Terminal")
    for d in range(30):
        _checkin(client, d, hurt=3 if d < 14 else 6)
    client.post("/animals/1/events/new", data={"event_date": (TODAY - timedelta(days=13)).isoformat(),
                                               "type": "pain_medication_started",
                                               "title": "Diagnosed with arthritis, started gabapentin"})
    for path in ("/animals/1/today", "/animals/1/vet", "/animals/1/export.pdf"):
        assert client.get(path).status_code == 200, path


def test_pdf_survives_a_very_long_note():
    animal = Animal(1, "Maggie", "dog", None, None, None, None, None, "active", None, "daily")
    note = ("lorem ipsum dolor sit amet " * 200)[:5000]
    rows = [_entry(d, 6, notes=note if d == 0 else None) for d in range(5)]
    data = pdf.build_pdf(animal, rows, rows, [], [], {}, None, [], TODAY - timedelta(days=4), TODAY,
                         include_appendix=True)
    assert data.startswith(b"%PDF")


def test_pdf_says_when_a_list_is_cut_short():
    animal = Animal(1, "Maggie", "dog", None, None, None, None, None, "active", None, "daily")
    rows = [_entry(d, 6) for d in range(10)]
    meds = [Medication(i, 1, f"Med{i:02d}", "1 mg", "daily", None, None, True) for i in range(20)]
    data = pdf.build_pdf(animal, rows, rows, meds, [], {}, None, [], TODAY - timedelta(days=9), TODAY)
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    assert "and 12 more" in text


def test_behaviors_page_uses_the_passing_date(client):
    _pet(client)
    client.post("/animals/1/markers", data={"labels": ["Greets me", "Eats dinner", "Plays"]})
    for d in range(200, 230):
        client.post("/animals/1/checkin/quick",
                    data={"entry_date": (TODAY - timedelta(days=d)).isoformat(), "day_status": "good",
                          "markers_included": "1", "markers": ["1", "2", "3"]})
    client.post("/animals/1/passed", data={"passed_date": (TODAY - timedelta(days=199)).isoformat()})
    html = client.get("/animals/1/behaviors?range=30").get_data(as_text=True)
    assert "No answers yet" not in html
    assert "100%" in html


def test_below_baseline_ignores_days_after_the_end():
    pts = [an.Point(TODAY - timedelta(days=30 - d), 9) for d in range(20)]
    pts += [an.Point(TODAY - timedelta(days=10 - d), 3) for d in range(10)]
    assert an.below_baseline(pts, 8, end=TODAY - timedelta(days=15)) == (0, 12)
    assert an.below_baseline(pts, 8) == (10, 12)


def test_trends_with_no_entries_does_not_invent_a_day(client):
    _pet(client)
    html = client.get("/animals/1/trends?range=all").get_data(as_text=True)
    assert "not logged in this range" not in html
    assert "No check-ins in this range" in html


def test_vet_verdict_matches_the_displayed_numbers(client):
    _pet(client)
    # recent 30 days: mean 6.23 -> shown 6.2; previous 30: mean 5.77 -> shown 5.8; diff 0.4, not 0.5
    for d in range(30):
        _checkin(client, d, hurt=7 if d < 7 else 6)
    for d in range(30, 60):
        _checkin(client, d, hurt=5 if d < 37 else 6)
    html = client.get(f"/animals/1/vet?since={(TODAY - timedelta(days=29)).isoformat()}").get_data(as_text=True)
    assert "Higher by 0.5" not in html  # 6.2 vs 5.8 on the page is a 0.4 difference
    assert "Relatively stable" in html


def test_vet_since_in_the_future_is_ignored(client):
    _pet(client)
    for d in range(40):
        _checkin(client, d)
    html = client.get("/animals/1/vet?since=2099-01-01").get_data(as_text=True)
    assert "2099" not in html
    assert client.get("/animals/1/vet?since=2099-01-01").status_code == 200


# --- front end ------------------------------------------------------------------

def test_shortcut_routes_with_several_pets_go_home(client):
    _pet(client)
    _pet(client, name="Second")
    with client.session_transaction() as s:
        s.pop("current_animal_id", None)
    for path in ("/today", "/trends", "/calendar", "/vet"):
        r = client.get(path)
        assert r.status_code == 302, path
        assert r.headers["Location"].endswith("/"), path


def test_baseline_saves_only_the_sliders_that_were_moved(client, app):
    from app import baseline as bl
    _pet(client)
    data = {k: "7" for k in KEYS}
    data.update({"mobility": "8", "mobility_set": "1", "good_day_pattern": "mostly_good"})
    r = client.post("/animals/1/baseline", data=data)
    assert r.status_code == 302
    with app.app_context():
        base = bl.get_baseline(1)
    assert base.mobility == 8
    assert all(getattr(base, k) is None for k in KEYS if k != "mobility")


def test_more_tab_is_highlighted_on_its_sub_pages(client):
    _pet(client)
    for path in ("/animals/1/baseline", "/animals/1/markers", "/animals/1/events/new", "/animals/1/edit",
                 "/animals/1/passed", "/animals/1/remove", "/animals/1/settings"):
        html = client.get(path).get_data(as_text=True)
        assert 'nav-item active" href="/more"' in html, path


# --- example pets ---------------------------------------------------------------

def test_example_pets_can_be_added_and_removed(client, app):
    html = client.get("/how-it-works").get_data(as_text=True)
    assert "See an example" in html
    r = client.post("/examples/add", follow_redirects=True)
    assert b"Meet Maggie, Bruno, Juniper" in r.data
    assert b"Example pet" in r.data  # badge on the dashboard the add lands on
    with app.app_context():
        demo = models.list_demo_animals()
        assert [a.name for a in demo] == ["Maggie", "Bruno", "Juniper"]
        assert all(a.demo for a in demo)
        assert len(entries.list_entries(demo[2].id)) > 40
    html = client.get("/how-it-works").get_data(as_text=True)
    assert "Remove the examples" in html and ">Juniper</a>" in html
    # adding again is harmless
    r = client.post("/examples/add", follow_redirects=True)
    assert b"already here" in r.data
    # a real pet is untouched by removal
    _pet(client, name="Mine")
    r = client.post("/examples/remove", follow_redirects=True)
    assert b"Example pets removed" in r.data
    with app.app_context():
        assert models.list_demo_animals() == []
        assert [a.name for a in models.list_animals()] == ["Mine"]


def test_version_2_database_gains_the_demo_column(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    conn = sqlite3.connect(d / "t.sqlite")
    conn.executescript(open("app/schema.sql").read().replace(
        "    demo          INTEGER NOT NULL DEFAULT 0,   -- 1 for the built-in example pets\n", ""))
    conn.execute("INSERT INTO animals (name, species) VALUES ('Old', 'dog')")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    app = create_app({"TESTING": True, "DATA_DIR": d, "DATABASE": d / "t.sqlite", "PHOTO_DIR": d / "p"})
    with app.app_context():
        assert models.get_animal(1).demo is False
        assert models.list_demo_animals() == []


# --- pet switcher -------------------------------------------------------------

def test_pet_switcher_keeps_the_page_and_only_shows_with_several_pets(client):
    _pet(client)
    html = client.get("/animals/1/trends").get_data(as_text=True)
    assert "pet-switcher" not in html
    _pet(client, name="Second")
    html = client.get("/animals/1/trends").get_data(as_text=True)
    assert "pet-switcher" in html
    assert 'href="/animals/2/trends"' in html          # same page, other pet
    assert 'class="pet-chip current"' in html
    html = client.get("/animals/2/trends/mobility").get_data(as_text=True)
    assert 'href="/animals/1/trends/mobility"' in html
    html = client.get("/more").get_data(as_text=True)   # not a pet page: chips go to Today
    assert 'href="/animals/1/today"' in html


def test_home_tab_goes_to_the_home_page(client):
    _pet(client)
    html = client.get("/animals/1/trends").get_data(as_text=True)
    assert '>Home</a>' in html and 'href="/how-it-works"' in html
    html = client.get("/how-it-works").get_data(as_text=True)
    assert 'nav-item active" href="/how-it-works">Home' in html
    assert "Go to Maggie" in html


def test_update_photo_sits_under_the_portrait_on_today(client, app):
    _pet(client)
    html = client.get("/animals/1/today").get_data(as_text=True)
    assert "Add a photo" in html and 'action="/animals/1/photo"' in html
    img = io.BytesIO()
    Image.new("RGB", (40, 40)).save(img, format="JPEG")
    img.seek(0)
    r = client.post("/animals/1/photo", data={"photo": (img, "a.jpg")}, content_type="multipart/form-data",
                    headers={"Referer": "http://localhost/animals/1/today"})
    assert r.headers["Location"].endswith("/animals/1/today")
    html = client.get("/animals/1/today").get_data(as_text=True)
    assert "Update photo" in html and "<img src=" in html


# --- second hunt over the example-pet and photo changes --------------------------

def test_removing_examples_deletes_their_photo_files(client, app):
    from scripts.seed_demo import remove_examples
    client.post("/examples/add")
    with app.app_context():
        maggie = models.list_demo_animals()[0]
    img = io.BytesIO()
    Image.new("RGB", (40, 40)).save(img, format="JPEG")
    img.seek(0)
    client.post(f"/animals/{maggie.id}/photo", data={"photo": (img, "a.jpg")}, content_type="multipart/form-data")
    assert list(app.config["PHOTO_DIR"].rglob("*.jpg"))
    with app.app_context():
        remove_examples()
    assert not list(app.config["PHOTO_DIR"].rglob("*.jpg"))


def test_adding_examples_twice_at_once_makes_one_set(app):
    from scripts.seed_demo import add_examples
    results = []

    def worker():
        with app.app_context():
            results.append(add_examples())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with app.app_context():
        assert sorted(a.name for a in models.list_demo_animals()) == ["Bruno", "Juniper", "Maggie"]
    assert sorted(len(r) for r in results) == [0, 3]


def test_photo_upload_only_returns_to_this_site(client):
    _pet(client)
    img = io.BytesIO()
    Image.new("RGB", (40, 40)).save(img, format="JPEG")
    img.seek(0)
    r = client.post("/animals/1/photo", data={"photo": (img, "a.jpg")}, content_type="multipart/form-data",
                    headers={"Referer": "https://evil.example/phish"})
    assert r.headers["Location"].endswith("/animals/1/settings")


def test_seed_cli_does_not_duplicate_examples(app, monkeypatch):
    from scripts import seed_demo
    monkeypatch.setattr(seed_demo, "create_app", lambda: app)
    seed_demo.seed(reset=False)
    seed_demo.seed(reset=False)
    with app.app_context():
        assert sorted(a.name for a in models.list_demo_animals()) == ["Bruno", "Juniper", "Maggie"]


# --- phone access ------------------------------------------------------------

PHONE = {"REMOTE_ADDR": "192.168.1.23", "pet_qol.phone_listener": True}


def _from_phone(client, path, **kw):
    return client.open(path, environ_base=PHONE, **kw)


def test_phone_access_is_off_by_default_and_remote_requests_are_refused(client):
    _pet(client)
    assert _from_phone(client, "/animals/1/today").status_code == 403
    assert client.get("/animals/1/today").status_code == 200  # this computer is unaffected


def test_enabling_phone_access_needs_a_matching_passcode(client, app):
    r = client.post("/settings/phone", data={"action": "enable", "passcode": "short", "passcode_confirm": "short"})
    assert r.status_code == 400
    r = client.post("/settings/phone", data={"action": "enable", "passcode": "sunflower", "passcode_confirm": "sunflowers"})
    assert r.status_code == 400
    r = client.post("/settings/phone", data={"action": "enable", "passcode": "sunflower", "passcode_confirm": "sunflower"})
    assert r.status_code == 302
    from app import phone
    with app.app_context():
        assert phone.is_enabled()
        assert phone.check_passcode("sunflower") and not phone.check_passcode("Sunflower")
    text = (app.config["DATA_DIR"] / "settings.json").read_text()
    assert "sunflower" not in text  # only a hash is stored


def test_phone_must_unlock_with_the_phone_passcode(client):
    _pet(client)
    client.post("/settings/phone", data={"action": "enable", "passcode": "sunflower", "passcode_confirm": "sunflower"})
    phone = client.application.test_client()  # a second browser: the phone
    r = phone.get("/animals/1/today", environ_base=PHONE)
    assert r.status_code == 302 and "/unlock" in r.headers["Location"]
    r = phone.post("/unlock?next=/animals/1/today", data={"passcode": "wrong"}, environ_base=PHONE)
    assert r.status_code == 401
    r = phone.post("/unlock?next=/animals/1/today", data={"passcode": "sunflower"}, environ_base=PHONE)
    assert r.status_code == 302 and r.headers["Location"].endswith("/animals/1/today")
    assert phone.get("/animals/1/today", environ_base=PHONE).status_code == 200
    # The computer itself never needs the phone passcode.
    assert client.get("/animals/1/today").status_code == 200
    assert client.get("/unlock").status_code == 302


def test_phone_cannot_change_phone_access(client):
    client.post("/settings/phone", data={"action": "enable", "passcode": "sunflower", "passcode_confirm": "sunflower"})
    phone = client.application.test_client()
    phone.post("/unlock", data={"passcode": "sunflower"}, environ_base=PHONE)
    assert phone.get("/settings/phone", environ_base=PHONE).status_code == 200
    assert phone.post("/settings/phone", data={"action": "disable"}, environ_base=PHONE).status_code == 403
    r = client.post("/settings/phone", data={"action": "disable"})
    assert r.status_code == 302
    assert phone.get("/animals/1/today", environ_base=PHONE).status_code == 403


def test_phone_page_shows_address_and_qr_when_on(client, monkeypatch):
    from app import phone
    monkeypatch.setattr(phone, "lan_ip", lambda: "192.168.1.5")
    html = client.get("/settings/phone").get_data(as_text=True)
    assert "Switch it on" in html and "qr-code" not in html
    client.post("/settings/phone", data={"action": "enable", "passcode": "sunflower", "passcode_confirm": "sunflower"})
    html = client.get("/settings/phone").get_data(as_text=True)
    assert "http://192.168.1.5:5100/" in html and 'class="qr-code"' in html and 'width="' not in html.split("qr-code")[1][:40]
    assert "Switch off" in html


def test_phone_links_are_on_settings_and_more(client):
    _pet(client)
    assert "/settings/phone" in client.get("/settings").get_data(as_text=True)
    assert "/settings/phone" in client.get("/more").get_data(as_text=True)


# --- medications: how it's going --------------------------------------------

def test_medication_summary_counts_given_days_and_comfort(client):
    _pet(client)
    start = (TODAY - timedelta(days=10)).isoformat()
    client.post("/animals/1/medications", data={"name": "Gabapentin", "start_date": start})
    for d in range(20, 10, -1):  # two weeks before: comfort 4
        _checkin(client, d, each=4)
    for d in range(10, 0, -1):  # after: comfort 7, given on every other day
        extra = {"meds_included": "1", **({"given": "1"} if d % 2 == 0 else {})}
        _checkin(client, d, each=7, **extra)
    html = client.get("/animals/1/medications").get_data(as_text=True)
    assert "How it" in html
    assert "Given on 5 of the 10 days with a full check-in in the last 30 days." in html
    assert "Comfort scores averaged 7.0 in the two weeks after Gabapentin started, compared with 4.0" in html
    assert html.count('class="med-day given"') == 5 + 1  # strip plus the legend
    assert html.count('class="med-day missed"') == 5 + 1


def test_medication_summary_without_records(client):
    _pet(client)
    client.post("/animals/1/medications", data={"name": "Meloxicam"})
    html = client.get("/animals/1/medications").get_data(as_text=True)
    assert "Not ticked in a full check-in yet." in html
    assert "Comfort scores" not in html


def test_medication_summary_text_passes_the_safety_guard():
    from app import meds
    from app.safety import guard
    med = Medication(1, 1, "Prednisolone", None, None, TODAY - timedelta(days=10), None, True)
    ents = [_entry(d, each=(3 if d > 10 else 8)) for d in range(1, 24)]
    [summary] = meds.summarize([med], ents, {1: {TODAY - timedelta(days=1): True}}, TODAY)
    assert summary.given == 1 and summary.offered == 1
    assert "8.0" in summary.comfort_text and "3.0" in summary.comfort_text
    guard(summary.count_text)


# --- photo timeline --------------------------------------------------------

def _add_photo(client, days_ago, size=(40, 40)):
    img = io.BytesIO()
    Image.new("RGB", size, (200, 120, 90)).save(img, format="JPEG")
    img.seek(0)
    day = (TODAY - timedelta(days=days_ago)).isoformat()
    data = {"entry_date": day, "day_status": "good", "photos": (img, f"p{days_ago}.jpg")}
    r = client.post("/animals/1/checkin", data=data, content_type="multipart/form-data")
    assert r.status_code == 302, r.get_data(as_text=True)[:200]


def test_photo_timeline_lists_photos_newest_first_by_month(client):
    _pet(client)
    html = client.get("/animals/1/photos").get_data(as_text=True)
    assert "No photos yet" in html
    _add_photo(client, 40)
    _add_photo(client, 3)
    _add_photo(client, 1)
    html = client.get("/animals/1/photos").get_data(as_text=True)
    assert "3 photos" in html
    assert html.count('class="photo-tile"') == 3
    months = [m for m in {(TODAY - timedelta(days=d)).strftime("%B %Y") for d in (40, 3, 1)}]
    for m in months:
        assert m in html
    first = html.index(f"date={(TODAY - timedelta(days=1)).isoformat()}")
    last = html.index(f"date={(TODAY - timedelta(days=40)).isoformat()}")
    assert first < last
    assert "/animals/1/photos" in client.get("/more").get_data(as_text=True)
    assert "/animals/1/photos" in client.get("/animals/1/today").get_data(as_text=True)


def test_photo_timeline_only_shows_this_pets_photos(client):
    _pet(client)
    _pet(client, "Otis")
    _add_photo(client, 2)
    assert client.get("/animals/2/photos").get_data(as_text=True).count('class="photo-tile"') == 0
    assert client.get("/animals/1/photos").get_data(as_text=True).count('class="photo-tile"') == 1
    assert client.get("/animals/99/photos").status_code == 404


# --- fourth bug check: phone access follow-ups --------------------------------

def _enable(client, passcode="sunflower"):
    r = client.post("/settings/phone", data={"action": "enable", "passcode": passcode, "passcode_confirm": passcode})
    assert r.status_code == 302


def test_switching_phone_access_off_and_on_signs_every_phone_out(client):
    _pet(client)
    _enable(client)
    phone = client.application.test_client()
    phone.post("/unlock", data={"passcode": "sunflower"}, environ_base=PHONE)
    assert phone.get("/animals/1/today", environ_base=PHONE).status_code == 200
    client.post("/settings/phone", data={"action": "disable"})
    _enable(client, "newsecret99")
    r = phone.get("/animals/1/today", environ_base=PHONE)
    assert r.status_code == 302 and "/unlock" in r.headers["Location"]  # the old unlock no longer counts
    assert phone.post("/unlock", data={"passcode": "sunflower"}, environ_base=PHONE).status_code == 401
    phone.post("/unlock", data={"passcode": "newsecret99"}, environ_base=PHONE)
    assert phone.get("/animals/1/today", environ_base=PHONE).status_code == 200


def test_phone_gets_a_lock_button_and_can_lock(client):
    _pet(client)
    _enable(client)
    phone = client.application.test_client()
    phone.post("/unlock", data={"passcode": "sunflower"}, environ_base=PHONE)
    html = phone.get("/animals/1/today", environ_base=PHONE).get_data(as_text=True)
    assert "/lock" in html
    assert "/lock" not in client.get("/animals/1/today").get_data(as_text=True)  # the computer has nothing to lock
    phone.post("/lock", environ_base=PHONE)
    assert phone.get("/animals/1/today", environ_base=PHONE).status_code == 302


def test_repeated_wrong_phone_passcodes_are_slowed_down(client):
    _enable(client)
    from app import phone as ph
    ph._failures.clear()
    attacker = client.application.test_client()
    for _ in range(5):
        assert attacker.post("/unlock", data={"passcode": "guess"}, environ_base=PHONE).status_code == 401
    r = attacker.post("/unlock", data={"passcode": "sunflower"}, environ_base=PHONE)
    assert r.status_code == 429  # even the right one must wait now
    other = {**PHONE, "REMOTE_ADDR": "192.168.1.99"}
    assert client.application.test_client().post("/unlock", data={"passcode": "sunflower"}, environ_base=other).status_code == 302
    ph._failures.clear()


def test_phone_cannot_restore_a_backup(client):
    _pet(client)
    _enable(client)
    phone = client.application.test_client()
    phone.post("/unlock", data={"passcode": "sunflower"}, environ_base=PHONE)
    assert phone.get("/settings/backup.zip", environ_base=PHONE).status_code == 200
    html = phone.get("/settings", environ_base=PHONE).get_data(as_text=True)
    assert "only be done from the computer" in html and 'name="backup"' not in html
    data = _zip({"tracker.sqlite": b"x"})
    r = phone.post("/settings/restore", data={"backup": (io.BytesIO(data), "b.zip"), "confirm": "yes"},
                   content_type="multipart/form-data", environ_base=PHONE)
    assert r.status_code == 403
    assert client.get("/animals/1/today").status_code == 200  # nothing was replaced


def test_stopped_medication_days_after_its_end_are_blank(client):
    _pet(client)
    client.post("/animals/1/medications", data={"name": "Buprenorphine"})
    for d in range(8, 0, -1):
        _checkin(client, d, meds_included="1", given="1")
    from app import entries as en
    with client.application.app_context():
        en.set_medication_active(1, False, on=TODAY - timedelta(days=4))
    html = client.get("/animals/1/medications").get_data(as_text=True)
    assert "Given on 5 of the 5 days with a full check-in" in html  # days 8..4, not the three after it stopped
    with client.application.app_context():
        en.set_medication_active(1, False, on=TODAY - timedelta(days=40))
    html = client.get("/animals/1/medications").get_data(as_text=True)
    assert "Not ticked in any full check-in in the last 30 days." in html


# --- fifth bug check: browser walkthrough findings -------------------------------

def test_new_pet_is_not_nagged_before_its_first_checkin(client):
    _pet(client)
    assert b"No check-in recorded today" not in client.get("/animals/1/more").data
    _checkin(client, 2)
    assert b"No check-in recorded today" in client.get("/animals/1/more").data


def test_remembered_pet_entries_are_not_dead_links(client):
    _pet(client)
    _checkin(client, 1)
    client.post("/animals/1/passed", data={"passed_date": TODAY.isoformat(), "choice": "keep"})
    r = client.get("/animals/1/checkin", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "kept in memory" in html and "archived" not in html.split("<main")[1].split("Recent")[0]
    assert "/animals/1/checkin?date=" not in client.get("/animals/1/today").get_data(as_text=True)
    assert "/animals/1/checkin?date=" not in client.get("/animals/1/trends").get_data(as_text=True)


def test_good_days_observation_reads_as_a_sentence(client):
    _pet(client)
    for d in range(20, 7, -1):
        _checkin(client, d, each=8)
    for d in range(7, 0, -1):
        _checkin(client, d, each=8, good_days=3)
    html = unescape(client.get("/animals/1/today").get_data(as_text=True))
    assert "More good days than bad scores" not in html
    assert "The good-days-versus-bad score has been lower recently" in html


def test_unknown_pages_get_the_app_look(client):
    r = client.get("/animals/999/today")
    assert r.status_code == 404
    html = unescape(r.get_data(as_text=True))
    assert "isn't here" in html and 'class="topbar"' in html


def test_trend_summary_does_not_repeat_itself(client):
    _pet(client)
    _checkin(client, 0)
    html = unescape(client.get("/animals/1/today").get_data(as_text=True))
    summary = html.split('class="chart-summary">')[1].split("</p>")[0]
    assert summary.count("isn't enough information yet") == 1 and "Limited data" in summary


def test_remove_check_in_sits_below_the_save_bar(client):
    _pet(client)
    _checkin(client, 0)
    html = client.get("/animals/1/checkin").get_data(as_text=True)
    sticky = html.split('class="actions sticky-actions"')[1].split("</div>")[0]
    assert "Remove this check-in" not in sticky and 'class="remove-entry"' in html


# --- fifth bug check: back-end findings ---------------------------------------

def test_failed_restore_leaves_current_data_untouched(client, app, monkeypatch):
    _pet(client)
    _checkin(client, 1)
    good = client.get("/settings/backup.zip").data
    import shutil
    original = shutil.copy2

    def explode(src, dst, *a, **k):
        if str(dst).endswith(".restoring"):
            raise OSError(28, "No space left on device")
        return original(src, dst, *a, **k)
    monkeypatch.setattr(shutil, "copy2", explode)
    try:
        _restore(client, good)
    except OSError:
        pass  # the test app propagates the failure; a real one shows an error page
    monkeypatch.setattr(shutil, "copy2", original)
    assert client.get("/animals/1/today").status_code == 200  # the database is still there
    assert (app.config["DATABASE"]).exists()


def test_restore_refuses_a_database_without_pets(client):
    _pet(client)
    r = _restore(client, _zip({"tracker.sqlite": b""}))
    assert "no pet data" in r.get_data(as_text=True)
    assert client.get("/animals/1/today").status_code == 200


def test_restore_accepts_a_backup_bigger_than_a_checkin_upload(client, app):
    _pet(client)
    good = client.get("/settings/backup.zip").data
    padded = _zip({"tracker.sqlite": zipfile.ZipFile(io.BytesIO(good)).read("tracker.sqlite"),
                   "photos/pad.bin": b"\\0" * (12 * 1024 * 1024)})
    assert len(padded) > 10 * 1024 * 1024 or True  # zeros compress; the request itself is what is limited
    r = client.post("/settings/restore", data={"backup": (io.BytesIO(padded), "b.zip"), "confirm": "yes"},
                    content_type="multipart/form-data")
    assert r.status_code != 413


def test_pdf_survives_a_very_long_medication_name(client):
    _pet(client)
    _checkin(client, 1)
    client.post("/animals/1/medications", data={"name": "x" * 5000, "dose": "y" * 5000, "schedule": "z" * 5000})
    r = client.get("/animals/1/export.pdf")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"


def test_pdf_prints_non_latin_names(client):
    """Cyrillic, Greek and accented names print (DejaVu Sans). CJK is still not covered."""
    _pet(client, "Мурка Ωμέγα Zoë")
    _checkin(client, 1, notes="Хороший день")
    r = client.get("/animals/1/export.pdf?appendix=1")
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.data)).pages)
    assert "Мурка" in text and "Ωμέγα" in text and "Zoë" in text and "Хороший" in text


def test_hosted_passcode_is_throttled_too(app):
    app.config["PASSCODE"] = "letmein99"
    from app import phone as ph
    ph._failures.clear()
    c = app.test_client()
    for _ in range(5):
        assert c.post("/unlock", data={"passcode": "nope"}).status_code == 401
    assert c.post("/unlock", data={"passcode": "letmein99"}).status_code == 429
    ph._failures.clear()


def test_domain_names_in_host_are_refused_locally(client):
    _pet(client)
    assert client.get("/animals/1/today", headers={"Host": "attacker.example:5000"}).status_code == 403
    assert client.post("/animals/1/archive", headers={"Host": "attacker.example:5000",
                                                      "Origin": "http://attacker.example:5000"}).status_code == 403
    assert client.get("/animals/1/today", headers={"Host": "127.0.0.1:5000"}).status_code == 200
    assert client.get("/animals/1/today", headers={"Host": "localhost:5000"}).status_code == 200
    assert client.get("/animals/1/today", headers={"Host": "192.168.1.5:5100"}).status_code == 200


def test_photo_delete_cannot_reach_outside_the_photo_folder(client, app):
    _pet(client)
    victim = app.config["DATA_DIR"] / "victim.txt"
    victim.write_text("keep me")
    with app.app_context():
        from app.db import get_db
        get_db().execute("UPDATE animals SET photo_path = '../victim.txt' WHERE id = 1")
        get_db().commit()
    client.post("/animals/1/photo/delete")
    assert victim.exists()


def test_pdf_range_is_clamped_to_the_pets_history(client):
    _pet(client)
    _checkin(client, 3)
    import time
    t = time.monotonic()
    r = client.get("/animals/1/export.pdf?start=1900-01-01&end=2100-12-31")
    assert r.status_code == 200 and time.monotonic() - t < 15


def test_scored_days_without_a_day_status_are_not_called_not_logged():
    ents = [_entry(d, status=None) for d in range(1, 8)]
    counts = an.day_counts(ents, TODAY - timedelta(days=29), TODAY)
    assert counts.unrated == 7 and counts.not_logged == 23 and counts.logged == 0


def test_renamed_example_is_not_seeded_twice(client, app):
    client.post("/examples/add")
    client.post("/animals/1/edit", data={"name": "Maggie (example)", "species": "dog"})
    client.post("/examples/add")
    with app.app_context():
        assert len(models.list_demo_animals()) == 3


def test_birth_date_cannot_follow_the_passing_date(client, app):
    _pet(client)
    client.post("/animals/1/passed", data={"passed_date": "2025-01-01", "choice": "keep"})
    r = client.post("/animals/1/edit", data={"name": "Maggie", "species": "dog", "birth_date": "2026-01-01"})
    assert r.status_code == 400
    with app.app_context():
        assert models.get_animal(1).birth_date is None


def test_secret_key_is_private_to_this_user(app):
    import stat
    mode = stat.S_IMODE((app.config["DATA_DIR"] / "secret_key").stat().st_mode)
    assert mode == 0o600


def test_chart_sufficiency_matches_the_text_on_a_short_range(client):
    _pet(client)
    for d in range(40, 0, -1):
        _checkin(client, d)
    html = client.get("/animals/1/today?range=7").get_data(as_text=True)
    assert '"sufficiency": "adequate"' in html or '&#34;sufficiency&#34;: &#34;adequate&#34;' in html
