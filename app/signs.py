"""Clinical signs worth watching around a supplement, and the before/after
summary for each supplement.

A supplement is hard to judge by feel: you hope it helps, and hope colours
memory. So the owner picks the signs it is meant to affect, scores them in
the daily check-in, and this module shows the numbers before and after it
started. It describes; it never says the supplement works.

Some signs are their own 0-10 question (itching, stiffness after rest, skin
and coat, stool, energy). Two come from the HHHHHMM scores already recorded
(mobility, appetite), so there is nothing extra to answer for those.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from . import analytics as an
from .db import get_db
from .entries import Entry, Medication
from .safety import guard


@dataclass(frozen=True)
class Sign:
    key: str
    label: str
    question: str          # with {name}
    low: str               # what 0 means
    high: str              # what 10 means
    higher_is_better: bool
    score_key: str | None = None   # taken from the HHHHHMM score of that name instead of asked
    icon: str = "sparkles"         # the tile next to the question in the check-in

    @property
    def short(self) -> str:
        """The label without the "(from the daily scores)" note, for sentences."""
        return self.label.split(" (")[0]

    @property
    def asked(self) -> bool:
        return self.score_key is None


SIGNS: tuple[Sign, ...] = (
    Sign("itching", "Itching", "How much did {name} scratch, lick or chew today?",
         "not at all", "constantly, hard to settle", higher_is_better=False, icon="sparkles"),
    Sign("stiffness", "Stiffness after rest", "How stiff was {name} getting up after a rest?",
         "up like a youngster", "could not get up without help", higher_is_better=False, icon="stairs"),
    Sign("coat", "Skin and coat", "How did {name}'s skin and coat look today?",
         "flaky, red or dull", "clear skin, glossy coat", higher_is_better=True, icon="leaf"),
    Sign("stool", "Stool", "What were {name}'s stools like today?",
         "very loose or none", "normal and formed", higher_is_better=True, icon="bowl"),
    Sign("energy", "Energy", "How much energy did {name} have today?",
         "flat all day", "full of beans", higher_is_better=True, icon="sun"),
    Sign("mobility", "Mobility (from the daily scores)", "", "", "", higher_is_better=True, score_key="mobility"),
    Sign("appetite", "Appetite (from the daily scores)", "", "", "", higher_is_better=True, score_key="hunger"),
)
SIGN_BY_KEY = {s.key: s for s in SIGNS}
ASKED = tuple(s for s in SIGNS if s.asked)
ASKED_KEYS = tuple(s.key for s in SIGNS if s.asked)
WINDOW_DAYS = 30


# --- storage --------------------------------------------------------------------

def is_valid_value(raw) -> bool:
    return isinstance(raw, str) and raw.isdecimal() and 0 <= int(raw) <= 10


def save_signs(animal_id: int, day: date, values: dict[str, int]) -> None:
    """Store the signs scored on ``day`` (only the ones given; others are untouched)."""
    db = get_db()
    for key, value in values.items():
        if key not in SIGN_BY_KEY or not SIGN_BY_KEY[key].asked:
            continue
        db.execute(
            """INSERT INTO sign_entries (animal_id, entry_date, sign_key, value) VALUES (?, ?, ?, ?)
               ON CONFLICT (animal_id, entry_date, sign_key) DO UPDATE SET value = excluded.value""",
            (animal_id, day, key, int(value)),
        )
    db.commit()


def parse_form(form) -> tuple[dict[str, int], list[str]]:
    """Like the HHHHHMM sliders: only signs whose ``sign_<key>_set`` flag is 1 count."""
    values: dict[str, int] = {}
    errors: list[str] = []
    for key in ASKED_KEYS:
        if form.get(f"sign_{key}_set") != "1":
            continue
        raw = form.get(f"sign_{key}")
        if not is_valid_value(raw):
            errors.append(f"{SIGN_BY_KEY[key].label} must be a whole number from 0 to 10.")
        else:
            values[key] = int(raw)
    return values, errors


def signs_on(animal_id: int, day: date) -> dict[str, int]:
    rows = get_db().execute(
        "SELECT sign_key, value FROM sign_entries WHERE animal_id = ? AND entry_date = ?", (animal_id, day)
    ).fetchall()
    return {r["sign_key"]: r["value"] for r in rows}


def signs_for_animal(animal_id: int) -> dict[str, list[an.Point]]:
    """{sign key: points, oldest first} for every asked sign the pet has scores for."""
    rows = get_db().execute(
        "SELECT sign_key, entry_date, value FROM sign_entries WHERE animal_id = ? ORDER BY entry_date",
        (animal_id,),
    ).fetchall()
    out: dict[str, list[an.Point]] = {}
    for r in rows:
        out.setdefault(r["sign_key"], []).append(an.Point(r["entry_date"], float(r["value"])))
    return out


def watched_signs(supplements: list[Medication]) -> list[Sign]:
    """The asked signs any active supplement watches, in registry order."""
    keys = {k for s in supplements if s.active for k in s.signs}
    return [s for s in SIGNS if s.asked and s.key in keys]


# --- the summary ----------------------------------------------------------------

@dataclass(frozen=True)
class SignView:
    sign: Sign
    points: list[an.Point]            # inside the 30-day window, oldest first
    before: float | None              # mean in the 14 days before the supplement started
    after: float | None               # mean in the 14 days from the start
    before_n: int
    after_n: int
    recent: float | None              # mean of the last 7 days
    previous: float | None            # mean of the 21 days before those
    text: str | None                  # the guarded sentence, or None when there is not enough


@dataclass(frozen=True)
class SupplementView:
    supplement: Medication
    signs: list[SignView]
    days: list[date]

    def bars(self, view: SignView) -> list[tuple[date, float | None]]:
        by_day = {p.day: p.value for p in view.points}
        return [(d, by_day.get(d)) for d in self.days]


def _points_for(sign: Sign, entries: list[Entry], sign_points: dict[str, list[an.Point]]) -> list[an.Point]:
    if sign.score_key:
        return an.category_points(entries, sign.score_key)
    return sorted(sign_points.get(sign.key, []), key=lambda p: p.day)


def _sentence(sign: Sign, supplement: Medication, eff: an.EventEffect) -> str | None:
    if not eff.usable or eff.before_mean is None or eff.after_mean is None:
        return None
    direction = "lower" if eff.after_mean < eff.before_mean else "higher"
    if abs(eff.after_mean - eff.before_mean) < 0.5:
        shape = f"{sign.short} scores averaged about the same in the two weeks after {supplement.name} started as in the two weeks before"
        detail = f" ({eff.after_mean:.1f} compared with {eff.before_mean:.1f})."
    else:
        shape = (f"{sign.short} scores were {direction} in the two weeks after {supplement.name} started: "
                 f"average {eff.after_mean:.1f} compared with {eff.before_mean:.1f} before")
        detail = ". " + ("Lower is less of it." if not sign.higher_is_better else "Higher is better for this one.")
    return guard(shape + detail + " Many things change at once, so this is something to mention to your vet rather than a verdict.",
                 owner_text=(supplement.name,))


@dataclass(frozen=True)
class VetSupplement:
    """One supplement as the vet sees it: what, why, how reliably given, the
    owner's latest take, and each watched sign's numbers around the start."""
    name: str
    details: str            # dose · schedule
    purpose: str | None
    source: str             # who recommended it, as a label ("" when unknown)
    started: date | None
    active: bool
    given_text: str         # from meds.summarize
    owner_take: str | None  # "Seems to help (Nov 4): Up the back step without the pause."
    signs: list[str]        # one short line per sign


def for_vet(views: list[SupplementView], given: dict, notes: dict) -> list[VetSupplement]:
    out = []
    for v in views:
        sup = v.supplement
        latest = (notes.get(sup.id) or [None])[0]
        take = None
        if latest is not None:
            take = f"{latest.label} ({latest.note_date:%b} {latest.note_date.day})"
            if latest.note:
                take += f": {latest.note}"
        lines = []
        for sv in v.signs:
            hint = "higher is better" if sv.sign.higher_is_better else "lower is less of it"
            if sv.before is not None and sv.after is not None and sv.before_n >= 4 and sv.after_n >= 4:
                lines.append(f"{sv.sign.short}: {sv.before:.1f} in the two weeks before, {sv.after:.1f} in the two weeks after ({hint})")
            elif sv.recent is not None:
                lines.append(f"{sv.sign.short}: {sv.recent:.1f} over the last 7 days ({hint}); not enough scored days around the start to compare")
            else:
                lines.append(f"{sv.sign.short}: no recent scores")
        details = " · ".join(x for x in (sup.dose, sup.schedule) if x)
        given_text = given[sup.id].count_text if sup.id in given else ""
        out.append(VetSupplement(sup.name, details, sup.purpose, sup.source_label, sup.start_date, sup.active,
                                 given_text, take, lines))
    return out


def summarize(supplements: list[Medication], entries: list[Entry], end: date) -> list[SupplementView]:
    """One view per supplement: each watched sign's numbers around its start and over the last 30 days."""
    sign_points = signs_for_animal(supplements[0].animal_id) if supplements else {}
    start = end - timedelta(days=WINDOW_DAYS - 1)
    days = [start + timedelta(days=i) for i in range(WINDOW_DAYS)]
    out = []
    for sup in supplements:
        views = []
        for key in sup.signs:
            sign = SIGN_BY_KEY.get(key)
            if sign is None:
                continue
            pts = _points_for(sign, entries, sign_points)
            inside = [p for p in pts if start <= p.day <= end]
            comp = an.period_comparison(pts, end)
            eff = an.event_effect(pts, sup.start_date) if sup.start_date else an.EventEffect(None, None, 0, 0)
            views.append(SignView(sign, inside, eff.before_mean, eff.after_mean, eff.before_n, eff.after_n,
                                  comp.recent_mean, comp.previous_mean, _sentence(sign, sup, eff)))
        out.append(SupplementView(sup, views, days))
    return out
