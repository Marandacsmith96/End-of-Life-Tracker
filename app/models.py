"""Data access for animals."""
from dataclasses import dataclass
from datetime import date

from .db import get_db

SPECIES = ("cat", "dog")
SEXES = (("female", "Female"), ("male", "Male"), ("unknown", "Prefer not to say"))
STATUSES = ("active", "archived", "passed")
REMINDERS = (
    ("off", "Off"),
    ("daily", "Daily"),
    ("every_other_day", "Every other day"),
    ("weekly", "Weekly"),
)
REMINDER_DAYS = {"daily": 1, "every_other_day": 2, "weekly": 7}


@dataclass
class Animal:
    id: int
    name: str
    species: str
    breed: str | None
    sex: str | None
    birth_date: date | None
    photo_path: str | None
    diagnoses: str | None
    status: str
    passed_date: date | None
    reminder: str

    @property
    def archived(self) -> bool:
        """True when the animal is no longer being tracked (archived or passed)."""
        return self.status != "active"

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def age_text(self) -> str | None:
        """Human-friendly age such as '3 years, 2 months', or None if unknown."""
        if self.birth_date is None:
            return None
        until = self.passed_date or date.today()
        months = (until.year - self.birth_date.year) * 12 + (until.month - self.birth_date.month)
        if until.day < self.birth_date.day:
            months -= 1
        months = max(months, 0)
        years, months = divmod(months, 12)
        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months or not years:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        return ", ".join(parts)

    @property
    def initials(self) -> str:
        return self.name[:1].upper() if self.name else "?"


def _row_to_animal(row) -> Animal:
    return Animal(
        id=row["id"],
        name=row["name"],
        species=row["species"],
        breed=row["breed"],
        sex=row["sex"],
        birth_date=row["birth_date"],
        photo_path=row["photo_path"],
        diagnoses=row["diagnoses"],
        status=row["status"],
        passed_date=row["passed_date"],
        reminder=row["reminder"],
    )


def list_animals(include_archived: bool = False) -> list[Animal]:
    sql = "SELECT * FROM animals"
    if not include_archived:
        sql += " WHERE status = 'active'"
    sql += " ORDER BY (status != 'active'), name COLLATE NOCASE"
    return [_row_to_animal(r) for r in get_db().execute(sql).fetchall()]


def get_animal(animal_id: int) -> Animal | None:
    row = get_db().execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
    return _row_to_animal(row) if row else None


def create_animal(
    name: str, species: str, breed: str | None = None, birth_date: date | None = None,
    sex: str | None = None, diagnoses: str | None = None,
) -> int:
    db = get_db()
    cur = db.execute(
        """INSERT INTO animals (name, species, breed, birth_date, sex, diagnoses)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, species, breed, birth_date, sex, diagnoses),
    )
    db.commit()
    return cur.lastrowid


def update_animal(
    animal_id: int, name: str, species: str, breed: str | None, birth_date: date | None,
    sex: str | None = None, diagnoses: str | None = None,
) -> None:
    db = get_db()
    db.execute(
        """UPDATE animals SET name = ?, species = ?, breed = ?, birth_date = ?, sex = ?,
           diagnoses = ? WHERE id = ?""",
        (name, species, breed, birth_date, sex, diagnoses, animal_id),
    )
    db.commit()


def set_status(animal_id: int, status: str, passed_date: date | None = None) -> None:
    """Archive, mark as passed, or restore. Passing also switches reminders off."""
    db = get_db()
    if status == "passed":
        db.execute(
            "UPDATE animals SET status = 'passed', passed_date = ?, reminder = 'off' WHERE id = ?",
            (passed_date or date.today(), animal_id),
        )
    elif status == "active":
        db.execute(
            "UPDATE animals SET status = 'active', passed_date = NULL WHERE id = ?", (animal_id,)
        )
    else:
        db.execute("UPDATE animals SET status = ? WHERE id = ?", (status, animal_id))
    db.commit()


def set_archived(animal_id: int, archived: bool) -> None:
    set_status(animal_id, "archived" if archived else "active")


def set_reminder(animal_id: int, reminder: str) -> None:
    db = get_db()
    db.execute("UPDATE animals SET reminder = ? WHERE id = ?", (reminder, animal_id))
    db.commit()


def set_photo_path(animal_id: int, photo_path: str | None) -> None:
    db = get_db()
    db.execute("UPDATE animals SET photo_path = ? WHERE id = ?", (photo_path, animal_id))
    db.commit()


def delete_animal(animal_id: int) -> None:
    """Permanently remove an animal and everything recorded about them."""
    db = get_db()
    db.execute("DELETE FROM animals WHERE id = ?", (animal_id,))
    db.commit()
