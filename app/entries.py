"""Data access for daily entries, medications, and entry photos."""
from dataclasses import dataclass
from datetime import date

from .db import get_db
from .scoring import CATEGORY_KEYS, total_score


@dataclass
class Entry:
    id: int
    animal_id: int
    entry_date: date
    hurt: int
    hunger: int
    hydration: int
    hygiene: int
    happiness: int
    mobility: int
    good_days: int
    weight: float | None
    weight_unit: str | None
    appetite: str | None
    notes: str | None

    @property
    def scores(self) -> dict[str, int]:
        return {key: getattr(self, key) for key in CATEGORY_KEYS}

    @property
    def total(self) -> int:
        return total_score(self.scores)


@dataclass
class Medication:
    id: int
    animal_id: int
    name: str
    dose: str | None
    schedule: str | None
    active: bool


@dataclass
class EntryPhoto:
    id: int
    entry_id: int
    file_path: str
    caption: str | None


def _row_to_entry(row) -> Entry:
    return Entry(
        id=row["id"],
        animal_id=row["animal_id"],
        entry_date=row["entry_date"],
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


def save_entry(
    animal_id: int,
    entry_date: date,
    scores: dict[str, int],
    weight: float | None,
    weight_unit: str | None,
    appetite: str | None,
    notes: str | None,
) -> int:
    """Insert the day's entry, or update it if one already exists. Returns its id."""
    db = get_db()
    existing = get_entry_for_date(animal_id, entry_date)
    values = [scores[key] for key in CATEGORY_KEYS] + [weight, weight_unit, appetite, notes]
    if existing:
        db.execute(
            """UPDATE entries SET hurt=?, hunger=?, hydration=?, hygiene=?, happiness=?,
                   mobility=?, good_days=?, weight=?, weight_unit=?, appetite=?, notes=?,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id = ?""",
            values + [existing.id],
        )
        db.commit()
        return existing.id
    cur = db.execute(
        """INSERT INTO entries (animal_id, entry_date, hurt, hunger, hydration, hygiene,
               happiness, mobility, good_days, weight, weight_unit, appetite, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [animal_id, entry_date] + values,
    )
    db.commit()
    return cur.lastrowid


def delete_entry(entry_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()


# --- medications -------------------------------------------------------------

def _row_to_medication(row) -> Medication:
    return Medication(
        id=row["id"],
        animal_id=row["animal_id"],
        name=row["name"],
        dose=row["dose"],
        schedule=row["schedule"],
        active=bool(row["active"]),
    )


def list_medications(animal_id: int, active_only: bool = False) -> list[Medication]:
    sql = "SELECT * FROM medications WHERE animal_id = ?"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY active DESC, name COLLATE NOCASE"
    return [_row_to_medication(r) for r in get_db().execute(sql, (animal_id,)).fetchall()]


def get_medication(medication_id: int) -> Medication | None:
    row = get_db().execute(
        "SELECT * FROM medications WHERE id = ?", (medication_id,)
    ).fetchone()
    return _row_to_medication(row) if row else None


def create_medication(animal_id: int, name: str, dose: str | None, schedule: str | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO medications (animal_id, name, dose, schedule) VALUES (?, ?, ?, ?)",
        (animal_id, name, dose, schedule),
    )
    db.commit()
    return cur.lastrowid


def set_medication_active(medication_id: int, active: bool) -> None:
    db = get_db()
    db.execute("UPDATE medications SET active = ? WHERE id = ?", (int(active), medication_id))
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


# --- photos ------------------------------------------------------------------

def add_entry_photo(entry_id: int, file_path: str, caption: str | None = None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO photos (entry_id, file_path, caption) VALUES (?, ?, ?)",
        (entry_id, file_path, caption),
    )
    db.commit()
    return cur.lastrowid


def list_entry_photos(entry_id: int) -> list[EntryPhoto]:
    rows = get_db().execute(
        "SELECT * FROM photos WHERE entry_id = ? ORDER BY id", (entry_id,)
    ).fetchall()
    return [EntryPhoto(r["id"], r["entry_id"], r["file_path"], r["caption"]) for r in rows]


def get_entry_photo(photo_id: int) -> EntryPhoto | None:
    row = get_db().execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    return EntryPhoto(row["id"], row["entry_id"], row["file_path"], row["caption"]) if row else None


def delete_entry_photo(photo_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    db.commit()
