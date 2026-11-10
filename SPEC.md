# ETDRS Logger — spec

A local desktop app for a research assistant (RA) to log a participant's
letter-by-letter answers during ETDRS visual acuity testing, score logMAR, and
save the results as CSV. Runs offline on macOS. No network access.

## Platform

- Python 3 + tkinter (standard library only, no pip installs needed), so an RA
  can download the repo from GitHub and run `python3 etdrs_logger.py`.
- Must work on macOS with the python.org installer (which bundles Tk). The README
  should give step-by-step Mac setup for a non-programmer, including how to
  download the repo as a ZIP and run it, plus an optional double-clickable
  launcher (e.g. a `.command` file).
- Chart letters come from `charts.json` (do not hard-code them elsewhere).
  Photos of the physical charts are in `docs/chart_photos/` for reference.

## Flow

1. **Session setup screen**
   - Subject ID (text, required)
   - Visit/session (text or number, required)
   - Amblyopic eye: dropdown L / R (required)
   - RA initials (required)
   - Data folder: choose a directory (remember the last-used folder between runs,
     e.g. in a small config file in the user's home directory).
2. **Eye screen** — both eyes are always tested, one after the other, **amblyopic
   eye first**, then the fellow eye. Show clearly which eye is being tested
   (e.g. "Testing: LEFT eye (amblyopic)").
3. **Form selection** — three large buttons for forms 1, 2 and 3. Each shows the
   form number plus its first line (e.g. "Form 1 — C O H Z V") so it's easy to
   match to the physical chart. For the second eye, the form used for the first
   eye must be disabled / raise a clear error if chosen: the same form may not be
   used twice in one session.
4. **Chart screen** — a digital reconstruction of the chosen chart: 14 lines of 5
   letters, letter size shrinking down the chart like the real one (but all lines
   must stay comfortably readable on a laptop screen). Show the logMAR value
   for each line in the margin.
   - The RA presses **Go** to begin. A visible cursor marks the current letter,
     starting at line 1, letter 1, moving left to right then down.
   - **y** = correct → letter turns green, cursor advances.
   - **h** = wrong → letter turns red, cursor advances.
   - **Backspace** = undo the last mark (cursor goes back, letter returns to unmarked).
   - **Right-click** any letter cycles it unmarked → green → red → unmarked, for
     editing. (Also support Ctrl-click, since many Mac users have no right button.)
   - Keys must work regardless of caps lock (y/Y, h/H).
   - Running totals visible: letters correct so far, current estimated logMAR.
5. **Stop rule** — standard ETDRS: when a line is finished (all 5 letters marked)
   and 3 or more letters on that line are wrong, show a prominent popup telling
   the RA to **stop testing — the task is over for this eye**. Further y/h input
   is blocked after the popup (but right-click edits are still allowed).
   Keep the threshold (3) as a named constant.
   If the participant reads all 14 lines, the test also ends.
   The RA can also end early with an "End test" button (with confirmation).
6. **Scoring** — standard ETDRS letter-by-letter scoring at 4 m:
   `logMAR = 1.1 − 0.02 × (total letters correct)`.
   Any letter not marked (not reached because testing stopped) counts as wrong.
   Show the final logMAR and letters correct before submit, rounded to 2 decimals.
7. **Notes + Submit** — free-text notes field, then **Submit**. Submitting saves
   this eye's result and moves on to the fellow eye (back to form selection).
   After the second eye is submitted, show a summary of both eyes and return to
   the session setup screen for the next participant.

## Data output

For each subject and session, write two CSV files in the chosen data folder
(sanitize file names), so each stays a simple flat table:

- `<subjectID>_session<session>_summary.csv` — one row per eye:
  `subject_id, session, eye_tested (L/R), amblyopic_eye (L/R), eye_role
  (amblyopic/fellow), test_order (1/2), form, letters_correct, letters_total (70),
  logmar, stopped_at_line, stop_reason (stop_rule / completed_chart / ended_early),
  ra_initials, notes, timestamp (ISO 8601 local time), app_version`
- `<subjectID>_session<session>_letters.csv` — one row per letter on the chart
  (70 rows per eye): `subject_id, session, eye_tested, form, line (1–14),
  line_logmar, position (1–5), letter, result (correct / incorrect / not_read)`

Save each eye's rows immediately when that eye is submitted, so nothing is lost
if the app is closed between eyes. If files for that subject+session already
exist and already contain that eye, ask before overwriting (and on overwrite,
replace only that eye's rows). If they contain the other eye, append.
Also check the existing summary file when enforcing the "different form for each
eye" rule, so it still works if the app was restarted between eyes.

## Quality

- Keep the scoring, stop rule, and CSV-writing logic in a module separate from
  the GUI, with unit tests (`python3 -m unittest`) covering: scoring, stop rule
  on lines with 2 / 3 / 5 errors, not-read letters counted wrong, undo, CSV
  output, overwrite/append behavior, same-form rejection.
- Simple, uncluttered UI with large text: the RA is operating it in real time.

## Form counterbalancing (added in 1.2.0)

- Visits are fixed and listed in `study.json`: prep1a, S2 prep, 2-weeks S2,
  4-weeks S2, 8-weeks S2. The setup screen's Visit field is a dropdown of these.
- The first time a Subject ID is used with a data folder, the app confirms it is
  a new participant and assigns a schedule giving the form for each visit and eye
  (AE/FE). The schedule is saved in `form_assignments.csv` in the data folder
  and never changes after that.
- Schedules rotate through the forms (AE: A B C A B; FE one step ahead or
  behind: B C A B C or C A B C A), which minimises repeats:
  - the eyes differ within a visit
  - no eye gets the same form at consecutive visits
  - each eye's forms are used 2/2/1 times, and repeats are 3 visits apart
  - consecutive visits share only one form
- The 12 schedules (6 form labellings × 2 FE offsets) are given out by blocked
  randomisation (random order, each once per block of 12), which balances
  forms across visits and eyes over participants.
- The form screen shows and marks the scheduled form. Choosing another form
  needs confirmation. The summary CSV records `scheduled_form` next to `form`.
