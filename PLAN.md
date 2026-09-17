# Pet Quality-of-Life Tracker — Project Plan

A desktop app for pet owners to log a daily quality-of-life score for a cat or
dog near the end of its life, see patterns over time, and bring a PDF summary to
the vet. Semester-long solo class project. This file is the original plan; see the
Status section at the end.

## Decisions so far

| Question | Decision |
| --- | --- |
| Users | One pet owner, no accounts, no vet login |
| Animals | Several per owner; cats and dogs only for now |
| Scoring | HHHHHMM scale (Hurt, Hunger, Hydration, Hygiene, Happiness, Mobility, More good days than bad), each 0–10, total 0–70 |
| Logging | Once a day, plus notes, weight, appetite, medications, photos |
| Flags | Yes, simple rule-based nudges to "talk to your vet", never a diagnosis |
| Vet sharing | PDF export the owner brings to the appointment |
| Language | Python |
| Offline | Must work with no internet |
| Devices | One device, no sync |

## Recommended tools

- **Python 3.11 or newer** with a virtual environment.
- **Flask** for the app. It runs a tiny local web server, and the UI opens in a
  browser window. Everything stays on the machine, so it works offline.
- **SQLite** through Python's built-in `sqlite3` module for storage. One file,
  no database server, easy to back up. SQLAlchemy is optional and can be added
  later if the raw SQL gets tedious.
- **Jinja2 templates** (bundled with Flask) plus plain HTML and CSS for pages.
- **Chart.js** for the on-screen trend charts, saved into the repo so it loads
  offline (no CDN links).
- **matplotlib** to render the same chart as an image for the PDF.
- **ReportLab** to build the PDF summary.
- **Pillow** to resize uploaded photos.
- **pytest** for tests of scoring, flag rules, and database code.
- **pywebview** (later, optional) to wrap the Flask app in a native desktop
  window so it feels like a real app instead of a browser tab.
- **PyInstaller** (later, optional) to build a double-click executable.

Why not a pure desktop toolkit like Tkinter or PySide? Web pages are easier to
lay out and style, Chart.js gives good charts for free, and the same code can be
hosted online later if you ever want sync. pywebview closes the gap on the
"real app" feel.

## Data model

**animals**

- id, name, species (cat or dog), breed (optional), birth_date (optional),
  photo_path (optional), created_at, archived (bool, for after a pet passes)

**entries** — one per animal per day

- id, animal_id, date (unique with animal_id)
- hurt, hunger, hydration, hygiene, happiness, mobility, good_days — each 0–10
- total — computed, 0–70
- weight (optional, with unit)
- appetite (none / low / normal / high)
- notes (free text)
- created_at, updated_at

**medications** — a list per animal

- id, animal_id, name, dose, schedule, active (bool)

**entry_medications** — which meds were given on a given day

- entry_id, medication_id, given (bool)

**photos**

- id, entry_id, file_path, caption

Photos live in a `data/photos/` folder on disk; the database only stores the
path.

## Flag rules (first draft, adjust with a vet's input)

Flags appear as a gentle banner on the dashboard and in the PDF. Wording is
always "consider talking with your vet", never a verdict.

1. Total score below 35 on 3 or more consecutive days.
2. Any single category at 3 or below for 3 consecutive days.
3. Weight down 10% or more compared with 30 days earlier.
4. Appetite logged as "none" for 2 consecutive days.
5. No entry logged for 3 days (a reminder, not a health flag).

## Features by milestone

**M1 — Skeleton (weeks 1–2)**
- Project setup, virtual environment, Flask "hello", SQLite schema created on
  first run, pytest running.

**M2 — Animals (weeks 3–4)**
- Add, edit, archive an animal. Upload a profile photo. Pick an animal to work
  with.

**M3 — Daily entry (weeks 5–6)**
- Daily form with the seven sliders, weight, appetite, notes, medication
  checklist, photo upload. Editing today's entry replaces it. Tests for scoring.

**M4 — History and charts (weeks 7–8)**
- Entry list with filters by date range. Line chart of total score over time,
  with each category toggleable. Weight chart.

**M5 — Flags (week 9)**
- Flag rules implemented as pure functions with tests. Dashboard banner.

**M6 — PDF export (weeks 10–11)**
- Choose a date range, generate a PDF: animal details, score chart, weight
  chart, table of daily totals, active flags, notes, medication list.

**M7 — Polish and packaging (weeks 12–14)**
- Better styling, empty states, confirmation dialogs. Backup and restore of the
  data folder. Optional pywebview window and PyInstaller build. README with
  screenshots and a short write-up of design decisions for the class.

## File layout

See the "Project layout" section of README.md for the layout as built. It
follows this plan with two additions: entry data access lives in
`app/entries.py` rather than `models.py`, and backup/restore got its own
`app/backup.py` and settings page.

## Definition of done for the semester

- A user can add a cat or dog, log a daily entry for it, and see a chart of the
  last 30 days with no internet connection.
- The app flags the patterns listed above and explains them in plain language.
- The user can export a PDF for any date range and open it in a normal PDF
  reader.
- Tests pass for scoring, flags, and database code.
- README explains how to install and run it.

## Risks and how to handle them

- **Medical wording.** The app must not tell anyone when to euthanize. Keep all
  flag text as "consider discussing with your vet" and cite the HHHHHMM scale as
  the source.
- **Scope creep.** Reminders, cloud sync, and mobile are out for this semester.
  Write them in a "later" list instead of building them.
- **Data loss.** Everything is in one folder; add a "back up my data" button
  early (M4 or M5) that zips the folder.
- **Packaging pain.** PyInstaller and pywebview are the last milestone so the
  core app is graded even if packaging is rough.

## Status

All seven milestones were built, and the app was then reworked into a second
version around good/bad days, personalized behaviors, a baseline, honest trend
analysis, and a one-page vet summary. See README.md and docs/ARCHITECTURE.md.
