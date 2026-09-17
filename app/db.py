"""SQLite connection handling and schema setup.

The database file and photo folder are created automatically the first time
the app starts, so there is no separate "install" step.
"""
import sqlite3
from pathlib import Path

import click
from flask import Flask, current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db() -> sqlite3.Connection:
    """Return the request-scoped database connection, opening it if needed."""
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    """Create the data folders and all tables if they do not already exist."""
    Path(current_app.config["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(current_app.config["PHOTO_DIR"]).mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


@click.command("init-db")
def init_db_command() -> None:
    """Create the database tables (safe to run more than once)."""
    init_db()
    click.echo("Database ready.")


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        init_db()
