"""Personalized good-day behaviors ("What does a good day look like?")."""
from dataclasses import dataclass

from .db import get_db

MIN_MARKERS = 3
MAX_MARKERS = 5

SUGGESTIONS = {
    "dog": [
        "Greets me at the door",
        "Finishes dinner",
        "Gets onto the couch without help",
        "Wants to go for a walk",
        "Plays with a favorite toy",
        "Comes outside with me",
        "Seeks affection",
        "Sleeps comfortably",
        "Gets up without help",
    ],
    "cat": [
        "Comes to greet me",
        "Finishes dinner",
        "Jumps onto the bed or windowsill",
        "Uses the litter box normally",
        "Grooms herself",
        "Seeks affection",
        "Plays or chases something",
        "Sleeps comfortably",
        "Sits in a favorite sunny spot",
    ],
}


@dataclass
class Marker:
    id: int
    animal_id: int
    label: str
    sort_order: int
    active: bool


def _row(r) -> Marker:
    return Marker(r["id"], r["animal_id"], r["label"], r["sort_order"], bool(r["active"]))


def list_markers(animal_id: int, active_only: bool = True) -> list[Marker]:
    sql = "SELECT * FROM personal_markers WHERE animal_id = ?"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY active DESC, sort_order, id"
    return [_row(r) for r in get_db().execute(sql, (animal_id,)).fetchall()]


def get_marker(marker_id: int) -> Marker | None:
    row = get_db().execute("SELECT * FROM personal_markers WHERE id = ?", (marker_id,)).fetchone()
    return _row(row) if row else None


def create_marker(animal_id: int, label: str) -> int:
    db = get_db()
    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM personal_markers WHERE animal_id = ?",
        (animal_id,),
    ).fetchone()[0]
    cur = db.execute(
        "INSERT INTO personal_markers (animal_id, label, sort_order) VALUES (?, ?, ?)",
        (animal_id, label, order),
    )
    db.commit()
    return cur.lastrowid


def replace_markers(animal_id: int, labels: list[str]) -> None:
    """Set the active marker list. Existing labels keep their history; removed
    ones are deactivated (never deleted), so old responses still count."""
    db = get_db()
    existing = {m.label.strip().lower(): m for m in list_markers(animal_id, active_only=False)}
    wanted = [label.strip() for label in labels if label.strip()]
    keep_ids = set()
    for order, label in enumerate(wanted, start=1):
        found = existing.get(label.lower())
        if found:
            db.execute(
                "UPDATE personal_markers SET active = 1, sort_order = ?, label = ? WHERE id = ?",
                (order, label, found.id),
            )
            keep_ids.add(found.id)
        else:
            cur = db.execute(
                "INSERT INTO personal_markers (animal_id, label, sort_order) VALUES (?, ?, ?)",
                (animal_id, label, order),
            )
            keep_ids.add(cur.lastrowid)
    for m in existing.values():
        if m.id not in keep_ids:
            db.execute("UPDATE personal_markers SET active = 0 WHERE id = ?", (m.id,))
    db.commit()


def set_marker_active(marker_id: int, active: bool) -> None:
    db = get_db()
    db.execute("UPDATE personal_markers SET active = ? WHERE id = ?", (int(active), marker_id))
    db.commit()


def set_responses(entry_id: int, completed_ids: set[int], offered_ids: set[int]) -> None:
    db = get_db()
    for marker_id in offered_ids:
        db.execute(
            """INSERT INTO marker_responses (entry_id, marker_id, completed) VALUES (?, ?, ?)
               ON CONFLICT (entry_id, marker_id) DO UPDATE SET completed = excluded.completed""",
            (entry_id, marker_id, int(marker_id in completed_ids)),
        )
    db.commit()


def responses_for_entry(entry_id: int) -> dict[int, bool]:
    rows = get_db().execute(
        "SELECT marker_id, completed FROM marker_responses WHERE entry_id = ?", (entry_id,)
    ).fetchall()
    return {r["marker_id"]: bool(r["completed"]) for r in rows}


def responses_for_animal(animal_id: int) -> dict[int, dict[int, bool]]:
    """{entry_id: {marker_id: completed}} for every entry of the animal."""
    rows = get_db().execute(
        """SELECT mr.entry_id, mr.marker_id, mr.completed
           FROM marker_responses mr JOIN entries e ON e.id = mr.entry_id
           WHERE e.animal_id = ?""",
        (animal_id,),
    ).fetchall()
    out: dict[int, dict[int, bool]] = {}
    for r in rows:
        out.setdefault(r["entry_id"], {})[r["marker_id"]] = bool(r["completed"])
    return out
