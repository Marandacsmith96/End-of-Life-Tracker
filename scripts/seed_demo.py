"""Fill the database with a realistic sample pet for demos and screenshots.

Usage (from the project root, with the virtual environment active):

    python scripts/seed_demo.py            # adds "Biscuit" with 45 days of entries
    python scripts/seed_demo.py --reset    # wipes the data folder first

Nothing here is medical data; the numbers are invented to show a gentle
decline with good and bad days, the kind of pattern the charts should reveal.
"""
import argparse
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, entries, models  # noqa: E402
from app.scoring import CATEGORY_KEYS  # noqa: E402

NOTES = [
    None, None, None,
    "Ate breakfast on her own for the first time in a few days.",
    "Slow getting up from her bed this morning.",
    "Short walk to the mailbox, tail wagging.",
    "Skipped dinner. Drank plenty of water.",
    "Slept most of the afternoon in the sun.",
    "Seemed sore on the stairs; carried her up.",
    "Good day. Played with the rope toy for a minute.",
    "Restless overnight, panting a little.",
]


def seed(reset: bool) -> None:
    app = create_app()
    if reset:
        data_dir = Path(app.config["DATA_DIR"])
        if data_dir.exists():
            shutil.rmtree(data_dir)
        app = create_app()

    rng = random.Random(7)
    with app.app_context():
        animal_id = models.create_animal(
            "Biscuit", "dog", "Beagle mix", date.today() - timedelta(days=365 * 14 + 40)
        )
        gaba = entries.create_medication(animal_id, "Gabapentin", "100 mg", "twice a day")
        carp = entries.create_medication(animal_id, "Carprofen", "25 mg", "with breakfast")

        today = date.today()
        days = 45
        weight = 11.8
        for i in range(days, -1, -1):
            day = today - timedelta(days=i)
            if rng.random() < 0.08:  # occasional missed day
                continue
            progress = (days - i) / days  # 0 at start, 1 today
            base = 8.2 - 3.0 * progress + rng.uniform(-0.8, 0.8)
            scores = {}
            for key in CATEGORY_KEYS:
                bump = {"mobility": -1.2 * progress, "hunger": -0.6 * progress,
                        "happiness": 0.3}.get(key, 0)
                scores[key] = max(0, min(10, round(base + bump + rng.uniform(-1.2, 1.2))))
            weight = max(8.0, weight - rng.uniform(0.0, 0.06))
            log_weight = round(weight, 1) if rng.random() < 0.5 else None
            appetite = rng.choices(
                ["normal", "low", "none", "high"],
                weights=[0.6 - 0.4 * progress, 0.3 + 0.3 * progress, 0.05 + 0.1 * progress, 0.05],
            )[0]
            entry_id = entries.save_entry(
                animal_id, day, scores,
                log_weight, "kg" if log_weight else None,
                appetite, rng.choice(NOTES),
            )
            given = {gaba} if rng.random() < 0.9 else set()
            if rng.random() < 0.7:
                given.add(carp)
            entries.set_entry_medications(entry_id, given, {gaba, carp})
    print("Added Biscuit with sample entries. Start the app and pick Biscuit on the dashboard.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reset", action="store_true", help="delete existing data first")
    seed(parser.parse_args().reset)
