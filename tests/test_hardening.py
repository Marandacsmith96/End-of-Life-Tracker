"""Regression tests for the issues found in the code review."""
import io
import sqlite3
import zipfile
from datetime import date

from PIL import Image

from app import create_app, entries, models

KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")


def _locked(tmp_path, passcode):
    d = tmp_path / "data"
    return create_app({"TESTING": True, "DATA_DIR": d, "DATABASE": d / "t.sqlite", "PHOTO_DIR": d / "p",
                       "PASSCODE": passcode}).test_client()


def test_restoring_an_old_backup_upgrades_it(client, app):
    """A version-1 database inside a backup must be migrated before pages use it."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE animals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            species TEXT NOT NULL, breed TEXT, birth_date DATE, photo_path TEXT,
            archived INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, animal_id INTEGER NOT NULL,
            entry_date DATE NOT NULL, hurt INTEGER NOT NULL, hunger INTEGER NOT NULL, hydration INTEGER NOT NULL,
            hygiene INTEGER NOT NULL, happiness INTEGER NOT NULL, mobility INTEGER NOT NULL, good_days INTEGER NOT NULL,
            weight REAL, weight_unit TEXT, appetite TEXT, notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE medications (id INTEGER PRIMARY KEY AUTOINCREMENT, animal_id INTEGER NOT NULL, name TEXT NOT NULL,
            dose TEXT, schedule TEXT, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE entry_medications (entry_id INTEGER NOT NULL, medication_id INTEGER NOT NULL, given INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (entry_id, medication_id));
        CREATE TABLE photos (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL, file_path TEXT NOT NULL, caption TEXT);
        INSERT INTO animals (name, species, archived) VALUES ('Old Dog', 'dog', 0);
        INSERT INTO entries (animal_id, entry_date, hurt, hunger, hydration, hygiene, happiness, mobility, good_days)
            VALUES (1, '2026-01-01', 5, 5, 5, 5, 5, 5, 5);
    """)
    dump = "\n".join(conn.iterdump())
    file_db = sqlite3.connect(str(app.config["DATA_DIR"] / "old.sqlite"))
    file_db.executescript(dump); file_db.commit(); file_db.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(app.config["DATA_DIR"] / "old.sqlite", "tracker.sqlite")
    r = client.post("/settings/restore", data={"backup": (io.BytesIO(buf.getvalue()), "old.zip"), "confirm": "yes"},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Backup restored. 1 pet loaded." in r.data
    assert client.get("/animals/1/today").status_code == 200  # would be a 500 without the upgrade
    with app.app_context():
        assert models.get_animal(1).status == "active"


def test_non_ascii_passcode_works(tmp_path):
    c = _locked(tmp_path, "sésame 🐾")
    assert c.post("/unlock", data={"passcode": "sesame"}).status_code == 401
    assert c.post("/unlock", data={"passcode": "sésame 🐾"}).status_code == 302
    assert c.get("/").status_code == 200


def test_unlock_only_redirects_within_the_site(tmp_path):
    c = _locked(tmp_path, "pw")
    r = c.post("/unlock?next=https://evil.example/phish", data={"passcode": "pw"})
    assert r.headers["Location"].startswith("/") and "evil" not in r.headers["Location"]
    c2 = _locked(tmp_path / "b", "pw")
    r = c2.post("/unlock?next=//evil.example", data={"passcode": "pw"})
    assert "evil" not in r.headers["Location"]
    c3 = _locked(tmp_path / "c", "pw")
    r = c3.post("/unlock?next=/pets", data={"passcode": "pw"})
    assert r.headers["Location"].endswith("/pets")


def test_event_next_only_redirects_within_the_site(client):
    client.post("/animals/new", data={"name": "M", "species": "cat"})
    r = client.post("/animals/1/events/new", data={"event_date": date.today().isoformat(), "type": "other",
                                                   "next": "https://evil.example"})
    assert "evil" not in r.headers["Location"]


def test_cross_site_posts_are_refused(client):
    client.post("/animals/new", data={"name": "M", "species": "cat"})
    r = client.post("/animals/1/archive", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = client.post("/animals/1/archive", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/animals/1/archive", headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://localhost"})
    assert r.status_code == 302  # the app's own forms still work
    assert client.get("/animals/1/today", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200  # reads are fine


def test_secret_key_file_is_created_once(tmp_path):
    from app import _load_or_create_secret
    d = tmp_path / "data"
    first = _load_or_create_secret(d)
    (d / "secret_key").write_text("existing-key")
    assert _load_or_create_secret(d) == "existing-key"
    assert first != "existing-key"


def test_pdf_charts_do_not_use_pyplot():
    import app.pdf_charts as pc
    assert not hasattr(pc, "plt")


def test_removing_a_profile_removes_entry_photos(client, app):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    buf = io.BytesIO(); Image.new("RGB", (300, 300), (1, 2, 3)).save(buf, format="JPEG"); buf.seek(0)
    client.post("/animals/1/checkin", data={"entry_date": date.today().isoformat(), "day_status": "good",
                                            "photos": [(buf, "a.jpg")]}, content_type="multipart/form-data")
    with app.app_context():
        entry = entries.list_entries(1)[0]
        path = app.config["PHOTO_DIR"] / entries.list_entry_photos(entry.id)[0].file_path
    assert path.exists()
    client.post("/animals/1/remove", data={"confirm_name": "Mochi"})
    assert not path.exists() and not path.parent.exists()


def test_nan_weight_is_rejected(client, app):
    client.post("/animals/new", data={"name": "M", "species": "cat"})
    for bad in ("nan", "inf", "-inf"):
        r = client.post("/animals/1/checkin", data={"entry_date": date.today().isoformat(), "day_status": "good",
                                                    "weight": bad, "weight_unit": "kg"})
        assert r.status_code == 400, bad
    with app.app_context():
        assert entries.list_entries(1) == []


def test_medication_names_in_one_query(client, app):
    client.post("/animals/new", data={"name": "M", "species": "cat"})
    client.post("/animals/1/medications", data={"name": "Gabapentin"})
    client.post("/animals/1/checkin", data={"entry_date": date.today().isoformat(), "day_status": "good",
                                            "meds_included": "1", "given": ["1"]})
    with app.app_context():
        names = entries.medications_given_names_for_animal(1)
        entry = entries.list_entries(1)[0]
    assert names == {entry.id: ["Gabapentin"]}
    assert b"Gabapentin" in client.get("/animals/1/trends").data


def test_confirm_dialogs_survive_apostrophes(client):
    client.post("/animals/new", data={"name": "O'Malley", "species": "cat"})
    client.post("/animals/1/medications", data={"name": "D'oh"})
    for path in ("/animals/1/settings", "/animals/1/medications"):
        page = client.get(path).data.decode()
        assert "onsubmit=" not in page and "onclick=" not in page
        assert 'data-confirm="' in page
