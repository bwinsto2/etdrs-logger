"""Scoring, stop rule, form checks and CSV storage for the ETDRS Logger.

This module has no GUI code so it can be unit tested on its own
(``python3 -m unittest``). The GUI lives in ``etdrs_logger.py``.
"""

from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

APP_VERSION = "1.2.0"

# Standard ETDRS stop rule: stop once a completed line has this many errors.
STOP_RULE_ERRORS = 3

LETTERS_PER_LINE = 5
NUM_LINES = 14
TOTAL_LETTERS = LETTERS_PER_LINE * NUM_LINES  # 70

# logMAR = LOGMAR_BASE - LOGMAR_PER_LETTER * letters correct (4 m testing).
LOGMAR_BASE = 1.1
LOGMAR_PER_LETTER = 0.02

EYES = ("L", "R")
EYE_NAMES = {"L": "LEFT", "R": "RIGHT"}

STOP_RULE = "stop_rule"
COMPLETED_CHART = "completed_chart"
ENDED_EARLY = "ended_early"

RESULT_CORRECT = "correct"
RESULT_INCORRECT = "incorrect"
RESULT_NOT_READ = "not_read"

SUMMARY_COLUMNS = [
    "subject_id", "session", "eye_tested", "amblyopic_eye", "eye_role",
    "test_order", "retest", "form", "scheduled_form", "letters_correct", "letters_total", "logmar",
    "stopped_at_line", "stop_reason", "ra_initials", "notes", "timestamp",
    "app_version",
]
LETTER_COLUMNS = [
    "subject_id", "session", "eye_tested", "form", "line", "line_logmar",
    "position", "letter", "result",
]

# Written with a byte-order mark so Excel on a Mac reads non-ASCII text
# (e.g. accents in notes) correctly; Python, R and pandas all handle it.
CSV_ENCODING = "utf-8-sig"


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------

@dataclass
class Charts:
    line_logmar: List[float]
    forms: Dict[str, List[str]]  # form number ("1".."3") -> 14 lines of 5 letters

    def form_numbers(self) -> List[str]:
        return sorted(self.forms, key=int)


def load_charts(path: str) -> Charts:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    line_logmar = [float(v) for v in data["line_logmar"]]
    forms = {str(k): [str(line) for line in v] for k, v in data["forms"].items()}
    if len(line_logmar) != NUM_LINES:
        raise ValueError(f"charts.json: expected {NUM_LINES} line_logmar values")
    for form, lines in forms.items():
        if len(lines) != NUM_LINES or any(len(l) != LETTERS_PER_LINE for l in lines):
            raise ValueError(
                f"charts.json: form {form} must have {NUM_LINES} lines "
                f"of {LETTERS_PER_LINE} letters")
    return Charts(line_logmar=line_logmar, forms=forms)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def logmar_from_letters(letters_correct: int) -> float:
    """ETDRS letter-by-letter score at 4 m, rounded to 2 decimals."""
    value = round(LOGMAR_BASE - LOGMAR_PER_LETTER * letters_correct, 2)
    return value if value != 0 else 0.0  # avoid "-0.00"


def format_logmar(value: float) -> str:
    value = round(value, 2)
    if value == 0:
        value = 0.0
    return f"{value:.2f}"


