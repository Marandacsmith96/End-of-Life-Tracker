# Build log: Pet Quality-of-Life Tracker

*Phase 2 submission. The dated running notes this is condensed from are in
`docs/BUILD-LOG.md`; the commit history on the branch is the other record.*

## What I was building, and how the work was split

A small offline app for people whose pet is old or seriously ill. You record
one thing a day (was it a good day or a bad day), optionally seven scores
from a published veterinary scale, and the app shows the trend honestly and
prepares a one-page summary for the vet. It must never say "it's time"; that
is the vet's conversation, not the app's.

To be plain about authorship: every line of code, every test, and every
document in the repository was written by Claude Code. I set the direction,
answered the scoping questions, made the product decisions, used the thing,
and sent back what was wrong. This log is about what that arrangement was
actually like. **[you: one or two sentences on why you chose this project.]**

## What worked, and why I think it worked

**Answering questions before any code existed.** The first session wrote no
code at all. It asked fourteen scoping questions (who is this for, one pet or
several, phone or laptop, offline or hosted, what should it never say) and I
answered them. The stack, the scale, and the no-verdicts rule were decided
that day and never had to be reopened. I think it worked because every later
"should it do X?" had an answer already written down.

**Milestones with a test run and a commit after each.** Seven milestones in
one day, each one leaving the app in a known-good state. When something broke
later, there was always a last-good commit a few minutes back.

**Keeping the analysis as pure functions.** The trend smoothing and the
"improving / declining / stable / not enough data" classifier take a list of
dated numbers and return an answer; no database, no web framework. That made
them easy to test with hand-built data, and it is where the one bug caught by
a test written straight from a sentence in my spec lived (below).

**Looking at the output instead of only testing it.** Claude Code took
screenshots of its own pages and rendered its own PDFs, then read them. That
caught overlapping chart labels, a wall of thirteen amber warning boxes, a
Save button that hid itself, and a dog's "age" that read "0 months". None of
those would ever have failed a unit test.

**Example pets.** Three fictional animals with different trajectories (steady,
declining, improving). The second one, Bruno, exposed two design problems
within minutes of existing, because the real pet I was imagining had only one
story. The third, Juniper, was built to improve and the app called her
"stable" on the first try; the curve had to be re-tuned until the classifier
agreed with the story.

## What I tried that failed, specifically

- **Loading Chart.js from a CDN.** The build environment blocks outside
  networks, so the page loaded with no chart. The fix was to vendor the
  library and the font into the repo, which turned out to be right anyway for
  an app that promises to work offline.
- **Deploying to Fly.io from the coding session.** The deploy API was
  unreachable from the sandbox. We moved deployment into a GitHub Actions
  workflow that I trigger by hand; the first version of that workflow had zero
  jobs because a YAML value contained a colon followed by a space.
- **Building the Windows download in the sandbox.** PyInstaller only builds
  for the operating system it runs on, and the sandbox is Linux. GitHub's
  Windows and Mac runners build it instead.
- **The first time I opened the Windows download.** A black window, no app.
  The server was running, but the step that opens the browser had failed
  silently and the window said nothing. The launcher now prints the address
  in plain words, tries a second way to open the browser, picks the next free
  port if 5000 is busy, and leaves the window open on an error.
- **Trusting green checks.** Before the second bug hunt we had passing tests,
  a passing browser walkthrough, and a clean crawl of every page. Two
  independent reviews then found twenty-three real bugs. Green meant "the
  things we thought to check are fine", nothing more.
- **A shell command that killed itself.** Stopping the test server with
  `pkill` matched the shell that ran it, twice, taking the rest of the command
  chain with it. Small, but it cost real time until the pattern was noticed.

## Where the model handed me something that looked right and was wrong

This happened constantly. The table in the running notes has twenty rows;
these are the ones worth the page.

**The slider that saved a 5 nobody chose.** The seven score sliders defaulted
to the middle, and a check-in saved all seven even if you only answered
"good day or bad day". Every trend, every average, and every observation was
being computed partly from numbers no one had entered. It looked completely
right: the charts were smooth and the tests passed, because the tests had
been written by the same author with the same assumption. It lived for
several hours and through two design passes. It was caught not by a test but
by a deliberate "what here looks right and is wrong?" pass; the fix was an
"unset" state per slider, with only moved sliders saved. **[you: how would
you have spotted this as a user, and when?]**

