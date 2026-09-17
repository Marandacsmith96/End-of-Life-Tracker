# Architecture

A local-first web app: Python, Flask, SQLite, Jinja templates, a little vanilla
JavaScript, Chart.js for on-screen charts, matplotlib and ReportLab for the PDF.
It runs on the owner's own computer and stores everything in one folder.

## Why this stack

The brief suggested Next.js, TypeScript, PostgreSQL, and Prisma. This project
had already been built in Python by choice, so the same product was built on
the stack in hand. The trade-offs are documented honestly:

- **Kept:** every product requirement, the data model (as SQLite tables with
  foreign keys and indexes), modular analytics with unit tests, a safety layer,
  the one-page PDF, mobile-first layout, and a 90-day demo.
- **Simplified:** there is no account system. The app is single-user and local,
  so "User" from the suggested schema is implicit. Notifications are in-app
  notes only, because a local web app cannot push to a phone.
- **Different:** validation is done in the route functions rather than with a
  schema library; server-rendered pages replace React components; type hints
  and tests stand in for TypeScript strict mode.

## Layout

```
run.py, desktop.py          launchers (browser tab, or pywebview window)
app/
  __init__.py               app factory, current-pet loading, check-in prompt
  db.py                     connection, schema.sql, versioned migrations
  schema.sql                the tables (see below)
  models.py                 animals
  entries.py                daily check-ins, medications, photos
  markers.py                personalized good-day behaviors and responses
  baseline.py               owner-estimated baseline
  events.py                 timeline events
  caregiver.py              weekly caregiver check-ins (kept separate)
  scoring.py                HHHHHMM scale: labels, guidance, anchors, questions
  analytics.py              smoothing, sufficiency, comparisons, classification
  insights.py               deterministic observations with their numbers
  safety.py                 forbidden-statement guard and fixed copy
  charts.py                 series for Chart.js and the PDF
  pdf.py, pdf_charts.py     the vet summary
  backup.py, photos.py      zip backup/restore, image resizing
  routes/                   dashboard, animals, entries, markers, baseline,
                            trends, events, caregiver, export, settings
  templates/, static/       pages, stylesheet, scripts, vendored Chart.js and font
scripts/seed_demo.py        Maggie, 90 days
tests/                      pytest suite
```

## Schema (SQLite, version 2)

| Table | Purpose |
| --- | --- |
| `animals` | name, species (cat/dog), breed, sex, birth date, photo, diagnoses (owner's words), status (active/archived/passed), passed_date, reminder |
| `entries` | one row per animal per day: `day_status` (good/bad/mixed), seven optional 0–10 scores, weight, appetite, note |
| `personal_markers` | 3–5 behaviors per animal; deactivated rather than deleted so history stays |
| `marker_responses` | entry × marker → completed |
| `baselines` | one per animal: approximate date, estimated scores, good-day pattern, behavior frequency |
| `medications` | name, dose, schedule, start/end date, active |
| `entry_medications` | which medications were given on which day |
| `photos` | photos attached to an entry |
| `pet_events` | dated events with a type and title |
| `caregiver_checkins` | date, status (okay/harder/exhausted/overwhelmed), note |

Foreign keys cascade on delete; `PRAGMA user_version` tracks the schema
version and `db.py` upgrades older files in place (the first release had
non-null scores and an `archived` flag; the migration rebuilds `entries` and
maps `archived` to `status`).

## Trend and smoothing

All of this lives in `app/analytics.py` and is pure Python over lists, so it
can be unit-tested and replaced later.

1. **Daily overall score** is the mean of whichever HHHHHMM categories were
   scored that day (0–10). Days with no scores contribute nothing.
2. **Smoothing** is a *time-windowed trailing mean*: for each logged day, the
   mean of all logged values in the previous 7 calendar days. If fewer than 3
   observations fall in that window the value is `None`, so the chart shows a
   gap rather than a confident line. Missing days are never interpolated. An
   EWMA that decays by elapsed time is included as an alternative and tested,
   but the windowed mean is what the UI shows because it is easier to explain.
3. **Sufficiency**: the last 30 days need at least 8 scored days spanning at
   least 10 days to be "adequate"; otherwise the page says the data is limited
   and the smoothed line is drawn lighter.
4. **Comparison**: the mean of the last 7 days is compared with the mean of the
   21 days before that. Each side needs a minimum number of observations (4
   and 6).
5. **Classification**, in order:
   - `insufficient_data` if sufficiency or comparison minimums fail;
   - `gradual_down` / `gradual_up` if the means differ by at least 0.75 **and**
     at least 75% of the recent observations sit on that side of the previous
     mean (sustained, consistent evidence);
   - `temporary_fluctuation` if exactly one recent day deviates by 2.5 or more
     while the rest are steady (a single bad day is never a trend);
   - `increased_variability` if the recent standard deviation is at least 1.4
     and at least 1.4× the previous period's;
   - otherwise `stable`.
6. User-facing wording for each class is fixed text in `insights.py`, all of
   it cautious ("Scores have generally trended lower over the past few
   weeks."). The same machinery runs per category, for the baseline
   comparison ("below the owner-estimated baseline on 9 of the last 12 logged
   days"), for behavior completion rates (this month vs last month), and for
   before/after a treatment event (14 days each side of a medication change,
   at least 4 observations on each side).

Every insight carries its numbers so the owner can see where it came from.
Nothing here is machine learning, and the product never calls it AI.

## Safety rules

`app/safety.py` holds the forbidden patterns (for example "it's time",
"euthan", "put down", "should", "recommend", "is dying", "is suffering",
"acceptable quality of life") and a `guard()` that raises if generated text
matches. The insight engine, the vet-visit page, and the PDF pass every
generated sentence through it. Tests assert that all sample outputs are clean
and that each prohibited example statement is caught. The strongest guidance
the app can give is "You may want to share these changes with your
veterinarian." The fixed disclaimer is the only text that names euthanasia,
in order to say the app never recommends it.

Tone rules are enforced by tests too: no streaks, badges, "oops", or guilt
copy on the pages; the missed-day state reads "No check-in recorded today".

## Known limitations

- Single user, single device. Sync is by copying the data folder or a backup.
- Reminders are in-app only; there are no push notifications.
- The trend classifier is deliberately simple. It has no change-point
  detection and no confidence intervals beyond the "limited data" state.
- The behavior list is capped at five to keep check-ins short.
- Photos are stored on disk and are not in the PDF.
- The one-page PDF truncates long event and medication lists to eight rows;
  the optional appendix has everything.
- Not a medical device; the flag thresholds have not been reviewed by a vet.

## Suggested next steps for a real launch

1. Ask two or three veterinarians to review the wording, the guidance
   thresholds, and the PDF layout.
2. Add accounts and a hosted database so a household can share one pet and a
   clinic can be invited to view a summary (the schema already keys everything
   by animal).
3. Replace the windowed-mean classifier with a tested change-point method
   behind the same `classify()` interface, and show a confidence band.
4. Real reminders through a mobile wrapper, still defaulting to off.
5. Accessibility audit with a screen reader, and an offline-capable PWA build.
6. Video-based gait or grimace scoring as an *optional supplemental*
   observation, never a replacement for a vet.
