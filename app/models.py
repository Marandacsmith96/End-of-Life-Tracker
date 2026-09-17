"""Data access for animals.

Each function takes and returns plain Python values so the routes stay thin
and the tests can exercise the logic without HTTP.
"""
from dataclasses import dataclass
from datetime import date

from .db import get_db

SPECIES = ("cat", "dog")


@dataclass
class Animal:
    id: int
    name: str
    species: str
    breed: str | None
    birth_date: date | None
    photo_path: str | None
    archived: bool

    @property
    def age_text(self) -> str | None:
        """Human-friendly age such as '3 years, 2 months', or None if unknown."""
        if self.birth_date is None:
            return None
        today = date.today()
        months = (today.year - self.birth_date.year) * 12 + (
            today.month - self.birth_date.month
        )
        if today.day < self.birth_date.day:
            months -= 1
        months = max(months, 0)
        years, months = divmod(months, 12)
        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months or not years:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        return ", ".join(parts)


def _row_to_animal(row) -> Animal:
    return Animal(
        id=row["id"],
        name=row["name"],
        species=row["species"],
        breed=row["breed"],
        birth_date=row["birth_date"],
        photo_path=row["photo_path"],
        archived=bool(row["archived"]),
    )


def list_animals(include_archived: bool = False) -> list[Animal]:
    sql = "SELECT * FROM animals"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY archived, name COLLATE NOCASE"
    return [_row_to_animal(r) for r in get_db().execute(sql).fetchall()]


def get_animal(animal_id: int) -> Animal | None:
    row = get_db().execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
    return _row_to_animal(row) if row else None


def create_animal(name: str, species: str, breed: str | None, birth_date: date | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO animals (name, species, breed, birth_date) VALUES (?, ?, ?, ?)",
        (name, species, breed, birth_date),
    )
    db.commit()
    return cur.lastrowid


def update_animal(
    animal_id: int, name: str, species: str, breed: str | None, birth_date: date | None
) -> None:
    db = get_db()
    db.execute(
        "UPDATE animals SET name = ?, species = ?, breed = ?, birth_date = ? WHERE id = ?",
        (name, species, breed, birth_date, animal_id),
    )
    db.commit()


def set_archived(animal_id: int, archived: bool) -> None:
    db = get_db()
    db.execute("UPDATE animals SET archived = ? WHERE id = ?", (int(archived), animal_id))
    db.commit()


def set_photo_path(animal_id: int, photo_path: str | None) -> None:
    db = get_db()
    db.execute("UPDATE animals SET photo_path = ? WHERE id = ?", (photo_path, animal_id))
    db.commit()
