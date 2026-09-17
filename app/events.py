"""Timeline events: vet visits, medication changes, procedures, and so on."""
from dataclasses import dataclass
from datetime import date

from .db import get_db

EVENT_TYPES = (
    ("vet_visit", "Veterinary appointment"),
    ("new_medication", "New medication"),
    ("dose_change", "Medication dose change"),
    ("medication_stopped", "Medication stopped"),
    ("pain_medication_started", "Pain medication started"),
    ("appetite_stimulant_started", "Appetite stimulant started"),
    ("procedure", "Procedure"),
    ("surgery", "Surgery"),
    ("hospitalization", "Hospitalization"),
    ("injury", "Injury"),
    ("diet_change", "Diet change"),
    ("treatment", "Treatment"),
    ("physical_therapy", "Physical therapy"),
    ("active_day", "Unusually active day"),
    ("travel", "Travel"),
    ("grooming", "Grooming"),
    ("other", "Other"),
)
EVENT_LABELS = dict(EVENT_TYPES)
# Events that plausibly change comfort; the insight engine compares before/after.
TREATMENT_TYPES = {
    "new_medication", "dose_change", "medication_stopped", "pain_medication_started",
    "appetite_stimulant_started", "procedure", "surgery", "treatment", "physical_therapy",
    "diet_change",
}


@dataclass
class Event:
    id: int
    animal_id: int
    event_date: date
    type: str
    title: str
    note: str | None

    @property
    def type_label(self) -> str:
        return EVENT_LABELS.get(self.type, "Other")


def _row(r) -> Event:
    return Event(r["id"], r["animal_id"], r["event_date"], r["type"], r["title"], r["note"])


def list_events(animal_id: int, start: date | None = None, end: date | None = None,
                newest_first: bool = True) -> list[Event]:
    sql = "SELECT * FROM pet_events WHERE animal_id = ?"
    params: list = [animal_id]
    if start is not None:
        sql += " AND event_date >= ?"
        params.append(start)
    if end is not None:
        sql += " AND event_date <= ?"
        params.append(end)
    sql += " ORDER BY event_date " + ("DESC" if newest_first else "ASC") + ", id"
    return [_row(r) for r in get_db().execute(sql, params).fetchall()]


def get_event(event_id: int) -> Event | None:
    row = get_db().execute("SELECT * FROM pet_events WHERE id = ?", (event_id,)).fetchone()
    return _row(row) if row else None


def create_event(animal_id: int, event_date: date, type_: str, title: str, note: str | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO pet_events (animal_id, event_date, type, title, note) VALUES (?, ?, ?, ?, ?)",
        (animal_id, event_date, type_, title, note),
    )
    db.commit()
    return cur.lastrowid


def update_event(event_id: int, event_date: date, type_: str, title: str, note: str | None) -> None:
    db = get_db()
    db.execute(
        "UPDATE pet_events SET event_date = ?, type = ?, title = ?, note = ? WHERE id = ?",
        (event_date, type_, title, note, event_id),
    )
    db.commit()


def delete_event(event_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM pet_events WHERE id = ?", (event_id,))
    db.commit()


def last_vet_visit(animal_id: int) -> Event | None:
    row = get_db().execute(
        """SELECT * FROM pet_events WHERE animal_id = ? AND type = 'vet_visit'
           ORDER BY event_date DESC, id DESC LIMIT 1""",
        (animal_id,),
    ).fetchone()
    return _row(row) if row else None
