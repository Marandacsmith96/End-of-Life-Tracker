import sqlite3

import pytest

from app.db import SCHEMA_VERSION, get_db, init_db

EXPECTED_TABLES = {"animals", "entries", "medications", "entry_medications", "photos", "personal_markers",
                   "marker_responses", "baselines", "pet_events", "caregiver_checkins"}


def test_data_folders_created_on_startup(app):
    assert app.config["DATABASE"].exists()
    assert app.config["PHOTO_DIR"].is_dir()


def test_schema_has_all_tables_and_version(app):
    with app.app_context():
        rows = get_db().execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        assert {row["name"] for row in rows} >= EXPECTED_TABLES
        assert get_db().execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_schema_is_safe_to_run_twice(app):
    with app.app_context():
        init_db()


def test_species_is_restricted_to_cat_or_dog(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Mochi', 'cat')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO animals (name, species) VALUES ('Nemo', 'fish')")


def test_scores_optional_but_bounded(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Rex', 'dog')")
        db.execute("INSERT INTO entries (animal_id, entry_date, day_status) VALUES (1, '2026-09-17', 'good')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO entries (animal_id, entry_date, hurt) VALUES (1, '2026-09-18', 11)")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO entries (animal_id, entry_date, day_status) VALUES (1, '2026-09-19', 'great')")


def test_one_entry_per_animal_per_day(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Rex', 'dog')")
        db.execute("INSERT INTO entries (animal_id, entry_date) VALUES (1, '2026-09-17')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO entries (animal_id, entry_date) VALUES (1, '2026-09-17')")


def test_deleting_animal_cascades(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Rex', 'dog')")
        db.execute("INSERT INTO entries (animal_id, entry_date) VALUES (1, '2026-09-17')")
        db.execute("INSERT INTO personal_markers (animal_id, label) VALUES (1, 'Greets me')")
        db.execute("INSERT INTO marker_responses (entry_id, marker_id, completed) VALUES (1, 1, 1)")
        db.execute("INSERT INTO pet_events (animal_id, event_date, type, title) VALUES (1, '2026-09-01', 'vet_visit', 'x')")
        db.execute("DELETE FROM animals WHERE id = 1")
        for table in ("entries", "personal_markers", "marker_responses", "pet_events"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_migration_from_version_1(tmp_path):
    """A database created by the first release upgrades in place without losing rows."""
    from app import create_app

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE animals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            species TEXT NOT NULL CHECK (species IN ('cat','dog')), breed TEXT, birth_date DATE,
            photo_path TEXT, archived INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT,
            animal_id INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE, entry_date DATE NOT NULL,
            hurt INTEGER NOT NULL, hunger INTEGER NOT NULL, hydration INTEGER NOT NULL, hygiene INTEGER NOT NULL,
            happiness INTEGER NOT NULL, mobility INTEGER NOT NULL, good_days INTEGER NOT NULL,
            weight REAL, weight_unit TEXT, appetite TEXT, notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (animal_id, entry_date));
        CREATE TABLE medications (id INTEGER PRIMARY KEY AUTOINCREMENT,
            animal_id INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE, name TEXT NOT NULL, dose TEXT,
            schedule TEXT, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE entry_medications (entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
            given INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (entry_id, medication_id));
        CREATE TABLE photos (id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE, file_path TEXT NOT NULL, caption TEXT);
        INSERT INTO animals (name, species, archived) VALUES ('Old', 'dog', 1), ('Young', 'cat', 0);
        INSERT INTO entries (animal_id, entry_date, hurt, hunger, hydration, hygiene, happiness, mobility, good_days, notes)
            VALUES (1, '2026-01-01', 5, 5, 5, 5, 5, 5, 5, 'kept');
        INSERT INTO medications (animal_id, name) VALUES (1, 'Gabapentin');
        INSERT INTO entry_medications (entry_id, medication_id, given) VALUES (1, 1, 1);
        """
    )
    conn.commit()
    conn.close()

    app = create_app({"TESTING": True, "DATA_DIR": data_dir, "DATABASE": path, "PHOTO_DIR": data_dir / "photos"})
    with app.app_context():
        db = get_db()
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        rows = db.execute("SELECT name, status FROM animals ORDER BY id").fetchall()
        assert [(r["name"], r["status"]) for r in rows] == [("Old", "archived"), ("Young", "active")]
        e = db.execute("SELECT * FROM entries").fetchone()
        assert e["notes"] == "kept" and e["day_status"] is None
        assert db.execute("SELECT COUNT(*) FROM entry_medications").fetchone()[0] == 1
        db.execute("INSERT INTO entries (animal_id, entry_date, day_status) VALUES (2, '2026-02-02', 'good')")  # nullable scores now
