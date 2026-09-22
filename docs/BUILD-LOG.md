# Build log (running notes)

Raw material for the Phase 2 build log. Not the essay: a dated record of what
actually happened, kept as we go so it doesn't have to be reconstructed later.
Organised around the assignment's questions. Items marked **[you]** are places
where only you can fill in what you decided, why, and how it felt.

How the work was split, stated plainly so the log can be honest: every line of
code, every test, and every document in this repo was written by Claude Code
(Anthropic's coding agent) in a series of sessions. You set the direction,
answered the scoping questions, made every product decision, reviewed the
results, and asked for changes. That division is itself worth writing about.

---

## Timeline

### Sep 16, 2026 — planning, no code

- Started from an empty repo with the instruction "don't write any code yet,
  ask me questions first."
- Claude Code asked 14 scoping questions. Your answers set the shape of the
  whole project: pet owners only; several pets, cats and dogs; a real app, not
  a class demo; base it on the HHHHHMM scale; log once a day; include notes,
  weight, appetite, meds, photos; flag patterns; PDF for the vet; no vet
  login; Python; must work offline; semester, solo; one device is enough.
  **[you]** why Python, why offline, why one device.
- Plan written to `PLAN.md`: Flask + SQLite + Jinja + Chart.js + matplotlib +
  ReportLab + pytest, seven milestones over the semester. Rationale recorded
  for "why not Tkinter/PySide": web pages are easier to lay out, charts come
  free, same code can be hosted later.

### Sep 17 — milestones 1 to 7 built in one day

You said "keep working, you don't need to check in unless there's a problem."
Claude Code built all seven milestones in sequence, committing after each.

- **M1 skeleton.** pytest couldn't import the app until a `pyproject.toml`
  set `pythonpath`. First "it works on the machine but not in the test
  runner" moment.
- **M2 animals.** Photo upload with Pillow resizing. Self-caught mistake: the
  detail page used a Linux-only date format flag (`%-d`) that would have
  crashed on Windows; caught while re-reading the template before commit.
- **M3 daily entry.** One test failed and the *test* was wrong: it asserted a
  removed medication's name no longer appeared on the page, but the "removed"
  flash message contained the name. Caught immediately from the failure
  output. Lesson: a failing test is not automatically a bug in the code.
- **M4 charts.** The sandbox's network policy blocked every CDN (jsdelivr,
  cdnjs, unpkg). Chart.js was pulled from the npm registry tarball instead
  and vendored into the repo, which is what an offline app needed anyway.
  Chose seven small charts over one seven-line chart after reading the
  data-viz guidance: seven colours can't be told apart under colour
  blindness. Playwright's bundled browser version didn't match the installed
  Chromium; solved by pointing at the executable directly. The entries table
  overflowed its column; found by *looking* at a screenshot, not by a test.
- **M5 flags.** Pure functions with tests; wording rule "consider talking with
  your vet", never a verdict.
- **M6 PDF.** A helper passed `textColor` twice to ReportLab; it looked fine
  in the editor and crashed on the first real request. Caught in minutes by
  a smoke test that fetched every page. The first PDF spilled to two pages
  and two same-day event labels overlapped; caught only by rendering the PDF
  to PNG and reading it.
- **M7 polish.** Backup/restore as a zip (SQLite backup API for a consistent
  copy), random secret key stored in the data folder, PyInstaller build
  verified on Linux, README, DESIGN.md.

### Sep 17 — design passes

- "Make it prettier": Nunito font bundled (via npm tarball again) for offline
  use; warm palette; score ring; live total on the form.
- "Prompt each question daily, not a natural look, some pretty blue": the
  form became a one-question-at-a-time flow with a progress bar; palette
  switched to blue. Bug found by screenshot: the Save button showed on step
  one because a `display:flex` rule overrode the HTML `hidden` attribute.
  Fixed with a global `[hidden] { display:none !important }`.

### Sep 17 — version 2 from the long spec

You pasted a detailed product brief (good/bad day as the core field,
personalized behaviors, baseline, honest trend analysis, safety rules, tone
rules, one-page vet PDF, graceful ending, 33 screens).

- **Decision:** the brief asked for Next.js + Postgres. Claude Code kept
  Python/Flask because the project was already built on it and the brief
  allowed a documented alternative. Recorded in `docs/ARCHITECTURE.md`.
  **[you]** whether you agree with that call.
- Schema version 2 with an in-place migration for version-1 databases
  (scores became optional, `archived` became `status`).
- Analytics module: time-windowed 7-day mean that goes blank when the window
  is too empty; sufficiency levels; period comparison; classification into
  insufficient / stable / gradual down / gradual up / increased variability /
  temporary fluctuation. Written as pure functions with unit tests.
- **Model error caught by a test:** the first classifier labelled a single
  terrible day among steady ones as "increased variability". The spec said a
  single bad day must never look like a pattern; a test written from that
  sentence failed, and the fix checks for a lone outlier before variability.
