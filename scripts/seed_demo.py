"""Seed realistic demo pets so the trend view means something immediately.

    python scripts/seed_demo.py                 # adds Maggie, Bruno, and Juniper
    python scripts/seed_demo.py --reset         # wipes the data folder first
    python scripts/seed_demo.py --pet maggie    # just one of them

Maggie is a 13-year-old Golden Retriever: a relatively stable first month,
gradual mobility decline with appetite mostly maintained, more bad days over
time, a pain-medication change around day 55 with a temporary improvement,
then a slower decline.

Bruno is a 14-year-old Labrador: a steady decline over about two months with
no recovery, mobility falling fastest, appetite holding until late, good days
becoming rare.

Juniper is a 12-year-old cat who starts low after a diagnosis of an overactive
thyroid and dental disease, dips again around a dental procedure, then climbs
steadily as treatment takes hold and levels off near her old self.

All three include noise, the odd off day, and missing entries. Nothing here is
real.
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


def seed_maggie(rng: random.Random, today: date) -> None:
    if True:  # noqa: keeps the original block indentation
        animal_id = models.create_animal(
            "Maggie", "dog", "Golden Retriever", today - timedelta(days=365 * 13 + 61), "female",
            "Osteoarthritis (hips, elbows); early kidney disease", demo=True)
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


BRUNO_MARKERS = ["Meets me at the gate", "Eats breakfast", "Climbs the porch steps", "Carries his ball around"]
BRUNO_NOTES = {
    "good": [None, "Brighter today. Sat in the sun and watched the road.", "Ate all of breakfast."],
    "mixed": [None, "Needed help up from the kitchen floor.", "Ate half of dinner.", "Panting after the short walk."],
    "bad": [None, "Wouldn't get up until noon.", "Refused breakfast and dinner.", "Slipped on the steps; carried him in.",
            "Restless all night, panting.", "Didn't lift his head when I came home."],
}


def seed_bruno(rng: random.Random, today: date) -> None:
    """A steady decline with no recovery, over about 60 days."""
    animal_id = models.create_animal(
        "Bruno", "dog", "Labrador Retriever", today - timedelta(days=365 * 14 + 120), "male",
        "Severe osteoarthritis; degenerative myelopathy suspected; heart murmur", demo=True)
    marker_ids = [markers.create_marker(animal_id, m) for m in BRUNO_MARKERS]
    baseline.save_baseline(animal_id, today - timedelta(days=182),
                           {"hurt": 8, "hunger": 9, "hydration": 9, "hygiene": 9, "happiness": 9,
                            "mobility": 7, "good_days": 9}, "mostly_good", "most_days",
                           "Slower on the stairs but still keen on everything.")
    melox = entries.create_medication(animal_id, "Meloxicam", "1.5 mg", "once a day with food", today - timedelta(days=150))
    gaba = entries.create_medication(animal_id, "Gabapentin", "300 mg", "three times a day", today - timedelta(days=30))
    d0 = today - timedelta(days=59)
    events.create_event(animal_id, d0 + timedelta(days=8), "vet_visit", "Check-up and bloodwork",
                        "Murmur louder than last time. Discussed mobility and pain options.")
    events.create_event(animal_id, d0 + timedelta(days=30), "pain_medication_started", "Started gabapentin 300 mg",
                        "Three times a day. Little change noticed so far.")
    events.create_event(animal_id, d0 + timedelta(days=46), "other", "Stopped managing the porch steps", None)
    events.create_event(animal_id, d0 + timedelta(days=55), "vet_visit", "Recheck", "Talked through what the next weeks might look like.")

    weight = 33.8
    for i in range(60):
        day = d0 + timedelta(days=i)
        if rng.random() < 0.1:
            continue
        t = i / 59
        noise = lambda s=1.0: rng.gauss(0, s)  # noqa: E731
        mobility = 7.5 - 5.2 * t
        comfort = 7.6 - 3.6 * t
        happiness = 8.0 - 3.6 * t
        hunger = 8.2 - 1.2 * t - (2.6 * max(0, (i - 40) / 19))    # holds, then drops late
        hydration = 8.0 - 2.0 * t
        hygiene = 8.6 - 1.0 * t - (2.8 * max(0, (i - 44) / 15))
        good_days = 8.0 - 5.0 * t
        scores = {
            "hurt": clamp(round(comfort + noise())), "hunger": clamp(round(hunger + noise(0.8))),
            "hydration": clamp(round(hydration + noise(0.7))), "hygiene": clamp(round(hygiene + noise(0.7))),
            "happiness": clamp(round(happiness + noise())), "mobility": clamp(round(mobility + noise(0.9))),
            "good_days": clamp(round(good_days + noise(0.8))),
        }
        if rng.random() < 0.07:   # the occasional clearly better day, even late on
            scores = {k: clamp(v + 2) for k, v in scores.items()}
        mean = sum(scores.values()) / 7
        if mean >= 7.0:
            status = "good"
        elif mean <= 5.2:
            status = "bad"
        else:
            status = "mixed" if rng.random() < 0.65 else ("bad" if rng.random() < 0.6 else "good")
        include_scores = rng.random() > 0.15
        weight = max(28.5, weight - rng.uniform(0.02, 0.12))
        log_weight = round(weight, 1) if rng.random() < 0.3 else None
        appetite = rng.choices(["normal", "low", "none"], weights=[0.8 - 0.7 * t, 0.15 + 0.45 * t, 0.05 + 0.25 * t])[0]
        entry_id = entries.save_entry(
            animal_id, day, status, scores if include_scores else {}, log_weight, "kg" if log_weight else None,
            appetite if include_scores else None, rng.choice(BRUNO_NOTES[status]))
        probs = {
            marker_ids[0]: 0.9 - 0.75 * t,                      # gate: steady fade
            marker_ids[1]: 0.92 - 0.2 * t - 0.6 * max(0, (i - 40) / 19),  # breakfast: holds then drops
            marker_ids[2]: 0.85 - 0.85 * min(1, i / 46),        # steps: gone by day 46
            marker_ids[3]: 0.8 - 0.8 * t,                       # ball: steady fade
        }
        done = {m for m, p in probs.items() if rng.random() < clamp(p, 0, 1)}
        markers.set_responses(entry_id, done, set(marker_ids))
        given = {melox} if rng.random() < 0.95 else set()
        if i >= 30 and rng.random() < 0.9:
            given.add(gaba)
        entries.set_entry_medications(entry_id, given, {melox, gaba})
    for weeks_ago, status, note in ((7, "okay", None), (4, "harder", None),
                                    (2, "exhausted", "Carrying him outside four times a day."),
                                    (0, "overwhelmed", "I don't know how to tell if he's still enjoying anything.")):
        caregiver.save_checkin(animal_id, today - timedelta(days=7 * weeks_ago + 1), status, note)


JUNIPER_MARKERS = ["Comes to greet me", "Finishes dinner", "Jumps onto the windowsill", "Grooms herself"]
JUNIPER_NOTES = {
    "good": [None, "Chased the string toy for a whole minute.", "Sat in the sun on the windowsill all afternoon.",
             "Asked for breakfast before I was up."],
    "mixed": [None, "Ate slowly but finished eventually.", "Quiet day, but came for a cuddle.", "Only groomed her face."],
    "bad": [None, "Hid under the bed most of the day.", "Refused food; drooling a little.", "Coat looks unkempt; didn't groom.",
            "Vomited once in the morning."],
}


def seed_juniper(rng: random.Random, today: date) -> None:
    """Starts low, improves with treatment, levels off near her old self."""
    animal_id = models.create_animal(
        "Juniper", "cat", "Domestic shorthair", today - timedelta(days=365 * 12 + 200), "female",
        "Hyperthyroidism (diagnosed this summer); dental disease", demo=True)
    marker_ids = [markers.create_marker(animal_id, m) for m in JUNIPER_MARKERS]
    baseline.save_baseline(animal_id, today - timedelta(days=182),
                           {"hurt": 8, "hunger": 8, "hydration": 8, "hygiene": 9, "happiness": 8,
                            "mobility": 9, "good_days": 8}, "mostly_good", "most_days",
                           "Normal for her before the weight loss started.")
    methimazole = entries.create_medication(animal_id, "Methimazole", "2.5 mg", "twice a day", today - timedelta(days=58))
    pain = entries.create_medication(animal_id, "Buprenorphine", "0.1 ml", "twice a day for 5 days", today - timedelta(days=47))
    entries.set_medication_active(pain, False, on=today - timedelta(days=42))
    d0 = today - timedelta(days=59)
    events.create_event(animal_id, d0 + timedelta(days=1), "vet_visit", "Bloodwork: overactive thyroid confirmed",
                        "Had lost a lot of weight. Started methimazole.")
    events.create_event(animal_id, d0 + timedelta(days=1), "new_medication", "Started methimazole 2.5 mg", None)
    events.create_event(animal_id, d0 + timedelta(days=12), "procedure", "Dental: three teeth removed",
                        "Home the same evening, sore for a few days.")
    events.create_event(animal_id, d0 + timedelta(days=35), "vet_visit", "Recheck bloodwork",
                        "Thyroid levels back in range. Gained weight.")

    weight = 3.1
    for i in range(60):
        day = d0 + timedelta(days=i)
        if rng.random() < 0.08:
            continue
        t = i / 59
        noise = lambda s=0.9: rng.gauss(0, s)  # noqa: E731
        # Recovery curve: a slow start, a dental dip, then steady gains that continue to the end.
        recovery = 0.6 * t + 0.4 * t ** 2   # slow at first, still climbing at the end
        dental_dip = 2.2 * max(0, 1 - abs(i - 13) / 4) if 10 <= i <= 17 else 0
        comfort = 4.0 + 4.0 * recovery - dental_dip
        hunger = 3.5 + 4.5 * recovery - dental_dip * 1.2
        hydration = 5.0 + 3.0 * recovery
        hygiene = 3.8 + 4.6 * recovery - dental_dip * 0.5
        happiness = 3.5 + 4.6 * recovery - dental_dip
        mobility = 6.0 + 2.5 * recovery - dental_dip * 0.4
        good_days = 3.0 + 5.2 * recovery - dental_dip
        scores = {
            "hurt": clamp(round(comfort + noise())), "hunger": clamp(round(hunger + noise())),
            "hydration": clamp(round(hydration + noise(0.7))), "hygiene": clamp(round(hygiene + noise(0.8))),
            "happiness": clamp(round(happiness + noise())), "mobility": clamp(round(mobility + noise(0.7))),
            "good_days": clamp(round(good_days + noise(0.8))),
        }
        if rng.random() < 0.06:   # an off day even while improving
            scores = {k: clamp(v - 2) for k, v in scores.items()}
        mean = sum(scores.values()) / 7
        if mean >= 6.8:
            status = "good"
        elif mean <= 4.8:
            status = "bad"
        else:
            status = "mixed" if rng.random() < 0.7 else ("good" if rng.random() < 0.5 else "bad")
        include_scores = rng.random() > 0.15
        weight = min(4.3, weight + rng.uniform(0.0, 0.05) * (1 if i > 14 else 0.2))
        log_weight = round(weight, 2) if rng.random() < 0.3 else None
        appetite = rng.choices(["none", "low", "normal", "high"],
                               weights=[0.3 - 0.28 * recovery, 0.5 - 0.35 * recovery, 0.2 + 0.55 * recovery, 0.05 * recovery])[0]
        entry_id = entries.save_entry(
            animal_id, day, status, scores if include_scores else {}, log_weight, "kg" if log_weight else None,
            appetite if include_scores else None, rng.choice(JUNIPER_NOTES[status]))
        probs = {
            marker_ids[0]: 0.2 + 0.7 * recovery,                      # greets: returns steadily
            marker_ids[1]: 0.15 + 0.75 * recovery - (0.4 if 10 <= i <= 16 else 0),  # dinner: dips with the dental
            marker_ids[2]: 0.3 + 0.55 * recovery,                     # windowsill
            marker_ids[3]: 0.1 + 0.8 * recovery,                      # grooming: the clearest sign she feels better
        }
        done = {m for m, pr in probs.items() if rng.random() < clamp(pr, 0, 1)}
        markers.set_responses(entry_id, done, set(marker_ids))
        given = {methimazole} if rng.random() < 0.95 else set()
        if 12 <= i <= 17:
            given.add(pain)
        entries.set_entry_medications(entry_id, given, {methimazole, pain})
    for weeks_ago, status, note in ((7, "overwhelmed", "Didn't know if she'd recover."), (4, "harder", None),
                                    (1, "okay", "Feels like I have her back.")):
        caregiver.save_checkin(animal_id, today - timedelta(days=7 * weeks_ago + 2), status, note)


# What the "Try it with example pets" section shows. Order matters.
EXAMPLES = (
    {"key": "maggie", "name": "Maggie", "species": "dog", "seed": 13, "fn": seed_maggie,
     "story": "13-year-old Golden Retriever, 90 days. Mostly steady, with mobility slipping and a "
              "medication change that helped for a while."},
    {"key": "bruno", "name": "Bruno", "species": "dog", "seed": 29, "fn": seed_bruno,
     "story": "14-year-old Labrador, 60 days. A steady decline with no recovery; what the trend "
              "pages look like when things are getting worse."},
    {"key": "juniper", "name": "Juniper", "species": "cat", "seed": 41, "fn": seed_juniper,
     "story": "12-year-old cat, 60 days. Starts low after a thyroid diagnosis and dental surgery, "
              "then improves as treatment takes hold."},
)


def add_examples(today: date | None = None) -> list[str]:
    """Seed any example pet that is not already present. Needs an app context.
    Returns the names that were added."""
    today = today or date.today()
    present = {a.name for a in models.list_demo_animals()}
    added = []
    for ex in EXAMPLES:
        if ex["name"] not in present:
            ex["fn"](random.Random(ex["seed"]), today)
            added.append(ex["name"])
    return added


def remove_examples() -> int:
    """Delete every example pet and all its data. Needs an app context."""
    demo = models.list_demo_animals()
    for animal in demo:
        models.delete_animal(animal.id)
    return len(demo)


def seed(reset: bool, pet: str = "all") -> None:
    app = create_app()
    if reset:
        data_dir = Path(app.config["DATA_DIR"])
        if data_dir.exists():
            shutil.rmtree(data_dir)
        app = create_app()
    today = date.today()
    with app.app_context():
        if pet in ("maggie", "all"):
            seed_maggie(random.Random(13), today)
        if pet in ("bruno", "all"):
            seed_bruno(random.Random(29), today)
        if pet in ("juniper", "all"):
            seed_juniper(random.Random(41), today)
    names = {"maggie": "Maggie", "bruno": "Bruno", "juniper": "Juniper", "all": "Maggie, Bruno, and Juniper"}[pet]
    print(f"Added {names} with demo entries. Start the app and choose a pet.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reset", action="store_true", help="delete existing data first")
    parser.add_argument("--pet", choices=("maggie", "bruno", "juniper", "all"), default="all", help="which demo pet to add")
    args = parser.parse_args()
    seed(args.reset, args.pet)
