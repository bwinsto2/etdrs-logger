# ETDRS Logger

A small app for logging a participant's answers, letter by letter, during ETDRS
visual acuity testing (Good-Lite ETDRS 2000-series charts, forms 1–3, at 4 m).
It scores logMAR automatically and saves the results as spreadsheet (CSV) files.

It runs on your Mac, works offline, and never sends data anywhere.

---

## 1. One-time setup (about 10 minutes)

### Install Python

1. Go to **https://www.python.org/downloads/** and click the yellow
   **Download Python 3.x.x** button.
2. Open the downloaded `.pkg` file and click through the installer
   (Continue → Agree → Install). Enter your Mac password if asked.
3. When it finishes, you can close the Finder window that opens.

> Use the python.org installer, not Homebrew or the Mac's built-in `python3`.
> The python.org version includes the window toolkit (Tk) this app needs.

### Download the app

1. Go to the project page on GitHub: **https://github.com/bwinsto2/etdrs-logger**
2. Click the green **Code** button, then **Download ZIP**.
3. Open your **Downloads** folder and double-click `etdrs-logger-main.zip`.
   A folder called `etdrs-logger-main` appears.
4. Move that folder somewhere easy to find, for example your **Documents** folder.

### First launch

1. Open the `etdrs-logger-main` folder.
2. Double-click **`Start ETDRS Logger.command`**.
3. The first time, macOS may say it "cannot be opened because it is from an
   unidentified developer" or "could not verify" it. If so:
   - **Right-click** (or Control-click) the file and choose **Open**, then click
     **Open** again; **or**
   - open **System Settings → Privacy & Security**, scroll down, and click
     **Open Anyway** next to the message about `Start ETDRS Logger.command`.

   You only need to do this once.
4. A Terminal window opens (leave it open; it closes the app if you quit it),
   and then the ETDRS Logger window appears.

**If double-clicking doesn't work**, start it by hand: open the **Terminal** app
(Applications → Utilities → Terminal), type `cd ` (with a space), drag the
`etdrs-logger-main` folder onto the Terminal window, press Return, then type:

```
python3 etdrs_logger.py
```

and press Return.

---

## 2. Running a session

### Setup screen

Fill in every field:

| Field | What to enter |
|---|---|
| Subject ID | The participant's study ID |
| Visit / session | The visit or session number |
| Amblyopic eye | **L** or **R** |
| RA initials | Your initials |
| Data folder | Where the CSV files are saved. Click **Choose…** to change it. The app remembers your choice next time. |

Click **Start testing**. The amblyopic eye is always tested first, then the
fellow eye. The coloured bar at the top always shows which eye you are testing
(for example **Testing: LEFT eye (amblyopic)**).

### Choose the form

Click the button for the chart you are using (Form 1, 2 or 3). Each button
shows the chart's top line so you can match it to the physical chart.
**The same form cannot be used for both eyes in one session** — the form already
used for the first eye is greyed out for the second eye.

### Grade the letters

1. Click **Go** when the participant is ready. A blue box marks the current letter.
2. As the participant reads each letter aloud, press:

| Key | Meaning |
|---|---|
| **y** | Correct — letter turns **green**, box moves on |
| **h** | Wrong — letter turns **red**, box moves on |
| **delete** (Backspace) | Undo the last letter |
| **Right-click** or **Control-click** a letter | Change that letter: blank → green → red → blank |

Caps Lock doesn't matter. The box moves left to right, then down to the next line.
The panel on the right shows letters correct and the current logMAR as you go.

### When to stop

- If a participant gets **3 or more letters wrong on a line**, a **STOP TESTING**
  message appears as soon as that line is finished. The test is over for that eye
  and y/h stop working. (If the stop came from a mistyped key, press
  **delete** to undo it, or right-click the letter to fix it.)
- If the participant reads all 14 lines, the test ends by itself.
- To stop early for any other reason, click **End test early…**.

Letters that were never read count as wrong.

### Notes and Submit

After the test ends, check the marks, type any notes (e.g. "squinting",
"needed a break"), then click **Submit this eye**. The results for that eye are
saved straight away, and you go on to the fellow eye. After the second eye, a
summary of both eyes is shown; click **Next participant** to start again.

If that eye is already saved for this subject and session (for example, you are
re-testing), the app asks before replacing it. Only that eye's data is replaced.
If the app was closed between eyes, enter the same subject and session again and
it will offer to skip straight to the fellow eye.

---

## 3. Where the data goes

The default data folder is **Documents → ETDRS data** (you can choose another one
on the setup screen). Each subject + session gets two files, which open in
Excel, Numbers, R, SPSS, etc.:

### `<subject>_session<session>_summary.csv` — one row per eye

| Column | Meaning |
|---|---|
| subject_id | Subject ID as typed |
| session | Visit / session as typed |
| eye_tested | L or R |
| amblyopic_eye | L or R |
| eye_role | amblyopic or fellow |
| test_order | 1 (amblyopic eye) or 2 (fellow eye) |
| form | Chart form used: 1, 2 or 3 |
| letters_correct | Number of letters read correctly (0–70) |
| letters_total | Always 70 |
| logmar | 1.1 − 0.02 × letters_correct, 2 decimals |
| stopped_at_line | Line (1–14) where testing stopped; blank if no letters were read |
| stop_reason | `stop_rule` (3+ wrong on a line), `completed_chart` (all 14 lines read) or `ended_early` |
| ra_initials | RA initials |
| notes | Free-text notes |
| timestamp | Date and time saved, e.g. `2026-10-27T14:03:12-04:00` |
| app_version | Version of this app |

### `<subject>_session<session>_letters.csv` — one row per letter (70 per eye)

| Column | Meaning |
|---|---|
| subject_id, session, eye_tested, form | As above |
| line | Chart line, 1 (top) to 14 (bottom) |
| line_logmar | logMAR of that line, 1.0 (top) to -0.3 (bottom) |
| position | Letter position in the line, 1–5 (left to right) |
| letter | The chart letter |
| result | `correct`, `incorrect` or `not_read` |

Characters other than letters, numbers, `-`, `_` and `.` in the subject ID or
session are replaced with `_` in the **file name** only (the ID inside the file
is kept as typed).

---

## 4. Updating the app

Download the ZIP again (step 1, "Download the app") and replace the old folder.
Your data is not stored in the app folder, so nothing is lost.

---

## For developers

- `etdrs_logger.py` — the tkinter GUI (standard library only).
- `etdrs_core.py` — scoring, stop rule (`STOP_RULE_ERRORS = 3`), form-reuse check,
  CSV reading/writing. No GUI code.
- `charts.json` — the letters of the three forms (verified against the physical charts).
- `test_etdrs_core.py` — unit tests: `python3 -m unittest`
- `docs/chart_photos/` — photos of the physical charts.
- The last-used data folder is stored in `~/.etdrs_logger.json`.

See `SPEC.md` for the full specification.
