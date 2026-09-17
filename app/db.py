"""SQLite connection handling, schema setup, and migrations.

The database file and photo folder are created automatically the first time
the app starts. Existing databases are upgraded in place: each migration bumps
``PRAGMA user_version`` so it runs exactly once.
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path

import click
from flask import Flask, current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 2

# Store dates as ISO text and turn DATE / TIMESTAMP columns back into objects.
sqlite3.register_adapter(date, date.isoformat)
sqlite3.register_adapter(datetime, datetime.isoformat)
sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
sqlite3.register_converter(
    "TIMESTAMP", lambda b: datetime.fromisoformat(b.decode().replace(" ", "T"))
)


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    """Return the request-scoped database connection, opening it if needed."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _columns(conn, table: str) -> dict:
    return {row["name"]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Version 1 had NOT NULL scores, no day status, and an 'archived' flag."""
    cols = _columns(conn, "animals")
    if "status" not in cols:
        conn.executescript(
            """
            ALTER TABLE animals ADD COLUMN sex TEXT;
            ALTER TABLE animals ADD COLUMN diagnoses TEXT;
            ALTER TABLE animals ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
            ALTER TABLE animals ADD COLUMN passed_date DATE;
            ALTER TABLE animals ADD COLUMN reminder TEXT NOT NULL DEFAULT 'daily';
            """
        )
        if "archived" in cols:
            conn.execute("UPDATE animals SET status = 'archived' WHERE archived = 1")
    entry_cols = _columns(conn, "entries")
    if "day_status" not in entry_cols or entry_cols["hurt"]["notnull"]:
        # Rebuild entries with nullable scores and the day_status column.
        conn.executescript(
            """
            CREATE TABLE entries_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
                entry_date  DATE    NOT NULL,
                day_status  TEXT    CHECK (day_status IN ('good', 'bad', 'mixed')),
                hurt        INTEGER CHECK (hurt      BETWEEN 0 AND 10),
                hunger      INTEGER CHECK (hunger    BETWEEN 0 AND 10),
                hydration   INTEGER CHECK (hydration BETWEEN 0 AND 10),
                hygiene     INTEGER CHECK (hygiene   BETWEEN 0 AND 10),
                happiness   INTEGER CHECK (happiness BETWEEN 0 AND 10),
                mobility    INTEGER CHECK (mobility  BETWEEN 0 AND 10),
                good_days   INTEGER CHECK (good_days BETWEEN 0 AND 10),
                weight      REAL,
                weight_unit TEXT    CHECK (weight_unit IN ('kg', 'lb')),
                appetite    TEXT    CHECK (appetite IN ('none', 'low', 'normal', 'high')),
                notes       TEXT,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (animal_id, entry_date)
            );
            INSERT INTO entries_new (id, animal_id, entry_date, hurt, hunger, hydration,
                hygiene, happiness, mobility, good_days, weight, weight_unit, appetite,
                notes, created_at, updated_at)
            SELECT id, animal_id, entry_date, hurt, hunger, hydration, hygiene, happiness,
                mobility, good_days, weight, weight_unit, appetite, notes, created_at,
                updated_at FROM entries;
            DROP TABLE entries;
            ALTER TABLE entries_new RENAME TO entries;
            CREATE INDEX IF NOT EXISTS idx_entries_animal_date ON entries(animal_id, entry_date);
            """
        )
    med_cols = _columns(conn, "medications")
    if "start_date" not in med_cols:
        conn.executescript(
            """
            ALTER TABLE medications ADD COLUMN start_date DATE;
            ALTER TABLE medications ADD COLUMN end_date DATE;
            """
        )


MIGRATIONS = {1: _migrate_v1_to_v2}


def init_db() -> None:
    """Create the data folders and tables, then apply any pending migrations."""
    Path(current_app.config["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(current_app.config["PHOTO_DIR"]).mkdir(parents=True, exist_ok=True)
    conn = get_db()
    fresh = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'animals'"
    ).fetchone()[0] == 0
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if not fresh and version < SCHEMA_VERSION:
        # Dropping/rebuilding tables must not cascade-delete children.
        conn.execute("PRAGMA foreign_keys = OFF")
        for from_version in range(max(version, 1), SCHEMA_VERSION):
            MIGRATIONS[from_version](conn)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


@click.command("init-db")
def init_db_command() -> None:
    """Create or upgrade the database tables (safe to run more than once)."""
    init_db()
    click.echo("Database ready.")


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        init_db()
