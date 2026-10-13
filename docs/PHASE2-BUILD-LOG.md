# Build log: Pet Quality-of-Life Tracker

*Phase 2 submission. The dated running notes this essay is condensed from are
in `docs/BUILD-LOG.md`, and the commit history on the branch is the other
record of what happened and when.*

## What I was building, and who actually wrote it

The project is a small app for people whose pet is old or seriously ill. Once
a day you answer one question, "was today a good day or a bad day for your
pet?", and if you have the energy you can also rate seven things on a scale
of 0 to 10: pain, appetite, hydration, cleanliness, happiness, mobility, and
whether good days outnumber bad ones. That scale is a real one that vets use.
The app turns those answers into a trend chart, writes plain-English
observations about what has changed, and prepares a one-page summary you can
hand to the vet. The one rule it must never break is that it never tells you
"it's time". That is a conversation for you and your vet, and the app's job
is to make that conversation better informed, not to have it for you.

I want to be plain about who did what, because the honesty of this log
depends on it. Every line of code, every test, and every document in the
project was written by Claude Code, which is an AI assistant that works
inside a programmer's tools and can read, write, and run code on its own. My
part was to decide what the app should be, answer its questions, make every
product decision, use the app as a real person would, and tell it what was
wrong. The rest of this log is about what that arrangement was actually
like. **[you: one or two sentences on why you chose this project.]**

## What worked, and why I think it worked

The single best decision was to answer questions before any code existed.
The first session produced no code at all. Instead, Claude Code asked me
fourteen questions: who is this for, one pet or several, phone or laptop,
does it need the internet, what must it never say. I answered them, and those
answers settled the technology, the vet scale, and the no-verdicts rule on
day one. None of them had to be reopened later. I think this worked because
every later "should it do X?" question already had an answer written down,
so there was nothing to argue about mid-build.

The second thing that worked was building in small steps and checking each
one. The app was built as seven milestones in one day, and after each one
the automated tests were run and the work was saved as a checkpoint. When
something broke later, there was always a known-good version a few minutes
back to compare against.

The third was keeping the analysis separate from everything else. The part of
the app that smooths the daily scores into a trend line, and the part that
decides whether a pet is "improving", "declining", "stable" or "not enough
data yet", are written as plain calculations: a list of dates and numbers
goes in, an answer comes out, with no database or web page involved. That
made them easy to test with made-up data, and it is where the one bug caught
by a test written straight from a sentence in my spec lived. More on that
below.

The fourth was looking at the output rather than only testing it. Claude
Code took screenshots of its own pages and opened the PDFs it generated, then
read them the way a person would. That is how it caught chart labels piled
on top of each other, a wall of thirteen amber warning boxes on one pet's
page, a Save button that hid itself, and a dog whose age read "0 months".
None of those would ever have failed an automated test, because the tests
only know what you tell them to check.

The last was the example pets. Three fictional animals were added with
different stories: Maggie is steady then declines, Bruno declines steadily,
and Juniper starts low and gets better. The second one exposed two design
problems within minutes of existing, because the real pet I had been
imagining had only one story. The third was built to improve, and the app
called her "stable" on the first try, so her made-up history had to be
adjusted until the app's own judgement agreed with the story we meant to
tell. That was a useful reminder that "the app says X" and "X is true" are
different things.

## What I tried that failed, specifically

Loading the chart library from the internet failed first. The environment
Claude Code works in blocks outside connections, so the page loaded with an
empty space where the chart should be. The fix was to copy the library and
the font into the project itself. That turned out to be the right design
anyway for an app that promises to work with no internet connection.

Publishing the app to a hosting service from inside the coding session
failed for the same reason: the service could not be reached. We moved that
job to GitHub Actions, which is a system that runs tasks on GitHub's own
computers when you ask it to. The first version of that task did nothing at
all, because one line of its configuration file contained a colon followed
by a space, which that file format reads as the start of a new setting. One
character of punctuation, zero jobs run.

Building the Windows download failed in the coding session because the tool
that packages a Python program into a double-clickable app can only build for
the operating system it is running on, and the session runs on Linux. GitHub's
Windows and Mac machines build the downloads instead.

The first time I opened the Windows download, I got a black window and no
app. The program was actually running, but the step that opens your web
browser had failed silently, and the window gave no hint of what to do. The
launcher now prints the address in plain words, tries a second way to open
the browser, moves to the next free port if the usual one is busy, and keeps
the window open on an error so you can read it.

Trusting green checkmarks failed in a more subtle way. Before the second bug
hunt we had passing tests, a passing automated walkthrough of the app in a
browser, and a clean crawl of every page. Two independent reviews then found
twenty-three real bugs. Green meant only "the things we thought to check are
fine", which is a much weaker statement than it feels like.

And one small, embarrassing one: a command meant to stop the test server
matched the very command window that ran it, and shut that down instead,
twice. It cost real time before the pattern was noticed.

## Where the model handed me something that looked right and was wrong

This happened constantly. The running notes have a table with twenty rows.
These are the ones worth the page.

**The slider that saved a 5 nobody chose.** The seven rating sliders started
in the middle, at 5, and a check-in saved all seven even if you only answered
the good-day-or-bad-day question. So every trend, every average, and every
observation was being calculated partly from numbers that nobody had entered.
It looked completely right. The charts were smooth and the tests passed,
because the tests had been written by the same author with the same
assumption baked in. It lived for several hours and through two rounds of
visual polish. It was caught not by a test but by a deliberate pass whose
only instruction was "what here looks right and is wrong?" The fix was to
give each slider an "untouched" state, so only sliders you actually moved are
saved. **[you: how would you have spotted this as a user, and when?]**

