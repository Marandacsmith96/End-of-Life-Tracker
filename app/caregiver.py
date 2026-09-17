"""Weekly caregiver check-in. Stored and shown separately from the animal's data."""
from dataclasses import dataclass
from datetime import date, timedelta

from .db import get_db

STATUSES = (
    ("okay", "I'm managing okay"),
    ("harder", "It's getting harder"),
    ("exhausted", "I'm exhausted"),
    ("overwhelmed", "I'm overwhelmed"),
)
STATUS_LABELS = dict(STATUSES)
INTERVAL_DAYS = 7

INTRO = (
    "Caring for an aging or ill animal can be physically and emotionally demanding. "
    "This check-in is for you and is kept separate from your pet's quality-of-life assessment."
)


@dataclass
class CaregiverCheckIn:
    id: int
    animal_id: int
    checkin_date: date
    status: str
    note: str | None

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


def _row(r) -> CaregiverCheckIn:
    return CaregiverCheckIn(r["id"], r["animal_id"], r["checkin_date"], r["status"], r["note"])


def list_checkins(animal_id: int, limit: int | None = None) -> list[CaregiverCheckIn]:
    sql = "SELECT * FROM caregiver_checkins WHERE animal_id = ? ORDER BY checkin_date DESC, id DESC"
    params: list = [animal_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [_row(r) for r in get_db().execute(sql, params).fetchall()]


def latest(animal_id: int) -> CaregiverCheckIn | None:
    rows = list_checkins(animal_id, limit=1)
    return rows[0] if rows else None


def is_due(animal_id: int, today: date | None = None) -> bool:
    """Once a week, and only if the owner has recorded anything at all recently."""
    today = today or date.today()
    last = latest(animal_id)
    return last is None or (today - last.checkin_date).days >= INTERVAL_DAYS


def save_checkin(animal_id: int, checkin_date: date, status: str, note: str | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO caregiver_checkins (animal_id, checkin_date, status, note) VALUES (?, ?, ?, ?)",
        (animal_id, checkin_date, status, note),
    )
    db.commit()
    return cur.lastrowid


def delete_checkin(checkin_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM caregiver_checkins WHERE id = ?", (checkin_id,))
    db.commit()