**The baseline form that never saved.** A template condition marked every
category "unsure" on first load, which disabled the sliders, so the form
posted nothing. Unit tests posted directly to the route and passed. It was
caught by the browser walkthrough, which asserts a downstream effect (the
baseline line appears on the chart) rather than a status code. It had been
broken since that version of the form was written.

**The classifier that called a single bad day "variability".** My spec said
one bad day must never change the trend. The implementation smoothed over a
window and would flag it. A test written from that one sentence failed on the
first run. Minutes to catch, because the rule came from outside the code.

**Restore, three times.** Backup and restore was reviewed twice and still:
accepted any file with an "animals" table; deleted the current data before
copying the new data in, so a full disk halfway through meant no database at
all; and refused any backup over 10 MB because the photo upload limit applied
to it. Caught in the fourth and fifth reviews by a reviewer deliberately
making the copy fail. The lesson I take: a destructive feature needs its own
failure-mode review, not a pass over the happy path.

**Phone access that didn't sign anyone out.** The feature let a phone on the
Wi-Fi unlock with a passcode. Switching it off and on with a new passcode
only rewrote a settings file; a phone that had unlocked stayed unlocked for
31 days. The page even promised the opposite. Two days, caught by a reviewer
replaying an old cookie.

**The cross-site check that trusted the Host header.** The guard against
other websites posting to the app compared the request's Origin to its Host,
and Host is whatever the browser was told. A page on an attacker's domain
pointed at 127.0.0.1 could have read and changed everything on a local copy.
Lived since the check was written; caught by a reviewer trying it.

The pattern across all of these: tests written by the author of the code
share its blind spots. Every serious bug was found from outside, by a
screenshot, a walkthrough that checks effects, a rule stated by someone else,
or a second reader told to break things.

## What I had to learn that I did not expect

- SQLite has no date type; dates come back as strings unless you register a
  converter, and a whole feature can silently compare strings to dates.
- A CSS `backdrop-filter` becomes the positioning parent for `position:
  fixed` children, which is why the phone's bottom navigation pinned itself
  to the header.
- Modern browsers send a `Sec-Fetch-Site` header, which is enough to refuse
  cross-site posts without a token on every form, and that still is not
  enough if you trust the Host header.
- Chrome refuses to open some ports as "unsafe" (5061 is reserved for a
  phone protocol), which is why the launcher's port search starts at 5000.
- Unsigned Windows and Mac apps both warn the user, and signing them costs
  developer-account money. The README has to explain the warning instead.
- The scale I used (HHHHHMM) publishes a threshold number. Drawing it as a
  line on a chart invites reading it as a verdict, which is exactly what the
  app must not do, so it is labelled as the scale's number and never the
  app's opinion.
- **[you: one thing you personally had to learn: Git, the terminal, reading
  a traceback, whatever it was.]**

## What surprised me

How much the *wording* mattered. The rules about what the app may never say
changed the product more than any feature did, and a test that forbids
words like "streak" and "badge" once failed on a CSS class name.

That the worst bug was in the feature everything else depends on, and that
the tests were part of the problem rather than the safety net.

How much of "shipping" was environment rather than code: blocked networks,
one operating system per build, YAML punctuation, a port Chrome won't open.

How a second reader kept finding things after the first one stopped. Five
rounds of "check for bugs" found 23, 10, 10, 9 and 28 real problems, and the
last round's two worst ones were old. I no longer believe a review is
finished because it came back empty once.

**[you: what surprised you about working this way, and what you would do
differently next time.]**

## Claude Code requirement

Every component was built with Claude Code. If one has to be shown, the
clearest is the **guided check-in** (`app/templates/checkin.html`,
`app/static/app.js`, `app/routes/entries.py`): Claude Code built it, took
screenshots to lay it out for a phone, then found its own default-5 flaw,
designed the "unset slider" fix, and wrote the regression tests that keep it
fixed. A second candidate is `app/analytics.py` with `tests/test_analytics.py`,
where the single-bad-day rule from my spec became a failing test before it
became working code.

What Claude Code did for me: asked the scoping questions, wrote the plan,
built every milestone, wrote 180 tests, took and read its own screenshots and
PDFs, ran reviews of its own code with independent reviewer agents and fixed
their findings, set up the build and deploy workflows, and kept the running
log this is condensed from. What it got wrong is the section above.

## Where to look

- Repository: branch `claude/animal-qol-tracker-planning-yavwqv`, one commit
  per milestone or fix, messages say what changed and why.
- Downloads for Windows and Mac are on the repository's Releases page.
- The read-only demo with the three example pets, and `docs/BUILD-LOG.md`
  for the full dated notes behind every claim here.