**The form that never saved.** The "baseline" form, where you estimate what
your pet was like before they got ill, had a condition that marked every
category as "unsure" when the page first loaded. That disabled the sliders,
so the form sent nothing when you pressed Save. The tests passed because they
sent data straight to the server, skipping the page entirely. It was caught
by the browser walkthrough, which checks for a downstream effect (does the
baseline line appear on the chart?) rather than just "did the server say
OK". It had been broken since that version of the form was written.

**One bad day called a trend.** My spec said a single bad day must never
change the trend. The first implementation smoothed over a window of days and
would have flagged it. A test written from that one sentence failed on the
first run. It took minutes to catch, and I think that is because the rule
came from outside the code, from me, rather than from the code's own logic.

**Backup and restore, three times.** This feature was reviewed twice and
still had three holes. It accepted any file that happened to contain a table
named "animals". It deleted your current data before copying the new data
in, so if the disk filled up halfway through you were left with no data at
all. And it refused any backup bigger than 10 MB, because the size limit meant
for photos applied to it. All three were caught in the fourth and fifth
reviews, by a reviewer who deliberately made the copy fail. The lesson I take
is that anything which can destroy data needs its own review of how it fails,
not just a check that it works when everything goes right.

**Phone access that didn't lock anyone out.** A late feature lets a phone on
your home Wi-Fi open the app after entering a passcode. Switching the feature
off and on again with a new passcode only rewrote a settings file. A phone
that had already unlocked stayed unlocked for 31 days, and the page even
promised the opposite. It lived for two days and was caught by a reviewer
who saved an old login and replayed it after the passcode change.

**The security check that trusted the wrong thing.** A guard stops other
websites from sending commands to the app. It worked by comparing where a
request claimed to come from with the address the app thought it was at, but
that second address is also just something the browser says. A malicious web
page could have pointed its own domain name at your computer and then read
and changed everything. It had been there since the guard was written and
was caught by a reviewer trying exactly that trick.

The pattern across all of these is the same: tests written by the author of
the code share the author's blind spots. Every serious bug was found from the
outside, by a screenshot, by a walkthrough that checks effects rather than
status codes, by a rule stated by someone other than the code's author, or by
a second reader whose only job was to break things.

## What I had to learn that I did not expect

Some of this is technical trivia I now know, and some of it changed how I
think about the project.

- The database the app uses has no idea what a date is. Dates come back as
  text unless you tell it otherwise, and a feature can quietly compare text
  to dates and get nonsense without ever showing an error.
- A visual blur effect on the top bar changed how the phone's bottom
  navigation positioned itself, which is why that bar pinned itself to the
  top of the screen for a while. Styling rules can have side effects far
  from where they are written.
- Chrome refuses to open some network ports because they are reserved for
  other kinds of traffic, which is why the app's launcher searches for a free
  port starting from a known-safe one.
- Unsigned Windows and Mac apps both show a scary warning when opened, and
  signing them costs money through a developer account. The README has to
  explain the warning instead.
- The vet scale the app uses publishes a threshold number. Drawing that
  number as a line on a chart invites people to read it as a verdict, which
  is exactly what the app must never give. So it is labelled as the scale's
  number and never as the app's opinion. I did not expect a chart design
  choice to be an ethics choice.
- **[you: one thing you personally had to learn: Git, the terminal, reading
  an error message, whatever it was.]**

## What surprised me

How much the wording mattered. The rules about what the app may never say
changed the product more than any feature did. There is a test that forbids
words like "streak" and "badge" anywhere in the app, because those words turn
caring for a dying pet into a game, and it once failed on an internal name
for a design element that no user would ever see. The rule was doing its job
even then.

That the worst bug was in the feature everything else depends on, and that
the tests were part of the problem rather than the safety net.

How much of "shipping" was about the environment rather than the code:
blocked networks, one operating system per build, a punctuation mark in a
configuration file, a port a browser refuses to open.

How a second reader kept finding things after the first one stopped. Five
rounds of "check for bugs" found 23, 10, 10, 9 and 28 real problems, and the
two worst ones in the last round were old. I no longer believe a review is
finished because it came back empty once.

**[you: what surprised you about working this way, and what you would do
differently next time.]**

## The Claude Code requirement

Every component was built with Claude Code. If one has to be shown, the
clearest is the guided check-in, the screen where you answer the daily
questions. Claude Code built it, took screenshots to lay it out for a phone,
then found its own "slider saves a 5" flaw, designed the untouched-slider
fix, and wrote the tests that keep it fixed. The files are
`app/templates/checkin.html`, `app/static/app.js`, and
`app/routes/entries.py`. A second candidate is the analysis module,
`app/analytics.py` with its tests, where the single-bad-day rule from my spec
became a failing test before it became working code.

What Claude Code did for me, in plain terms: it asked the questions a good
contractor would ask before starting, wrote the plan, built every piece,
wrote 180 automated tests, took and read its own screenshots and PDFs, ran
reviews of its own work using separate reviewer agents and then fixed what
they found, set up the automatic builds for Windows and Mac, and kept the
running notes this essay is condensed from. What it got wrong is the section
above, and it is long.

## Where to look

- The repository on GitHub, branch `claude/animal-qol-tracker-planning-yavwqv`,
  with one saved change per milestone or fix and messages that say what
  changed and why.
- The Windows and Mac downloads on the repository's Releases page.
- The read-only demo with the three example pets, and `docs/BUILD-LOG.md`
  for the full dated notes behind every claim made here.
