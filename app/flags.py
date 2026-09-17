"""Pattern flags: gentle nudges to talk with the vet.

Every function here is pure (entries in, flags out) so the rules are easy to
test and easy for a vet to review. Wording never gives a verdict; it points
at a pattern and suggests a conversation.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from .charts import to_unit
from .entries import Entry
from .scoring import ACCEPTABLE_TOTAL, CATEGORY_KEYS, CATEGORY_LABELS

LOW_TOTAL_DAYS = 3
LOW_CATEGORY_SCORE = 3
LOW_CATEGORY_DAYS = 3
WEIGHT_DROP_FRACTION = 0.10
WEIGHT_LOOKBACK_DAYS = 30
WEIGHT_LOOKBACK_TOLERANCE = 10  # accept a comparison weight 20-40 days back
NO_APPETITE_DAYS = 2
MISSED_ENTRY_DAYS = 3

VET_LINE = "Consider talking with your vet about this pattern."


@dataclass
class Flag:
    key: str
    level: str  # "watch" (a health pattern) or "reminder" (logging nudge)
    title: str
    detail: str

    @property
    def is_health(self) -> bool:
        return self.level == "watch"


def _ordered(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: e.entry_date)


def _fmt(day: date) -> str:
    return f"{day:%b} {day.day}"


def low_total(entries: list[Entry]) -> Flag | None:
    recent = _ordered(entries)[-LOW_TOTAL_DAYS:]
    if len(recent) < LOW_TOTAL_DAYS or any(e.total > ACCEPTABLE_TOTAL for e in recent):
        return None
    totals = ", ".join(str(e.total) for e in recent)
    return Flag(
        "low_total", "watch",
        f"Total score at or below {ACCEPTABLE_TOTAL} for the last {LOW_TOTAL_DAYS} entries",
        f"The last {LOW_TOTAL_DAYS} totals were {totals} out of 70 "
        f"({_fmt(recent[0].entry_date)} to {_fmt(recent[-1].entry_date)}). {VET_LINE}",
    )


def low_categories(entries: list[Entry]) -> list[Flag]:
    recent = _ordered(entries)[-LOW_CATEGORY_DAYS:]
    if len(recent) < LOW_CATEGORY_DAYS:
        return []
    flags = []
    for key in CATEGORY_KEYS:
        if all(getattr(e, key) <= LOW_CATEGORY_SCORE for e in recent):
            scores = ", ".join(str(getattr(e, key)) for e in recent)
            flags.append(Flag(
                f"low_{key}", "watch",
                f"{CATEGORY_LABELS[key]} scored {LOW_CATEGORY_SCORE} or lower "
                f"for the last {LOW_CATEGORY_DAYS} entries",
                f"{CATEGORY_LABELS[key]} was {scores} out of 10 on the last "
                f"{LOW_CATEGORY_DAYS} entries. {VET_LINE}",
            ))
    return flags


def weight_drop(entries: list[Entry]) -> Flag | None:
    weighed = [e for e in _ordered(entries) if e.weight is not None and e.weight_unit]
    if len(weighed) < 2:
        return None
    latest = weighed[-1]
    target = latest.entry_date - timedelta(days=WEIGHT_LOOKBACK_DAYS)
    candidates = [
        e for e in weighed[:-1]
        if abs((e.entry_date - target).days) <= WEIGHT_LOOKBACK_TOLERANCE
    ]
    if not candidates:
        return None
    earlier = min(candidates, key=lambda e: abs((e.entry_date - target).days))
    unit = latest.weight_unit
    before = to_unit(earlier.weight, earlier.weight_unit, unit)
    drop = (before - latest.weight) / before
    if drop < WEIGHT_DROP_FRACTION:
        return None
    return Flag(
        "weight_drop", "watch",
        f"Weight down {drop:.0%} over about a month",
        f"{before:g} {unit} on {_fmt(earlier.entry_date)} to {latest.weight:g} {unit} "
        f"on {_fmt(latest.entry_date)}. {VET_LINE}",
    )


def no_appetite(entries: list[Entry]) -> Flag | None:
    recent = _ordered(entries)[-NO_APPETITE_DAYS:]
    if len(recent) < NO_APPETITE_DAYS or any(e.appetite != "none" for e in recent):
        return None
    return Flag(
        "no_appetite", "watch",
        f"Not eating on the last {NO_APPETITE_DAYS} entries",
        f"Appetite was logged as \"not eating\" on {_fmt(recent[0].entry_date)} and "
        f"{_fmt(recent[-1].entry_date)}. {VET_LINE}",
    )


def missed_entries(entries: list[Entry], today: date | None = None) -> Flag | None:
    if not entries:
        return None
    today = today or date.today()
    latest = _ordered(entries)[-1].entry_date
    gap = (today - latest).days
    if gap < MISSED_ENTRY_DAYS:
        return None
    return Flag(
        "missed_entries", "reminder",
        f"No entry for {gap} days",
        f"The last entry was {_fmt(latest)}. Regular entries make the patterns "
        "easier to see.",
    )


def evaluate(entries: list[Entry], today: date | None = None) -> list[Flag]:
    """Run every rule and return the flags that apply, health patterns first."""
    flags: list[Flag] = []
    for flag in (low_total(entries), *low_categories(entries), weight_drop(entries),
                 no_appetite(entries), missed_entries(entries, today)):
        if flag is not None:
            flags.append(flag)
    return flags


# --- database-backed convenience ---------------------------------------------

FLAG_WINDOW_DAYS = 60


def for_animal(animal_id: int, today: date | None = None) -> list[Flag]:
    """Evaluate the rules against an animal's recent entries."""
    from .entries import list_entries  # local import keeps the rules pure

    today = today or date.today()
    recent = list_entries(animal_id, start=today - timedelta(days=FLAG_WINDOW_DAYS))
    return evaluate(recent, today)