- **Test-data errors:** two insight tests failed because the *test data* was
  wrong (a test expected "appetite stable" while its own data made appetite
  fall; another expected 25% where the data gave 27%). Time to diagnose: a
  few minutes each, from the assertion output.
- Safety layer: forbidden phrases ("it's time", "euthan", "put down", "you
  should", "recommend", "is dying"...). Tests assert the prohibited example
  statements are caught and all generated insights are clean. The fixed
  disclaimer is the only text that names euthanasia (to say the app never
  recommends it); tests had to strip it before checking pages.
- Maggie: 90 days of seeded data with noise, gaps, a treatment bump.
- One-page PDF rebuilt; first version spilled to page two and overlapped
  event labels; fixed after rendering to PNG.

### Sep 17 — "make it less ugly, test for bugs"

A scripted browser walkthrough (`scripts/e2e_check.py`) was added that
starts a fresh app and clicks through every flow like a person. It found
three real bugs the 90 unit tests had missed:

1. **Untouched sliders were saved as 5s.** Clicking Next through the score
   steps recorded a middle value for every category. The unit tests had
   encoded this behaviour as correct, so they passed. This is the clearest
   "looked right, was wrong" in the project: a data-integrity flaw in the
   core feature, present for hours, invisible to tests written by the same
   author as the code. Fix: an "unset" state per slider; only moved sliders
   are saved. **[you]** how you'd have spotted this as a user.
2. **The baseline never saved during onboarding.** A template condition
   ticked every category as "unsure" on first load, which disabled the
   sliders, so the form posted nothing. Unit tests posted directly to the
   route and passed. The walkthrough caught it only because it asserted a
   *downstream* effect (the dashboard mentioning the baseline).
3. **Phone navigation stuck to the top of the screen.** The header's blur
   filter made it the positioning parent of the fixed bottom nav. Diagnosed
   by reading the nav's computed position in the browser.

Also: the save function couldn't distinguish "leave alone" from "clear", so
editing couldn't blank a weight; fixed with an explicit sentinel.

### Sep 17 — demo link, second demo dog, graphics

- You asked for a clickable link. The app is a server, and the sandbox has no
  public address, so a read-only static snapshot was built by crawling the
  app and rewriting links, and published as a page. First crawl walked the
  calendar's "previous month" link back five years before a cap was added.
- Bruno, a steadily declining Labrador, added on request. The analytics
  classified him as "gradual decline" with no hand-tuning. Two things it
  exposed: the vet-visit comparison defaulted to a visit only four days old
  (near-empty comparison; now falls back to 30 days), and a steep decline
  produced thirteen amber observation boxes (capped to the biggest three
  category and two behavior changes).
- Icons and readability pass. Bug: navigation didn't know the current pet
  when a pet page was opened by direct link; fixed by reading the pet id from
  the URL on every request.

### Sep 22 — getting it onto your computer

- **Tried and failed: deploying to Fly.io from the sandbox.** Fly's API was
  blocked by the sandbox network policy. Workaround: a GitHub Actions
  workflow that deploys from GitHub's machines. Its first run failed
  instantly with zero jobs: two shell lines contained a colon-space inside a
  YAML plain scalar, which YAML can't parse. Then you chose to run locally
  instead, so the workflow was made manual-only.
- **Tried and failed: installing Python for you.** Not possible from a
  sandbox. Instead, GitHub Actions builds double-click packages on Windows
  and Mac runners with PyInstaller and attaches them to a release. The first
  build failed because a test-only package (`pypdf`) had been installed by
  hand and never listed; classic "works on my machine". The second build
  succeeded: a 46 MB Windows ZIP and a 35 MB Mac ZIP with Python inside.
  Unsigned, so both operating systems show a one-time warning; documented in
  READ-ME-FIRST.txt inside the ZIPs.
- **Bug check on request.** Unit suite (95 tests) and browser walkthrough
  passed; a code review of the whole codebase found ten real issues, three of
  which were reproduced against the running app before fixing:
  restoring an old-format backup broke every page until restart; non-ASCII
  passcodes crashed the unlock page; open redirects after unlock and after
  adding an event; no protection against another website posting to the
  local app (fixed with Sec-Fetch-Site/Origin checks rather than a token on
  every form); a race creating the secret key when two server workers start
  together; PDF charts used matplotlib's global state, unsafe under threads;
  removing a profile left its photo files behind; weight accepted "nan"; a
  one-query-per-row pattern on the trends page; and a pet named O'Malley
  broke the archive confirmation because the name was inside inline
  JavaScript. Eleven regression tests added; 106 tests now.
- The walkthrough script itself had a flaky step (read the page before the
  browser finished navigating). Not an app bug; fixed with an explicit wait.

---

## Answers to the assignment's questions (material)

### What worked, and why

- **Asking questions before writing code.** Fourteen answers on day one
  meant the stack, the scale, and the scope never had to be revisited.
- **Milestones with a commit and a test run after each.** Nothing was ever
  more than one milestone away from a known-good state.
- **Pure functions for the analytics and the flag/insight rules.** No
  database, no web framework, so they could be tested with hand-built data
  and argued with. The classifier bug was found by a test written straight
  from a sentence in the spec.
- **Looking at the output, not just testing it.** Screenshots and rendered
  PDFs caught overflow, overlap, the wrong-state Save button, the wall of
  amber boxes. None of those would ever fail a unit test.
- **A browser walkthrough that checks downstream effects**, not just that a
  form returned 200. That is what caught the silent baseline failure.
- **Vendoring dependencies** (Chart.js, the font). Forced by a blocked
  network, but exactly right for an offline app.
- **Honesty built into the copy and enforced by tests**: the safety layer,
  the "limited data" state, "no check-in recorded today" instead of guilt.

### What failed, specifically

- Loading Chart.js from a CDN: blocked. Loading Pyodide-style in-browser
  Python was considered for the demo link and rejected as too heavy and
  data-loss-prone.
- Deploying to Fly.io from the sandbox: the API host was unreachable.
- The first GitHub Actions workflow: YAML parse error, zero jobs.
- The first packaged build: missing test dependency.
- Installing Python on your machine from a remote session: impossible by
  design.
- The `pkill` command matching its own shell and killing the command chain
  that started the server (twice) — an embarrassing sandbox-side gotcha.

### Where the model handed over something that looked right and was wrong

| What | How caught | How long it lived |
| --- | --- | --- |
| Linux-only date format | re-reading before commit | minutes |
| ReportLab duplicate keyword | smoke-fetching every page | minutes |
| A test with wrong expectations (flash text) | test failure output | minutes |
| Single bad day classified as "variability" | unit test from the spec | minutes |
| Sliders' default 5 saved as data | reflection during the bug-hunt pass | several hours, across two design passes |
| Baseline form all "unsure" | browser walkthrough asserting a downstream effect | since version 2 was built |
| Fixed nav pinned to header on phones | inspecting computed style | since the nav was added |
| Vet comparison "since a visit 4 days ago" | looking at Bruno's page | until Bruno existed |
| Thirteen amber boxes | screenshot | until Bruno existed |
| YAML colon-space | GitHub, instantly | one push |
| Missing test dependency | CI | one push |
| Ten code-review findings | reading the code, then reproducing three | some since day one |

The pattern worth writing about: unit tests written by the same author as
the code share its blind spots. The two worst bugs were only visible from
the outside (a walkthrough, a screenshot) or from a rule stated by someone
else (the spec sentence about single bad days).

### What had to be learned that wasn't expected

- SQLite has no date type; `DATE` columns come back as strings unless you
  register converters.
- YAML plain scalars can't contain a colon followed by a space.
- `hmac.compare_digest` only accepts ASCII strings; compare bytes.
- An HTML `hidden` attribute loses to any CSS `display` rule.
- A CSS `backdrop-filter` (or any filter) becomes the containing block for
  `position: fixed` descendants.
- Modern browsers send `Sec-Fetch-Site`, which is enough to refuse cross-site
  form posts without a token on every form.
- matplotlib's `pyplot` keeps global state and isn't thread-safe; build
  `Figure` objects directly.
- PyInstaller only builds for the OS it runs on; a Linux sandbox can't make a
  Windows executable, but GitHub's runners can.
- macOS and Windows both warn about unsigned apps, and signing needs paid
  developer accounts.
- The HHHHHMM scale's "above 35" reference is published, but showing it as a
  line invites reading it as a verdict; the app labels it as the scale's
  number, never its own.

### What surprised (candidates)

- How much the *wording* mattered: the safety layer and tone rules changed
  the product more than any feature.
- That the most serious bug (default 5s saved as data) was in the feature
  everything else depends on, and the tests were part of the problem.
- That a second demo dog with a different trajectory revealed two design
  problems within minutes of existing.
- How much of "shipping" was environment, not code: blocked networks,
  OS-specific builds, code signing, YAML.
- **[you]** what surprised *you* about working this way.

### Claude Code requirement

Every component was built with Claude Code. If one has to be shown, the
strongest candidates are:

1. `app/analytics.py` + `tests/test_analytics.py`: the trend smoothing and
   classification, with the single-bad-day rule caught by a test.
2. The guided check-in (`app/templates/checkin.html`, `app/static/app.js`,
   `app/routes/entries.py`): built, then found to have the default-5 flaw,
   then fixed with the unset state and regression tests.
3. `scripts/e2e_check.py`: the browser walkthrough that found three bugs the
   unit tests missed.

What it did: asked the scoping questions, wrote the plan, built every
milestone, wrote the tests, took and read screenshots, rendered and read
PDFs, ran its own code review and fixed the findings, set up CI, and kept
this log. What it got wrong is listed above.

---

## Where to look

- Commit history on the branch: one commit per milestone or pass, messages
  describe what changed and why.
- `docs/ARCHITECTURE.md`: schema, the algorithm, safety rules, limitations.
- `docs/DESIGN.md`: the narrative of design decisions.
- `scripts/e2e_check.py` and `tests/`: what is checked automatically.
