"""Data access for daily entries, medications, and entry photos."""
from dataclasses import dataclass
from datetime import date

from .db import get_db
from .scoring import CATEGORY_KEYS

DAY_STATUSES = (("good", "Good day"), ("bad", "Bad day"), ("mixed", "Mixed / unsure"))
DAY_STATUS_LABELS = dict(DAY_STATUSES)


@dataclass
class Entry:
    id: int
    animal_id: int
    entry_date: date
    day_status: str | None
    hurt: int | None
    hunger: int | None
    hydration: int | None
    hygiene: int | None
    happiness: int | None
    mobility: int | None
    good_days: int | None
    weight: float | None
    weight_unit: str | None
    appetite: str | None
    notes: str | None

    @property
    def scores(self) -> dict[str, int | None]:
        return {key: getattr(self, key) for key in CATEGORY_KEYS}

    @property
    def has_scores(self) -> bool:
        """True when every HHHHHMM category was scored."""
        return all(v is not None for v in self.scores.values())

    @property
    def scored_values(self) -> list[int]:
        return [v for v in self.scores.values() if v is not None]

    @property
    def total(self) -> int | None:
        """Sum of the seven scores (0-70), or None if the full assessment wasn't done."""
        return sum(self.scored_values) if self.has_scores else None

    @property
    def mean(self) -> float | None:
        """Overall quality-of-life score, 0-10: mean of whichever categories were scored."""
        values = self.scored_values
        return round(sum(values) / len(values), 2) if values else None


def _row_to_entry(row) -> Entry:
    return Entry(
        id=row["id"],
        animal_id=row["animal_id"],
        entry_date=row["entry_date"],
        day_status=row["day_status"],
        hurt=row["hurt"],
        hunger=row["hunger"],
        hydration=row["hydration"],
        hygiene=row["hygiene"],
        happiness=row["happiness"],
        mobility=row["mobility"],
        good_days=row["good_days"],
        weight=row["weight"],
        weight_unit=row["weight_unit"],
        appetite=row["appetite"],
        notes=row["notes"],
    )


# --- entries -----------------------------------------------------------------

def get_entry(entry_id: int) -> Entry | None:
    row = get_db().execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def get_entry_for_date(animal_id: int, entry_date: date) -> Entry | None:
    row = get_db().execute(
        "SELECT * FROM entries WHERE animal_id = ? AND entry_date = ?",
        (animal_id, entry_date),
    ).fetchone()
    return _row_to_entry(row) if row else None


def list_entries(
    animal_id: int,
    start: date | None = None,
    end: date | None = None,
    newest_first: bool = True,
    limit: int | None = None,
) -> list[Entry]:
    sql = "SELECT * FROM entries WHERE animal_id = ?"
    params: list = [animal_id]
    if start is not None:
        sql += " AND entry_date >= ?"
        params.append(start)
    if end is not None:
        sql += " AND entry_date <= ?"
        params.append(end)
    sql += " ORDER BY entry_date " + ("DESC" if newest_first else "ASC")
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [_row_to_entry(r) for r in get_db().execute(sql, params).fetchall()]


KEEP = object()  # sentinel: leave the stored value as it is


