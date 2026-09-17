import sqlite3

import pytest

from app.db import get_db

EXPECTED_TABLES = {"animals", "entries", "medications", "entry_medications", "photos"}


def test_data_folders_created_on_startup(app):
    assert app.config["DATABASE"].exists()
    assert app.config["PHOTO_DIR"].is_dir()


def test_schema_has_all_tables(app):
    with app.app_context():
        rows = get_db().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= names


def test_schema_is_safe_to_run_twice(app):
    from app.db import init_db

    with app.app_context():
        init_db()  # already ran at startup; must not raise


def test_species_is_restricted_to_cat_or_dog(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Mochi', 'cat')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO animals (name, species) VALUES ('Nemo', 'fish')")


def test_scores_must_be_between_0_and_10(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Rex', 'dog')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO entries
                   (animal_id, entry_date, hurt, hunger, hydration, hygiene,
                    happiness, mobility, good_days)
                   VALUES (1, '2026-09-17', 11, 5, 5, 5, 5, 5, 5)"""
            )


def test_one_entry_per_animal_per_day(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Rex', 'dog')")
        insert = """INSERT INTO entries
                    (animal_id, entry_date, hurt, hunger, hydration, hygiene,
                     happiness, mobility, good_days)
                    VALUES (1, '2026-09-17', 5, 5, 5, 5, 5, 5, 5)"""
        db.execute(insert)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert)


def test_deleting_animal_removes_its_entries(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO animals (name, species) VALUES ('Rex', 'dog')")
        db.execute(
            """INSERT INTO entries
               (animal_id, entry_date, hurt, hunger, hydration, hygiene,
                happiness, mobility, good_days)
               VALUES (1, '2026-09-17', 5, 5, 5, 5, 5, 5, 5)"""
        )
        db.execute("DELETE FROM animals WHERE id = 1")
        count = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert count == 0
