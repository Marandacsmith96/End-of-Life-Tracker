"""Seed a realistic 90-day demo pet so the trend view means something immediately.

    python scripts/seed_demo.py            # adds Maggie
    python scripts/seed_demo.py --reset    # wipes the data folder first

Maggie is a 13-year-old Golden Retriever. The data shows a relatively stable
first month, gradual mobility decline with appetite mostly maintained, more
bad days over time, a pain-medication change around day 55 with a temporary
improvement, then a slower decline. It includes noise, occasional good days in
declining periods, and missing entries. Nothing here is real.
"""
import argparse
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import baseline, caregiver, create_app, entries, events, markers, models  # noqa: E402
from app.scoring import CATEGORY_KEYS  # noqa: E402

NOTES = {
    "good": [None, None, "Carried her toy around the garden.", "Ate everything and asked for more.",
             "Long sniff walk to the end of the street."],
    "mixed": [None, "Slow getting up this morning, brighter by afternoon.", "Ate breakfast, skipped dinner.",
              "Restless overnight.", "Wanted to walk but turned back early."],
    "bad": [None, "Didn't want to get up. Carried her outside.", "Panting in the evening.",
            "Skipped both meals.", "Slipped on the kitchen floor twice."],
}
MARKERS = ["Greets me when I come home", "Finishes dinner", "Gets onto the couch herself", "Wants to go for a short walk"]


def clamp(x, lo=0, hi=10):
    return max(lo, min(hi, x))


def seed(reset: bool) -> None:
    app = create_app()
    if reset:
        data_dir = Path(app.config["DATA_DIR"])
        if data_dir.exists():
            shutil.rmtree(data_dir)
        app = create_app()
    rng = random.Random(13)
    today = date.today()
    with app.app_context():
        animal_id = models.create_animal(
            "Maggie", "dog", "Golden Retriever", today - timedelta(days=365 * 13 + 61), "female",
            "Osteoarthritis (hips, elbows); early kidney disease")
        marker_ids = [markers.create_marker(animal_id, m) for m in MARKERS]
        baseline.save_baseline(animal_id, today - timedelta(days=182),
                               {"hurt": 8, "hunger": 9, "hydration": 9, "hygiene": 9, "happiness": 9,
                                "mobility": 8, "good_days": 9}, "mostly_good", "most_days",
                               "Still doing the full loop of the park most days.")
        gaba = entries.create_medication(animal_id, "Gabapentin", "100 mg", "twice a day", today - timedelta(days=120))
        carp = entries.create_medication(animal_id, "Carprofen", "75 mg", "with breakfast", today - timedelta(days=200))
        d0 = today - timedelta(days=89)
        med_change = d0 + timedelta(days=55)
        events.create_event(animal_id, d0 + timedelta(days=12), "vet_visit", "Check-up and bloodwork",
                            "Kidney values slightly worse. Discussed pain control.")
        events.create_event(animal_id, med_change, "dose_change", "Gabapentin increased to 200 mg",
                            "Twice a day. Vet suggested re-checking in three weeks.")
        events.create_event(animal_id, med_change, "vet_visit", "Pain review appointment", None)
        events.create_event(animal_id, d0 + timedelta(days=71), "active_day", "Family visit, lots of attention", None)

        # Latent "true" trajectory for mobility and comfort, 0-10.
        for i in range(90):
            day = d0 + timedelta(days=i)
            if rng.random() < (0.06 if i < 40 else 0.12):
                continue  # missed day
            t = i / 89
            # mobility: stable ~8 for a month, then declines; bump after med change; slower decline after
            mobility = 8.0 - 3.2 * max(0, (i - 28) / 61)
            comfort = 7.8 - 2.6 * max(0, (i - 28) / 61)
            if i >= 55:
                boost = 1.6 * max(0, 1 - (i - 55) / 24)
                comfort += boost
                mobility += boost * 0.6
            happiness = 8.2 - 1.8 * max(0, (i - 35) / 54)
            hunger = 8.4 - 0.9 * t
            hydration = 8.0 - 0.5 * t
            hygiene = 8.6 - 1.4 * max(0, (i - 60) / 29)
            good_days = 8.5 - 3.0 * max(0, (i - 30) / 59) + (0.8 if 55 <= i < 75 else 0)
            noise = lambda s=1.1: rng.gauss(0, s)  # noqa: E731
            scores = {
                "hurt": clamp(round(comfort + noise())), "hunger": clamp(round(hunger + noise(0.9))),
                "hydration": clamp(round(hydration + noise(0.8))), "hygiene": clamp(round(hygiene + noise(0.7))),
                "happiness": clamp(round(happiness + noise())), "mobility": clamp(round(mobility + noise())),
                "good_days": clamp(round(good_days + noise(0.9))),
            }
            # An occasional clearly good day even late on, and the odd bad day early.
            if rng.random() < 0.08:
                scores = {k: clamp(v + 2) for k, v in scores.items()}
            elif rng.random() < 0.05:
                scores = {k: clamp(v - 2) for k, v in scores.items()}
            mean = sum(scores.values()) / 7
            if mean >= 7.2:
                status = "good"
            elif mean <= 5.4:
                status = "bad"
            else:
                status = "mixed" if rng.random() < 0.7 else ("good" if rng.random() < 0.5 else "bad")
            include_scores = rng.random() > (0.12 if i < 50 else 0.2)  # quick check-ins sometimes
            weight = round(30.5 - 2.2 * t + rng.gauss(0, 0.15), 1) if rng.random() < 0.3 else None
            appetite = rng.choices(["normal", "low", "none", "high"],
                                   weights=[0.75 - 0.3 * t, 0.2 + 0.25 * t, 0.02 + 0.05 * t, 0.03])[0]
            entry_id = entries.save_entry(
                animal_id, day, status, scores if include_scores else {}, weight, "kg" if weight else None,
                appetite if include_scores else None, rng.choice(NOTES[status]))
            # Markers: each declines at its own rate.
            probs = {
                marker_ids[0]: 0.92 - 0.45 * max(0, (i - 40) / 49),           # greets: holds, then fades
                marker_ids[1]: 0.90 - 0.30 * t,                                # dinner: mostly maintained
                marker_ids[2]: 0.85 - 0.7 * max(0, (i - 25) / 64),             # couch: falls fastest
                marker_ids[3]: 0.88 - 0.55 * max(0, (i - 30) / 59),            # walk: falls steadily
            }
            if 55 <= i < 72:
                probs[marker_ids[2]] += 0.2
                probs[marker_ids[3]] += 0.15
            done = {m for m, p in probs.items() if rng.random() < clamp(p, 0, 1)}
            markers.set_responses(entry_id, done, set(marker_ids))
            given = {gaba} if rng.random() < 0.93 else set()
            if rng.random() < 0.85:
                given.add(carp)
            entries.set_entry_medications(entry_id, given, {gaba, carp})
        for weeks_ago, status, note in ((8, "okay", None), (5, "harder", "Not sleeping well; up with her twice a night."),
                                        (2, "exhausted", None)):
            caregiver.save_checkin(animal_id, today - timedelta(days=7 * weeks_ago), status, note)
    print("Added Maggie with about 90 days of demo entries. Start the app and open Maggie.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reset", action="store_true", help="delete existing data first")
    seed(parser.parse_args().reset)