def save_entry(
    animal_id: int,
    entry_date: date,
    day_status=KEEP,
    scores: dict[str, int | None] | None = None,
    weight=KEEP,
    weight_unit=KEEP,
    appetite=KEEP,
    notes=KEEP,
) -> int:
    """Insert the day's entry, or update it if one already exists. Returns its id.

    Fields left as ``KEEP`` are untouched on an existing entry, so a quick
    check-in never wipes scores recorded earlier the same day. ``scores`` only
    replaces the categories it contains; pass ``None`` for a category to clear it.
    """
    db = get_db()
    scores = scores or {}
    existing = get_entry_for_date(animal_id, entry_date)
    if existing:
        fields = {key: scores.get(key, getattr(existing, key)) for key in CATEGORY_KEYS}
        for name, value in (("day_status", day_status), ("weight", weight), ("weight_unit", weight_unit),
                            ("appetite", appetite), ("notes", notes)):
            fields[name] = getattr(existing, name) if value is KEEP else value
        assignments = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE entries SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [*fields.values(), existing.id],
        )
        db.commit()
        return existing.id
    plain = lambda v: None if v is KEEP else v  # noqa: E731
    cur = db.execute(
        """INSERT INTO entries (animal_id, entry_date, day_status, hurt, hunger, hydration,
               hygiene, happiness, mobility, good_days, weight, weight_unit, appetite, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [animal_id, entry_date, plain(day_status), *[scores.get(key) for key in CATEGORY_KEYS],
         plain(weight), plain(weight_unit), plain(appetite), plain(notes)],
    )
    db.commit()
    return cur.lastrowid


def delete_entry(entry_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()


# --- medications -------------------------------------------------------------

@dataclass
class Medication:
    id: int
    animal_id: int
    name: str
    dose: str | None
    schedule: str | None
    start_date: date | None
    end_date: date | None
    active: bool


def _row_to_medication(row) -> Medication:
    return Medication(
        id=row["id"], animal_id=row["animal_id"], name=row["name"], dose=row["dose"],
        schedule=row["schedule"], start_date=row["start_date"], end_date=row["end_date"],
        active=bool(row["active"]),
    )


def list_medications(animal_id: int, active_only: bool = False) -> list[Medication]:
    sql = "SELECT * FROM medications WHERE animal_id = ?"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY active DESC, name COLLATE NOCASE"
    return [_row_to_medication(r) for r in get_db().execute(sql, (animal_id,)).fetchall()]


def get_medication(medication_id: int) -> Medication | None:
    row = get_db().execute("SELECT * FROM medications WHERE id = ?", (medication_id,)).fetchone()
    return _row_to_medication(row) if row else None


def create_medication(
    animal_id: int, name: str, dose: str | None = None, schedule: str | None = None,
    start_date: date | None = None,
) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO medications (animal_id, name, dose, schedule, start_date) VALUES (?, ?, ?, ?, ?)",
        (animal_id, name, dose, schedule, start_date),
    )
    db.commit()
    return cur.lastrowid


def set_medication_active(medication_id: int, active: bool, on: date | None = None) -> None:
    db = get_db()
    if active:
        db.execute("UPDATE medications SET active = 1, end_date = NULL WHERE id = ?", (medication_id,))
    else:
        db.execute(
            "UPDATE medications SET active = 0, end_date = ? WHERE id = ?",
            (on or date.today(), medication_id),
        )
    db.commit()


def delete_medication(medication_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM medications WHERE id = ?", (medication_id,))
    db.commit()


def set_entry_medications(entry_id: int, given_ids: set[int], offered_ids: set[int]) -> None:
    """Record which of the offered medications were given on this entry's day."""
    db = get_db()
    for medication_id in offered_ids:
        db.execute(
            """INSERT INTO entry_medications (entry_id, medication_id, given)
               VALUES (?, ?, ?)
               ON CONFLICT (entry_id, medication_id) DO UPDATE SET given = excluded.given""",
            (entry_id, medication_id, int(medication_id in given_ids)),
        )
    db.commit()


def medications_given(entry_id: int) -> set[int]:
    rows = get_db().execute(
        "SELECT medication_id FROM entry_medications WHERE entry_id = ? AND given = 1",
        (entry_id,),
    ).fetchall()
    return {r["medication_id"] for r in rows}


def medications_given_names(entry_id: int) -> list[str]:
    rows = get_db().execute(
        """SELECT m.name FROM entry_medications em
           JOIN medications m ON m.id = em.medication_id
           WHERE em.entry_id = ? AND em.given = 1
           ORDER BY m.name COLLATE NOCASE""",
        (entry_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def medications_given_names_for_animal(animal_id: int) -> dict[int, list[str]]:
    """{entry_id: [medication names given]} for every entry of the animal, in one query."""
    rows = get_db().execute(
        """SELECT em.entry_id, m.name FROM entry_medications em
           JOIN medications m ON m.id = em.medication_id
           JOIN entries e ON e.id = em.entry_id
           WHERE e.animal_id = ? AND em.given = 1
           ORDER BY em.entry_id, m.name COLLATE NOCASE""",
        (animal_id,),
    ).fetchall()
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r["entry_id"], []).append(r["name"])
    return out


# --- photos ------------------------------------------------------------------

@dataclass
class EntryPhoto:
    id: int
    entry_id: int
    file_path: str
    caption: str | None


def add_entry_photo(entry_id: int, file_path: str, caption: str | None = None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO photos (entry_id, file_path, caption) VALUES (?, ?, ?)",
        (entry_id, file_path, caption),
    )
    db.commit()
    return cur.lastrowid


def list_entry_photos(entry_id: int) -> list[EntryPhoto]:
    rows = get_db().execute("SELECT * FROM photos WHERE entry_id = ? ORDER BY id", (entry_id,)).fetchall()
    return [EntryPhoto(r["id"], r["entry_id"], r["file_path"], r["caption"]) for r in rows]


def get_entry_photo(photo_id: int) -> EntryPhoto | None:
    row = get_db().execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    return EntryPhoto(row["id"], row["entry_id"], row["file_path"], row["caption"]) if row else None


def delete_entry_photo(photo_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    db.commit()
