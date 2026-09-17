"""Deterministic, explainable observations built from the recorded data.

Each insight carries the numbers it came from. Text is passed through the
safety layer so nothing here can produce a verdict. This is not AI and is
never described as such.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import analytics as an
from .baseline import Baseline
from .entries import Entry
from .events import Event, TREATMENT_TYPES
from .safety import MAX_GUIDANCE, guard
from .scoring import CATEGORY_KEYS, CATEGORY_LABELS

# How the trend classification is described to the owner. Cautious on purpose.
TREND_TEXT = {
    "insufficient_data": "There isn't enough information yet to identify a clear pattern.",
    "stable": "Recent scores have been relatively stable.",
    "gradual_down": "Scores have generally trended lower over the past few weeks.",
    "gradual_up": "Scores have generally trended higher over the past few weeks.",
    "increased_variability": "There has been more day-to-day variation recently.",
    "temporary_fluctuation": "Recent scores include a short-lived change that has not persisted.",
}


@dataclass
class Insight:
    text: str
    kind: str                       # trend | days | category | marker | baseline | event | note
    level: str = "info"             # info | attention
    numbers: dict = field(default_factory=dict)


def _fmt(d: date) -> str:
    return f"{d:%b} {d.day}"


def trend_summary(entries: list[Entry], end: date, name: str) -> tuple[an.Classification, str]:
    cls = an.classify(an.overall_points(entries), end)
    return cls, guard(TREND_TEXT[cls.kind])


def generate(entries: list[Entry], end: date, name: str, markers=(), responses=None,
             baseline: Baseline | None = None, events: list[Event] = (),
             today_entry: Entry | None = None) -> list[Insight]:
    """Build the insight list for the dashboard and the vet-prep page."""
    responses = responses or {}
    out: list[Insight] = []
    points = an.overall_points(entries)
    cls = an.classify(points, end)

    # 1. Overall trend.
    text = TREND_TEXT[cls.kind]
    numbers = {}
    if cls.comparison.usable:
        numbers = {"recent_mean": cls.comparison.recent_mean, "previous_mean": cls.comparison.previous_mean,
                   "recent_n": cls.comparison.recent_n, "previous_n": cls.comparison.previous_n}
        text += (f" Average {cls.comparison.recent_mean:.1f} over the last {an.RECENT_DAYS} days "
                 f"({cls.comparison.recent_n} scored), compared with {cls.comparison.previous_mean:.1f} "
                 f"over the {an.PREVIOUS_DAYS} days before ({cls.comparison.previous_n} scored).")
    out.append(Insight(guard(text), "trend",
                       "attention" if cls.kind in ("gradual_down", "increased_variability") else "info",
                       numbers))

    # 2. Good / bad days, last 7 logged days.
    statuses = [e for e in sorted(entries, key=lambda e: e.entry_date) if e.day_status and e.entry_date <= end][-7:]
    if len(statuses) >= 5:
        not_good = sum(1 for e in statuses if e.day_status != "good")
        bad = sum(1 for e in statuses if e.day_status == "bad")
        if not_good >= 4:
            out.append(Insight(
                guard(f"{not_good} of the last {len(statuses)} logged days were marked as bad or mixed "
                      f"({bad} bad)."),
                "days", "attention", {"not_good": not_good, "bad": bad, "n": len(statuses)}))
        elif statuses and all(e.day_status == "good" for e in statuses):
            out.append(Insight(guard(f"All of the last {len(statuses)} logged days were marked as good days."),
                               "days", "info", {"n": len(statuses)}))

    # 3. Per-category movement.
    for key in CATEGORY_KEYS:
        comp = an.period_comparison(an.category_points(entries, key), end)
        if not comp.usable or comp.delta is None:
            continue
        label = CATEGORY_LABELS[key]
        if comp.delta <= -1.0:
            out.append(Insight(
                guard(f"{label} scores have been lower recently: average {comp.recent_mean:.1f} over the last "
                      f"{an.RECENT_DAYS} days compared with {comp.previous_mean:.1f} before."),
                "category", "attention",
                {"key": key, "recent": comp.recent_mean, "previous": comp.previous_mean}))
        elif comp.delta >= 1.0:
            out.append(Insight(
                guard(f"{label} scores have been higher recently: average {comp.recent_mean:.1f} over the last "
                      f"{an.RECENT_DAYS} days compared with {comp.previous_mean:.1f} before."),
                "category", "info",
                {"key": key, "recent": comp.recent_mean, "previous": comp.previous_mean}))
    # A stable category alongside a falling one is worth saying out loud.
    falling = {i.numbers.get("key") for i in out if i.kind == "category" and i.level == "attention"}
    if falling and "hunger" not in falling:
        comp = an.period_comparison(an.category_points(entries, "hunger"), end)
        if comp.usable and comp.delta is not None and abs(comp.delta) < 0.5:
            out.append(Insight(
                guard(f"Appetite scores have remained relatively stable over the same period "
                      f"(average {comp.recent_mean:.1f})."),
                "category", "info", {"key": "hunger", "recent": comp.recent_mean}))

    # 4. Baseline comparison.
    if baseline:
        for key in ("mobility", "hurt", "happiness", "hunger"):
            base_value = getattr(baseline, key)
            if base_value is None:
                continue
            pts = an.category_points(entries, key)
            below, n = an.below_baseline(pts, base_value)
            if n >= 8 and below / n >= 0.7:
                out.append(Insight(
                    guard(f"{CATEGORY_LABELS[key]} has been below {name}'s earlier baseline "
                          f"({base_value}/10, owner estimate) on {below} of the last {n} logged days."),
                    "baseline", "attention", {"key": key, "below": below, "n": n, "baseline": base_value}))
                break  # one baseline sentence is enough

    # 5. Marker completion today and over time.
    if markers:
        done, total = an.markers_today(today_entry.id if today_entry else None, responses, markers)
        if today_entry and today_entry.id in responses:
            out.append(Insight(
                guard(f"{name} did {done} of {total} of their usual good-day behaviors today."),
                "marker", "info", {"done": done, "total": total}))
        recent_rates = an.marker_rates(entries, responses, markers, end - timedelta(days=29), end)
        earlier_rates = an.marker_rates(entries, responses, markers, end - timedelta(days=59), end - timedelta(days=30))
        earlier = {r.marker_id: r for r in earlier_rates}
        for r in recent_rates:
            prev = earlier.get(r.marker_id)
            if r.logged >= 8 and prev and prev.logged >= 8 and r.pct is not None and prev.pct is not None:
                if prev.pct - r.pct >= 25:
                    out.append(Insight(
                        guard(f"“{r.label}” decreased from {prev.pct}% of logged days last month "
                              f"to {r.pct}% this month."),
                        "marker", "attention", {"marker": r.label, "recent": r.pct, "previous": prev.pct}))
                elif r.pct - prev.pct >= 25:
                    out.append(Insight(
                        guard(f"“{r.label}” increased from {prev.pct}% of logged days last month "
                              f"to {r.pct}% this month."),
                        "marker", "info", {"marker": r.label, "recent": r.pct, "previous": prev.pct}))

    # 6. Before/after a treatment event (comfort = Hurt score).
    comfort = an.category_points(entries, "hurt")
    for ev in sorted(events, key=lambda e: e.event_date, reverse=True):
        if ev.type not in TREATMENT_TYPES or ev.event_date > end:
            continue
        eff = an.event_effect(comfort, ev.event_date)
        if eff.usable and eff.delta is not None and abs(eff.delta) >= 1.0:
            direction = "improved" if eff.delta > 0 else "were lower"
            out.append(Insight(
                guard(f"Comfort scores {direction} in the two weeks after “{ev.title}” "
                      f"recorded on {_fmt(ev.event_date)}: average {eff.after_mean:.1f} compared with "
                      f"{eff.before_mean:.1f} before."),
                "event", "info", {"event": ev.title, "before": eff.before_mean, "after": eff.after_mean}))
            break

    # 7. Closing guidance, only when something above deserves attention.
    if any(i.level == "attention" for i in out):
        out.append(Insight(guard(MAX_GUIDANCE), "note", "info"))
    return out


def discussion_points(entries: list[Entry], end: date, name: str, markers=(), responses=None,
                      baseline=None, events=()) -> list[str]:
    """Short bullets for 'Things you may want to discuss with your veterinarian'."""
    items = generate(entries, end, name, markers, responses, baseline, events)
    bullets = [i.text for i in items if i.kind in ("trend", "category", "days", "marker", "baseline", "event")
               and (i.level == "attention" or i.kind in ("event",))]
    return [guard(b) for b in bullets]
