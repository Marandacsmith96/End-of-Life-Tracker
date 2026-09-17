"""Owner-estimated baseline from about six months ago.

Stored separately from daily entries and always labelled as an estimate.
"""
from dataclasses import dataclass
from datetime import date

from .db import get_db
from .scoring import CATEGORY_KEYS

GOOD_DAY_PATTERNS = (
    ("mostly_good", "Mostly good days"),
    ("mixed", "A mix of good and bad days"),
    ("mostly_bad", "Mostly bad days"),
)
MARKER_FREQUENCIES = (
    ("most_days", "Most days"),
    ("some_days", "Some days"),
    ("rarely", "Rarely"),
)


@dataclass
class Baseline:
    animal_id: int
    approximate_date: date | None
    hurt: int | None
    hunger: int | None
    hydration: int | None
    hygiene: int | None
    happiness: int | None
    mobility: int | None
    good_days: int | None
    good_day_pattern: str | None
    marker_frequency: str | None
    notes: str | None

    @property
    def scores(self) -> dict[str, int | None]:
        return {key: getattr(self, key) for key in CATEGORY_KEYS}

    @property
    def mean(self) -> float | None:
        values = [v for v in self.scores.values() if v is not None]
        return round(sum(values) / len(values), 2) if values else None

    @property
    def label(self) -> str:
        when = f"approximately {self.approximate_date:%B} {self.approximate_date.year}" \
            if self.approximate_date else "approximately 6 months ago"
        return f"Owner-estimated baseline — {when}"


def get_baseline(animal_id: int) -> Baseline | None:
    row = get_db().execute("SELECT * FROM baselines WHERE animal_id = ?", (animal_id,)).fetchone()
    if not row:
        return None
    return Baseline(
        animal_id=row["animal_id"], approximate_date=row["approximate_date"],
        hurt=row["hurt"], hunger=row["hunger"], hydration=row["hydration"], hygiene=row["hygiene"],
        happiness=row["happiness"], mobility=row["mobility"], good_days=row["good_days"],
        good_day_pattern=row["good_day_pattern"], marker_frequency=row["marker_frequency"],
        notes=row["notes"],
    )


def save_baseline(
    animal_id: int, approximate_date: date | None, scores: dict[str, int | None],
    good_day_pattern: str | None, marker_frequency: str | None, notes: str | None,
) -> None:
    db = get_db()
    db.execute(
        """INSERT INTO baselines (animal_id, approximate_date, hurt, hunger, hydration, hygiene,
               happiness, mobility, good_days, good_day_pattern, marker_frequency, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (animal_id) DO UPDATE SET
               approximate_date = excluded.approximate_date, hurt = excluded.hurt,
               hunger = excluded.hunger, hydration = excluded.hydration, hygiene = excluded.hygiene,
               happiness = excluded.happiness, mobility = excluded.mobility,
               good_days = excluded.good_days, good_day_pattern = excluded.good_day_pattern,
               marker_frequency = excluded.marker_frequency, notes = excluded.notes""",
        (animal_id, approximate_date, *[scores.get(k) for k in CATEGORY_KEYS],
         good_day_pattern, marker_frequency, notes),
    )
    db.commit()


def delete_baseline(animal_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM baselines WHERE animal_id = ?", (animal_id,))
    db.commit()
