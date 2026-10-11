"""Small key/value preferences kept in settings.json inside the data folder.

Used for things that are not pet data: whether phone access is switched on,
its passcode hash, and the port it listens on.
"""
import json
import os
import tempfile
from pathlib import Path

from flask import current_app

FILE_NAME = "settings.json"


def _path() -> Path:
    return Path(current_app.config["DATA_DIR"]) / FILE_NAME


def load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get(key: str, default=None):
    return load().get(key, default)


def update(**values) -> dict:
    """Merge ``values`` into the file and return the new contents (atomic write)."""
    data = load()
    data.update(values)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return data
