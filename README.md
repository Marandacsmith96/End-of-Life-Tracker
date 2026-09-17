# Pet Quality-of-Life Tracker

A small offline app for pet owners to log a daily quality-of-life score for a
cat or dog near the end of its life, see trends over time, and export a PDF
summary to bring to the vet. Built in Python with Flask and SQLite.

See [PLAN.md](PLAN.md) for the full design, milestones, and data model.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python run.py
```

Open <http://127.0.0.1:5000> in a browser. The database and photo folder are
created automatically under `data/` on first start. That folder is your data;
back it up and never commit it.

## Test

```bash
pytest
```

## Status

- [x] Milestone 1: project skeleton, database schema, tests
- [x] Milestone 2: animals (add, edit, archive, photo, pick current pet)
- [x] Milestone 3: daily entry (scores, weight, appetite, notes, medications, photos)
- [x] Milestone 4: history and charts
- [x] Milestone 5: flags (patterns to watch)
- [ ] Milestone 6: PDF export
- [ ] Milestone 7: polish and packaging