class ChartTest:
    """State of one eye's test: a mark for each of the 70 letters plus a cursor.

    Each mark is None (not read), True (correct) or False (wrong). Letters are
    indexed 0..69, line by line, left to right.
    """

    def __init__(self, lines: List[str]):
        self.lines = list(lines)
        self.letters = "".join(self.lines)
        self.marks: List[Optional[bool]] = [None] * TOTAL_LETTERS
        self.cursor = 0
        self.ended_early = False

    # --- input ---------------------------------------------------------

    @property
    def accepting_input(self) -> bool:
        """True while y/h may still be entered."""
        return not self.is_over

    def mark(self, correct: bool) -> bool:
        """Mark the letter under the cursor and advance. Returns False if blocked."""
        if not self.accepting_input:
            return False
        self.marks[self.cursor] = bool(correct)
        self.cursor += 1
        return True

    def undo(self) -> bool:
        """Undo the last y/h mark: move the cursor back and clear that letter."""
        if self.cursor == 0 or self.ended_early:
            return False
        self.cursor -= 1
        self.marks[self.cursor] = None
        return True

    def cycle(self, index: int) -> Optional[bool]:
        """Right-click edit: unmarked -> correct -> wrong -> unmarked."""
        current = self.marks[index]
        self.marks[index] = True if current is None else (False if current else None)
        return self.marks[index]

    def end_early(self) -> None:
        if not self.is_over:
            self.ended_early = True

    def resume(self) -> bool:
        """Take back "End test early" so testing carries on where it stopped."""
        if not self.ended_early:
            return False
        self.ended_early = False
        return True

    # --- derived state -------------------------------------------------

    def line_marks(self, line: int) -> List[Optional[bool]]:
        """Marks for a 0-based line."""
        start = line * LETTERS_PER_LINE
        return self.marks[start:start + LETTERS_PER_LINE]

    def line_errors(self, line: int) -> int:
        return sum(1 for m in self.line_marks(line) if m is False)

    def line_complete(self, line: int) -> bool:
        return all(m is not None for m in self.line_marks(line))

    @property
    def stop_line(self) -> Optional[int]:
        """1-based line where the stop rule fired, or None.

        The rule is checked on every line the cursor has passed: the first one
        that is fully marked and has >= STOP_RULE_ERRORS wrong. It is worked
        out from the current marks, so undo or a right-click correction on
        that line takes the stop back.
        """
        lines_reached = self.cursor // LETTERS_PER_LINE
        for line in range(lines_reached):
            if self.line_complete(line) and self.line_errors(line) >= STOP_RULE_ERRORS:
                return line + 1
        return None

    @property
    def stop_rule_met(self) -> bool:
        return self.stop_line is not None

    @property
    def chart_completed(self) -> bool:
        return self.cursor >= TOTAL_LETTERS

    @property
    def is_over(self) -> bool:
        return self.ended_early or self.stop_rule_met or self.chart_completed

    @property
    def stop_reason(self) -> Optional[str]:
        if self.stop_rule_met:
            return STOP_RULE
        if self.chart_completed:
            return COMPLETED_CHART
        if self.ended_early:
            return ENDED_EARLY
        return None

    @property
    def stopped_at_line(self) -> Optional[int]:
        """1-based line where testing stopped (None if nothing was read)."""
        if self.stop_rule_met:
            return self.stop_line
        if self.cursor == 0:
            return None
        return (self.cursor - 1) // LETTERS_PER_LINE + 1

    @property
    def letters_correct(self) -> int:
        # Unmarked (not read) letters count as wrong.
        return sum(1 for m in self.marks if m is True)

    @property
    def logmar(self) -> float:
        return logmar_from_letters(self.letters_correct)


# --------------------------------------------------------------------------
# Results and CSV storage
# --------------------------------------------------------------------------

@dataclass
class EyeResult:
    subject_id: str
    session: str
    eye_tested: str       # "L" / "R"
    amblyopic_eye: str    # "L" / "R"
    test_order: int       # 1 = amblyopic eye, 2 = fellow eye
    form: str
    test: ChartTest
    line_logmar: List[float]
    ra_initials: str
    notes: str = ""
    timestamp: str = ""
    retest: bool = False  # set on save: True if it replaced an earlier test of this eye
    scheduled_form: str = ""  # form the counterbalancing schedule gave this visit+eye

    @property
    def eye_role(self) -> str:
        return "amblyopic" if self.eye_tested == self.amblyopic_eye else "fellow"

    def summary_row(self) -> Dict[str, str]:
        t = self.test
        stopped = t.stopped_at_line
        return {
            "subject_id": self.subject_id,
            "session": self.session,
            "eye_tested": self.eye_tested,
            "amblyopic_eye": self.amblyopic_eye,
            "eye_role": self.eye_role,
            "test_order": str(self.test_order),
            "retest": "yes" if self.retest else "no",
            "form": self.form,
            "scheduled_form": self.scheduled_form,
            "letters_correct": str(t.letters_correct),
            "letters_total": str(TOTAL_LETTERS),
            "logmar": format_logmar(t.logmar),
            "stopped_at_line": "" if stopped is None else str(stopped),
            "stop_reason": t.stop_reason or ENDED_EARLY,
            "ra_initials": self.ra_initials,
            "notes": self.notes,
            "timestamp": self.timestamp or now_iso(),
            "app_version": APP_VERSION,
        }

    def letter_rows(self) -> List[Dict[str, str]]:
        rows = []
        for i, letter in enumerate(self.test.letters):
            line = i // LETTERS_PER_LINE
            mark = self.test.marks[i]
            result = (RESULT_NOT_READ if mark is None
                      else RESULT_CORRECT if mark else RESULT_INCORRECT)
            rows.append({
                "subject_id": self.subject_id,
                "session": self.session,
                "eye_tested": self.eye_tested,
                "form": self.form,
                "line": str(line + 1),
                "line_logmar": f"{self.line_logmar[line]:.1f}",
                "position": str(i % LETTERS_PER_LINE + 1),
                "letter": letter,
                "result": result,
            })
        return rows


