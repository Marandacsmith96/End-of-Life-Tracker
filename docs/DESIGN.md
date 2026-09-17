# Design notes

See ARCHITECTURE.md for the technical summary. This file is the narrative.

Written for the class write-up: why the app is shaped the way it is, what was
hard, and what I would do next.

## The problem

When a pet is near the end of its life, owners are asked by their vet "how is
she doing?" and have to answer from memory, on a day that is often emotional.
Good days and bad days blur together. The HHHHHMM scale (Villalobos) gives a
structured way to score seven aspects of quality of life from 0 to 10, but it
is usually handed out as a paper worksheet that gets filled in once.

The app turns that worksheet into a one-minute daily habit and then does the
one thing paper cannot: show the pattern over weeks.

## Who it is for

One owner, on one computer, tracking one or a few cats or dogs. No vet login,
no accounts, no cloud. The owner brings a PDF to the appointment. This kept the
scope small enough to finish in a semester and meant no personal data ever
leaves the machine.

## Key decisions

**A local web app in Python, not a mobile app or a desktop toolkit.** Flask
serves pages to the owner's own browser from a server running on their
machine. This gave me HTML and CSS for layout, Chart.js for good charts with
almost no code, and Python for everything else. A desktop window is available
through pywebview and a double-click build through PyInstaller, but they are
optional layers on top; the core app is graded on its own.

**SQLite with hand-written SQL.** One file, no server, and the database itself
enforces the rules that matter: species must be cat or dog, scores must be 0
to 10, one entry per pet per day, and deleting a pet removes its entries. The
tests check those constraints directly. An ORM would have hidden this for no
real gain at this size.

**The scale is data, not code.** `scoring.py` holds the seven categories as a
tuple of (key, label, help text). The form, the history table, the small
charts, the PDF, and the flag rules all iterate over it. Adding or renaming a
category is a one-line change.

**Flags are pure functions.** `flags.py` takes a list of entries and returns
a list of flags, with no database or Flask involved. That made the rules easy
to unit test with hand-built entries and easy for a vet to read and argue with.
The rules deliberately look at the last few *entries* rather than calendar
days, so a missed day does not hide a pattern.

**Wording never gives a verdict.** Every flag ends with "consider talking with
your vet about this pattern," and the pages say the flags are patterns, not a
diagnosis. A test asserts that the word "euthanasia" never appears in flag
text. The 35-point threshold is shown because the scale publishes it, but it
is labelled as the scale's threshold, not the app's judgement.

**Seven small charts instead of one seven-line chart.** Seven lines in seven
colours on one chart is unreadable and not colourblind-safe. Small multiples
with a single hue, all on the same 0 to 10 axis, let the eye compare shapes.
The total-score chart is the headline; it has a dashed threshold line and is
the only chart with a legend.

**One question at a time.** The first version showed all seven sliders on
one page. Owners found that a wall of controls on a hard day, so the check-in
became a guided flow: one question per screen, phrased as a question about the
pet by name, a progress bar, and a review at the end. It is the same HTML form
underneath; a small script hides and shows steps, so it degrades to the
one-page form without JavaScript, and a toggle lets people choose. A banner
prompts for the check-in whenever today has not been logged.

**Blue, not beige.** The first palette was cream and sage, which read as
"natural" but also a little sombre. The current theme is a clean blue with a
soft gradient accent, white cards, and coral for low scores, which feels
lighter without being flippant.

**Offline for real.** Chart.js is vendored into the repo rather than loaded
from a CDN, so the history page works with no network. Fonts are system fonts.

**Photos are resized on upload.** Phone photos are several megabytes. They are
shrunk to 800 pixels on the long side and re-encoded, so a semester of daily
photos stays small enough to back up.

**Backup is a zip of the data folder.** The database is copied with SQLite's
backup API so it is consistent even mid-write. Restore validates the zip
(rejects unsafe paths and unreadable databases) and requires a checkbox plus a
confirm dialog, because it is the one destructive action in the app.

## What was hard

- **Dates.** SQLite has no date type. I registered adapters so `DATE` columns
  round-trip as Python `date` objects, and avoided a Linux-only `strftime`
  flag that would have broken on Windows.
- **Weight units.** Owners might log kg one day and lb the next. Series and
  flags convert to the most recently used unit before comparing.
- **PDF layout.** Getting seven tiny charts to have readable date ticks took a
  few rounds. Rendering the PDF to an image and looking at it caught problems
  the tests never would.
- **The test that was wrong.** One test asserted a medication name no longer
  appeared on a page, but the "removed" flash message contained the name. The
  code was right; the test needed to consume the message first.

## The second version

After the first build the product was reworked around one insight: people
can't remember the slope of decline, and the app can. The changes that
followed, in the order they mattered:

1. **A single tap is the core record.** "Was today a good day or a bad day?"
   is the first question, the least mood-corruptible field, and enough on its
   own to draw a trend. Scores became optional.
2. **Personal behaviors instead of generic happiness.** Three to five things
   this animal does when she feels like herself, chosen at setup, ticked daily.
3. **A baseline from before decline**, stored apart from daily data and drawn
   as a labelled reference line, so the reference point isn't already sad.
4. **Honest smoothing.** A time-windowed mean that goes blank when the window
   is too empty, a classifier that needs sustained and consistent evidence,
   and copy that says "limited data" out loud.
5. **A safety layer** through which every generated sentence must pass.
6. **Tone.** No streaks, badges, paw prints, or "you missed a day". A graceful
   flow for when the animal dies, with nothing deleted automatically.
7. **The caregiver.** A weekly "How are you doing?" kept entirely separate.

## What I would do next

1. Reminders: a system notification at a chosen time if today is not logged.
2. A "compare with last month" view on the history page.
3. Optional sync between two devices through a folder the owner already syncs
   (Dropbox, iCloud), since the whole data set is one folder.
4. Ask a vet to review the flag thresholds and wording.
5. Species-specific help text on the sliders; a cat's mobility looks different
   from a dog's.

## Tools used

Python 3.11, Flask, SQLite, Jinja2, Chart.js 4, matplotlib, ReportLab, Pillow,
pytest, Playwright (screenshots only), PyInstaller (optional packaging).
