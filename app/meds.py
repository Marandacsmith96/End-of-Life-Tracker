"""Per-medication summary for the Medications page: how often it was given
over the last 30 logged days, and comfort scores around its start date.

Descriptive only: it says what was recorded, never whether a medication is
"working" (that is a conversation for the vet)."""
from dataclasses import dataclass
from datetime import date, timedelta

from . import analytics as an
from .entries import Entry, Medication
from .safety import guard

WINDOW_DAYS = 30


@dataclass(frozen=True)
class MedDay:
    day: date
    state: str  # "given" | "missed" | "none" (no check-in, or the medication wasn't offered)


@dataclass(frozen=True)
class MedSummary:
    medication: Medication
    given: int
    offered: int
    days: list[MedDay]
    comfort_text: str | None

    @property
    def count_text(self) -> str:
        if not self.offered:
            return "Not recorded in a check-in yet."
        plural = "day" if self.offered == 1 else "days"
        return f"Given on {self.given} of the {self.offered} {plural} you logged in the last {WINDOW_DAYS} days."


def summarize(medications: list[Medication], entries: list[Entry],
              given_days: dict[int, dict[date, bool]], end: date) -> list[MedSummary]:
    start = end - timedelta(days=WINDOW_DAYS - 1)
    comfort = an.category_points(entries, "hurt")
    out = []
    for med in medications:
        record = given_days.get(med.id, {})
        days = []
        for i in range(WINDOW_DAYS):
            day = start + timedelta(days=i)
            if day in record:
                days.append(MedDay(day, "given" if record[day] else "missed"))
            else:
                days.append(MedDay(day, "none"))
        offered = sum(1 for d in days if d.state != "none")
        given = sum(1 for d in days if d.state == "given")
        out.append(MedSummary(med, given, offered, days, _comfort_text(med, comfort)))
    return out


def _comfort_text(med: Medication, comfort: list[an.Point]) -> str | None:
    if med.start_date is None:
        return None
    eff = an.event_effect(comfort, med.start_date)
    if not eff.usable:
        return None
    return guard(
        f"Comfort scores averaged {eff.after_mean:.1f} in the two weeks after {med.name} started, "
        f"compared with {eff.before_mean:.1f} in the two weeks before. "
        "Many things change at once, so this is something to mention to your vet rather than a verdict.",
        owner_text=(med.name,),
    )
