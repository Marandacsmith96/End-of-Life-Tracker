"""Back up and restore the data folder as a zip file."""
import io
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import current_app

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
        zf.extractall(staged)
        # Sanity-check the database before touching anything.
        try:
            conn = sqlite3.connect(staged / DB_NAME)
            count = conn.execute("SELECT COUNT(*) FROM animals").fetchone()[0]
            conn.close()
        except sqlite3.DatabaseError as exc:
            raise InvalidBackup("The database inside that backup is not readable.") from exc

        if photo_dir.exists():
            shutil.rmtree(photo_dir)
        staged_photos = staged / "photos"
        if staged_photos.is_dir():
            shutil.copytree(staged_photos, photo_dir)
        else:
            photo_dir.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm", "-journal"):
            leftover = db_path.with_name(db_path.name + suffix)
            if leftover.exists():
                leftover.unlink()
        shutil.copy2(staged / DB_NAME, db_path)
    data_dir.mkdir(parents=True, exist_ok=True)
    return count