def now_iso() -> str:
    """Local time with UTC offset, e.g. 2026-10-27T14:03:12-04:00."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sanitize_filename_part(text: str) -> str:
    """Make text safe to use in a file name (letters, digits, '-', '_', '.')."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip()).strip("._")
    return cleaned or "blank"


def file_paths(folder: str, subject_id: str, session: str) -> Dict[str, str]:
    base = (f"{sanitize_filename_part(subject_id)}"
            f"_session{sanitize_filename_part(session)}")
    return {
        "summary": os.path.join(folder, base + "_summary.csv"),
        "letters": os.path.join(folder, base + "_letters.csv"),
    }


def read_rows(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding=CSV_ENCODING) as f:
        return list(csv.DictReader(f))


def write_rows(path: str, columns: List[str], rows: List[Dict[str, str]]) -> None:
    """Write the whole file to a temp file, then swap it in, so a crash
    mid-write never leaves a half-written CSV."""
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".etdrs_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", newline="", encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def saved_eyes(folder: str, subject_id: str, session: str) -> Dict[str, Dict[str, str]]:
    """Summary rows already saved for this subject+session, keyed by eye."""
    rows = read_rows(file_paths(folder, subject_id, session)["summary"])
    return {r.get("eye_tested", ""): r for r in rows if r.get("eye_tested") in EYES}


def other_eye(eye: str) -> str:
    return "R" if eye == "L" else "L"


class FormAlreadyUsedError(ValueError):
    pass


class EyeAlreadySavedError(Exception):
    pass


def blocked_forms(eye: str, folder: str, subject_id: str, session: str,
                  in_memory: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Forms that may not be used for `eye`: form -> eye that already used it.

    Looks at the other eye in this run of the app (`in_memory`, eye -> form)
    and in the saved summary file, so the rule holds after a restart.
    """
    blocked: Dict[str, str] = {}
    other = other_eye(eye)
    saved = saved_eyes(folder, subject_id, session).get(other)
    if saved and saved.get("form"):
        blocked[saved["form"]] = other
    if in_memory and in_memory.get(other):
        blocked[in_memory[other]] = other
    return blocked


def check_form_allowed(form: str, eye: str, folder: str, subject_id: str,
                       session: str, in_memory: Optional[Dict[str, str]] = None) -> None:
    """Raise FormAlreadyUsedError if `form` was already used in this session."""
    blocked = blocked_forms(eye, folder, subject_id, session, in_memory)
    if form in blocked:
        raise FormAlreadyUsedError(
            f"Form {form} was already used for the {EYE_NAMES[blocked[form]]} eye "
            f"at this visit. Each eye must be tested with a different form.")


def save_eye_result(folder: str, result: EyeResult, overwrite: bool = False) -> Dict[str, str]:
    """Save one eye's rows to the summary and letters CSVs.

    Rows for the other eye are kept (append). If this eye is already saved,
    raises EyeAlreadySavedError unless overwrite=True, in which case only
    this eye's rows are replaced. Returns the two file paths.
    """
    paths = file_paths(folder, result.subject_id, result.session)
    eye = result.eye_tested
    summary = read_rows(paths["summary"])
    letters = read_rows(paths["letters"])

    already = (any(r.get("eye_tested") == eye for r in summary)
               or any(r.get("eye_tested") == eye for r in letters))
    if already and not overwrite:
        raise EyeAlreadySavedError(
            f"{EYE_NAMES[eye]} eye is already saved for subject "
            f"{result.subject_id}, visit {result.session}.")

    check_form_allowed(result.form, eye, folder, result.subject_id, result.session)

    result.retest = already
    if not result.timestamp:
        result.timestamp = now_iso()
    summary = [r for r in summary if r.get("eye_tested") != eye] + [result.summary_row()]
    letters = [r for r in letters if r.get("eye_tested") != eye] + result.letter_rows()
    # Keep both files in test order (amblyopic eye first).
    summary.sort(key=lambda r: r.get("test_order", ""))
    eye_order = [r.get("eye_tested") for r in summary]
    letters.sort(key=lambda r: eye_order.index(r.get("eye_tested"))
                 if r.get("eye_tested") in eye_order else len(eye_order))

    os.makedirs(folder, exist_ok=True)
    write_rows(paths["summary"], SUMMARY_COLUMNS, summary)
    write_rows(paths["letters"], LETTER_COLUMNS, letters)
    return paths


# --------------------------------------------------------------------------
# Settings (remembers the last data folder)
# --------------------------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".etdrs_logger.json")
DEFAULT_DATA_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "ETDRS data")


def load_config(path: str = CONFIG_PATH) -> Dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(config: Dict[str, str], path: str = CONFIG_PATH) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass  # Not remembering the folder is not worth interrupting a test.
