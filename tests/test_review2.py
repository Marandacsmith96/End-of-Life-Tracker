"""Regression tests for the second bug hunt (routes, data layer, analysis, PDF)."""
import io
import sqlite3
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
    assert "Add the example pets" in html and "Maggie" in html and "Juniper" in html
    r = client.post("/examples/add", follow_redirects=True)
    assert b"Added Maggie, Bruno, Juniper as example pets" in r.data
    assert b"Example pet" in r.data  # badge on the dashboard the add lands on
    with app.app_context():
        demo = models.list_demo_animals()
        assert [a.name for a in demo] == ["Maggie", "Bruno", "Juniper"]
        assert all(a.demo for a in demo)
        assert len(entries.list_entries(demo[2].id)) > 40
    html = client.get("/how-it-works").get_data(as_text=True)
    assert "Remove the example pets" in html and "Open Juniper" in html
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
