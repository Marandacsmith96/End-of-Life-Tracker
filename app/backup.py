"""Back up and restore the data folder as a zip file."""
import io
import os
import shutil
import sqlite3
import tempfile
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from flask import current_app

from . import db

DB_NAME = "tracker.sqlite"
MAX_RESTORE_BYTES = 500 * 1024 * 1024


class InvalidBackup(ValueError):
    pass


def make_backup() -> tuple[bytes, str]:
    """Return (zip_bytes, suggested_filename) for the whole data folder."""
    data_dir = Path(current_app.config["DATA_DIR"])
    db_path = Path(current_app.config["DATABASE"])
    photo_dir = Path(current_app.config["PHOTO_DIR"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Use sqlite's backup API so we copy a consistent snapshot even if the
        # file is mid-write.
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / DB_NAME
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(snapshot)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            zf.write(snapshot, DB_NAME)
        if photo_dir.is_dir():
            for path in sorted(photo_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, Path("photos") / path.relative_to(photo_dir))
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    return buf.getvalue(), f"pet-qol-backup-{stamp}.zip"


def _validate_staged_db(path: Path) -> int:
    """Upgrade the staged database in place and return its animal count."""
    try:
        conn = db.connect(path)
    except sqlite3.DatabaseError as exc:
        raise InvalidBackup("The database inside that backup is not readable.") from exc
    try:
        try:
            has_pets = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'animals'").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise InvalidBackup("That file is not a tracker database, or it is damaged.") from exc
        if not has_pets:
            raise InvalidBackup("That backup has no pet data in it (the database inside is empty).")
        try:
            db.upgrade(conn)
        except sqlite3.DatabaseError as exc:
            raise InvalidBackup("That file is not a tracker database, or it is damaged.") from exc
        problems = db.check_schema(conn)
        if problems:
            raise InvalidBackup("That file is not a tracker database (" + "; ".join(problems) + ").")
        count = conn.execute("SELECT COUNT(*) FROM animals").fetchone()[0]
        # Touch every table the app reads so a damaged one fails here, not later.
        for table in db.expected_columns():
            conn.execute(f"SELECT * FROM {table} LIMIT 1").fetchall()
    except db.UnsupportedDatabase as exc:
        raise InvalidBackup(str(exc)) from exc
    except sqlite3.DatabaseError as exc:
        raise InvalidBackup("The database inside that backup is not readable.") from exc
    finally:
        conn.close()
    return count


def restore_backup(file_storage) -> int:
    """Replace the data folder with the contents of an uploaded backup zip.

    Returns the number of animals in the restored database. Raises
    InvalidBackup if the file is not one of our backups.
    """
    if not file_storage or not file_storage.filename:
        raise InvalidBackup("No file was chosen.")
    raw = file_storage.read(MAX_RESTORE_BYTES + 1)
    if len(raw) > MAX_RESTORE_BYTES:
        raise InvalidBackup("That backup is too large to restore.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise InvalidBackup("That file is not a zip backup.") from exc
    names = zf.namelist()
    if DB_NAME not in names:
        raise InvalidBackup("That zip does not contain a tracker database.")
    for name in names:
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise InvalidBackup("That zip contains unsafe paths.")

    data_dir = Path(current_app.config["DATA_DIR"])
    photo_dir = Path(current_app.config["PHOTO_DIR"])
    db_path = Path(current_app.config["DATABASE"])

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        try:
            zf.extractall(staged)
        except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, OSError) as exc:
            raise InvalidBackup("That backup is damaged and could not be unpacked.") from exc
        # Check and upgrade the staged copy before touching the real data, so a
        # bad file can never leave the app with no database.
        count = _validate_staged_db(staged / DB_NAME)

        # Bring the new files next to the old ones first, then swap with
        # renames: if anything fails before the swap, the current data is
        # untouched; a rename cannot half-succeed the way a copy can.
        data_dir.mkdir(parents=True, exist_ok=True)
        incoming_db = db_path.with_name(db_path.name + ".restoring")
        incoming_photos = photo_dir.with_name(photo_dir.name + ".restoring")
        old_photos = photo_dir.with_name(photo_dir.name + ".replaced")
        for stale in (incoming_db, incoming_photos, old_photos):
            _remove(stale)
        shutil.copy2(staged / DB_NAME, incoming_db)
        staged_photos = staged / "photos"
        if staged_photos.is_dir():
            shutil.copytree(staged_photos, incoming_photos)
        else:
            incoming_photos.mkdir(parents=True)

        for suffix in ("-wal", "-shm", "-journal"):
            _remove(db_path.with_name(db_path.name + suffix))
        os.replace(incoming_db, db_path)
        if photo_dir.exists():
            os.replace(photo_dir, old_photos)
        os.replace(incoming_photos, photo_dir)
        _remove(old_photos)
    return count


def _remove(path: Path) -> None:
    """Delete a file or folder if it exists."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()
