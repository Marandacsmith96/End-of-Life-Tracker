"""Trend analytics for short, noisy, irregularly sampled 0-10 self-reports.

Design rules (see docs/ARCHITECTURE.md for the longer explanation):

* Missing days are missing. Nothing is interpolated; every statistic is
  computed over the days that were actually logged.
* Smoothing is a **time-windowed trailing mean**: for each logged day, the
  mean of all logged values in the previous ``window_days`` calendar days
  (inclusive). A window with fewer than ``min_points`` observations yields
  ``None`` so the chart can show a gap instead of a confident line. An EWMA
  variant is provided for comparison but the windowed mean is what the UI uses
  because it is easier to explain to an owner and a vet.
* A trend needs sustained evidence: a recent period is compared with the
  period before it, both periods must contain enough observations, and most
  of the recent observations must point the same way. A single bad day never
  becomes a trend.
* Every function here is pure and takes plain lists so it can be unit-tested
  and later swapped for a proper change-point method behind the same
  interfaces.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, pstdev

from .entries import Entry
from .scoring import CATEGORY_KEYS

# --- tunables ---------------------------------------------------------------
SMOOTH_WINDOW_DAYS = 7
SMOOTH_MIN_POINTS = 3
RECENT_DAYS = 7          # "recent period" length for comparisons
PREVIOUS_DAYS = 21       # the period before it (days 8-28 back)
MIN_RECENT_POINTS = 4
MIN_PREVIOUS_POINTS = 6
MIN_LOGGED_30D = 8       # below this the 30-day picture is "limited"
TREND_DELTA = 0.75       # mean change (0-10 scale) that counts as a trend
CONSISTENCY = 0.75       # share of recent points that must agree with the direction
VARIABILITY_STD = 1.4    # recent std that counts as "more variation"
VARIABILITY_RATIO = 1.4  # ...and it must be this much larger than before
SPIKE_DELTA = 2.5        # single-day deviation that counts as a fluctuation


@dataclass(frozen=True)
class Point:
    day: date
    value: float


@dataclass(frozen=True)
class Sufficiency:
    level: str          # "none" | "limited" | "adequate"
    logged: int         # entries with a value in the window
    span_days: int      # days between first and last logged point in the window
    text: str


@dataclass(frozen=True)
class Comparison:
    recent_mean: float | None
    previous_mean: float | None
    recent_n: int
    previous_n: int

    @property
    def delta(self) -> float | None:
        if self.recent_mean is None or self.previous_mean is None:
            return None
        return round(self.recent_mean - self.previous_mean, 2)

    @property
    def usable(self) -> bool:
        return self.recent_n >= MIN_RECENT_POINTS and self.previous_n >= MIN_PREVIOUS_POINTS


@dataclass(frozen=True)
class Classification:
    kind: str           # insufficient_data | stable | gradual_down | gradual_up |
                        # increased_variability | temporary_fluctuation
    comparison: Comparison
    sufficiency: Sufficiency


# --- series builders --------------------------------------------------------

def overall_points(entries: list[Entry]) -> list[Point]:
    """One point per logged day that has at least one HHHHHMM score."""
    out = [Point(e.entry_date, e.mean) for e in entries if e.mean is not None]
    return sorted(out, key=lambda p: p.day)


def category_points(entries: list[Entry], key: str) -> list[Point]:
    out = [Point(e.entry_date, float(getattr(e, key))) for e in entries if getattr(e, key) is not None]
    return sorted(out, key=lambda p: p.day)


def day_status_points(entries: list[Entry]) -> list[tuple[date, str]]:
    return sorted(((e.entry_date, e.day_status) for e in entries if e.day_status), key=lambda t: t[0])


# --- smoothing --------------------------------------------------------------

def rolling_mean(points: list[Point], window_days: int = SMOOTH_WINDOW_DAYS,
                 min_points: int = SMOOTH_MIN_POINTS) -> list[float | None]:
    """Time-windowed trailing mean, aligned with ``points`` (which must be sorted).

    Uses calendar days, not sample counts, so a gap in logging widens the
    uncertainty instead of silently pulling in stale values.
    """
    out: list[float | None] = []
    for i, p in enumerate(points):
        start = p.day - timedelta(days=window_days - 1)
        window = [q.value for q in points[: i + 1] if q.day >= start]
        out.append(round(mean(window), 2) if len(window) >= min_points else None)
    return out


def ewma(points: list[Point], halflife_days: float = 5.0) -> list[float]:
    """Exponentially weighted mean that decays by *elapsed time*, so gaps in
    logging reduce the weight of old observations. Provided as an alternative
    smoother; not used by the UI by default."""
    out: list[float] = []
    last_day: date | None = None
    level: float | None = None
    for p in points:
        if level is None:
            level = p.value
        else:
            gap = (p.day - last_day).days
            alpha = 1 - 0.5 ** (gap / halflife_days)
            level = level + alpha * (p.value - level)
        out.append(round(level, 2))
        last_day = p.day
    return out


# --- sufficiency ------------------------------------------------------------

def sufficiency(points: list[Point], end: date, window_days: int = 30) -> Sufficiency:
    start = end - timedelta(days=window_days - 1)
    inside = [p for p in points if start <= p.day <= end]
    if not inside:
        return Sufficiency("none", 0, 0, "No quality-of-life scores have been recorded in this period yet.")
    span = (inside[-1].day - inside[0].day).days
    if len(inside) < MIN_LOGGED_30D or span < 10:
        return Sufficiency(
            "limited", len(inside), span,
            f"Limited data: {len(inside)} scored {'day' if len(inside) == 1 else 'days'} in the last "
            f"{window_days} days. There isn't enough information yet to show a reliable trend.",
        )
    return Sufficiency("adequate", len(inside), span,
                       f"Based on {len(inside)} scored days in the last {window_days} days.")


# --- comparisons ------------------------------------------------------------

def period_comparison(points: list[Point], end: date, recent_days: int = RECENT_DAYS,
                      previous_days: int = PREVIOUS_DAYS) -> Comparison:
    """Mean of the last ``recent_days`` vs the ``previous_days`` before them."""
    recent_start = end - timedelta(days=recent_days - 1)
    previous_start = recent_start - timedelta(days=previous_days)
    recent = [p.value for p in points if recent_start <= p.day <= end]
    previous = [p.value for p in points if previous_start <= p.day < recent_start]
    return Comparison(
        round(mean(recent), 2) if recent else None,
        round(mean(previous), 2) if previous else None,
        len(recent), len(previous),
    )


def window_mean(points: list[Point], start: date, end: date) -> tuple[float | None, int]:
    vals = [p.value for p in points if start <= p.day <= end]
    return (round(mean(vals), 2) if vals else None), len(vals)


# --- classification ---------------------------------------------------------

def classify(points: list[Point], end: date) -> Classification:
    """Transparent rules, applied in order. See module docstring."""
    suff = sufficiency(points, end)
    comp = period_comparison(points, end)
    if suff.level != "adequate" or not comp.usable:
        return Classification("insufficient_data", comp, suff)

    recent_start = end - timedelta(days=RECENT_DAYS - 1)
    previous_start = recent_start - timedelta(days=PREVIOUS_DAYS)
    recent = [p.value for p in points if recent_start <= p.day <= end]
    previous = [p.value for p in points if previous_start <= p.day < recent_start]
    delta = comp.delta

    if delta is not None and delta <= -TREND_DELTA:
        below = sum(1 for v in recent if v < comp.previous_mean)
        if below / len(recent) >= CONSISTENCY:
            return Classification("gradual_down", comp, suff)
    if delta is not None and delta >= TREND_DELTA:
        above = sum(1 for v in recent if v > comp.previous_mean)
        if above / len(recent) >= CONSISTENCY:
            return Classification("gradual_up", comp, suff)

    # A lone outlier (one very different day among otherwise steady ones) is a
    # fluctuation, not variability and not a trend.
    outliers = [v for v in recent if abs(v - comp.previous_mean) >= SPIKE_DELTA]
    rest = [v for v in recent if abs(v - comp.previous_mean) < SPIKE_DELTA]
    rest_std = pstdev(rest) if len(rest) > 1 else 0.0
    if len(outliers) == 1 and rest_std < VARIABILITY_STD:
        return Classification("temporary_fluctuation", comp, suff)

    recent_std = pstdev(recent) if len(recent) > 1 else 0.0
    previous_std = pstdev(previous) if len(previous) > 1 else 0.0
    if recent_std >= VARIABILITY_STD and recent_std >= VARIABILITY_RATIO * max(previous_std, 0.5):
        return Classification("increased_variability", comp, suff)

    return Classification("stable", comp, suff)


# --- good / bad days --------------------------------------------------------

@dataclass(frozen=True)
class DayCounts:
    good: int
    mixed: int
    bad: int
    start: date
    end: date

    @property
    def logged(self) -> int:
        return self.good + self.mixed + self.bad

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def not_logged(self) -> int:
        return self.days - self.logged


def day_counts(entries: list[Entry], start: date, end: date) -> DayCounts:
    good = mixed = bad = 0
    for e in entries:
        if start <= e.entry_date <= end and e.day_status:
            if e.day_status == "good":
                good += 1
            elif e.day_status == "bad":
                bad += 1
            else:
                mixed += 1
    return DayCounts(good, mixed, bad, start, end)


# --- personal markers -------------------------------------------------------

@dataclass(frozen=True)
class MarkerRate:
    marker_id: int
    label: str
    completed: int
    logged: int

    @property
    def pct(self) -> int | None:
        return round(100 * self.completed / self.logged) if self.logged else None


def marker_rates(entries: list[Entry], responses: dict[int, dict[int, bool]],
                 markers, start: date, end: date) -> list[MarkerRate]:
    """Completion rate per marker over logged days in [start, end]."""
    out = []
    for m in markers:
        completed = logged = 0
        for e in entries:
            if not (start <= e.entry_date <= end):
                continue
            answers = responses.get(e.id)
            if answers is None or m.id not in answers:
                continue
            logged += 1
            completed += int(answers[m.id])
        out.append(MarkerRate(m.id, m.label, completed, logged))
    return out


def markers_today(entry_id: int | None, responses: dict[int, dict[int, bool]],
                  markers) -> tuple[int, int]:
    if entry_id is None or entry_id not in responses:
        return 0, len(markers)
    answers = responses[entry_id]
    return sum(1 for m in markers if answers.get(m.id)), len(markers)


# --- baseline & events ------------------------------------------------------

def below_baseline(points: list[Point], baseline_value: float, last_n: int = 12) -> tuple[int, int]:
    """How many of the last ``last_n`` logged points sit below the baseline."""
    recent = points[-last_n:]
    return sum(1 for p in recent if p.value < baseline_value), len(recent)


@dataclass(frozen=True)
class EventEffect:
    before_mean: float | None
    after_mean: float | None
    before_n: int
    after_n: int

    @property
    def delta(self) -> float | None:
        if self.before_mean is None or self.after_mean is None:
            return None
        return round(self.after_mean - self.before_mean, 2)

    @property
    def usable(self) -> bool:
        return self.before_n >= 4 and self.after_n >= 4


def event_effect(points: list[Point], on: date, days: int = 14) -> EventEffect:
    before = [p.value for p in points if on - timedelta(days=days) <= p.day < on]
    after = [p.value for p in points if on <= p.day < on + timedelta(days=days)]
    return EventEffect(
        round(mean(before), 2) if before else None,
        round(mean(after), 2) if after else None,
        len(before), len(after),
    )


# --- convenience ------------------------------------------------------------

def category_means(entries: list[Entry], start: date, end: date) -> dict[str, tuple[float | None, int]]:
    return {key: window_mean(category_points(entries, key), start, end) for key in CATEGORY_KEYS}
