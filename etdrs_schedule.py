"""Counterbalanced assignment of chart forms to visits and eyes.

Each participant gets a fixed schedule the first time they are tested, saying
which form the amblyopic eye (AE) and fellow eye (FE) get at every visit.

Schedules rotate through the forms. With forms A, B, C and five visits:

    AE:  A B C A B
    FE:  B C A B C     (FE one step ahead of AE)   or
    FE:  C A B C A     (FE one step behind AE)

so that
  - the two eyes never get the same form at a visit,
  - neither eye gets the same form at two visits in a row,
  - each eye's forms are as evenly used as possible (2, 2, 1 for 5 visits),
    and a repeated form comes back as late as possible (3 visits later),
  - consecutive visits share only one form (the fewest possible when each
    visit uses two of three forms).

The 6 ways of labelling A, B, C as forms 1, 2, 3, times the 2 FE offsets, give
12 schedules. New participants are given these in randomised blocks of 12
(each schedule once per block, in random order), so forms also stay balanced
across visits and eyes over the whole study.

Assignments are stored in ``form_assignments.csv`` in the data folder, one row
per participant, visit and eye.
"""

from __future__ import annotations

import itertools
import json
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import etdrs_core as core

ASSIGNMENTS_FILE = "form_assignments.csv"
ASSIGNMENT_COLUMNS = [
    "subject_id", "schedule_id", "visit_number", "visit", "eye_role", "form",
    "assigned_at", "ra_initials", "app_version",
]
ROLES = ("amblyopic", "fellow")


def load_visits(path: str) -> List[str]:
    with open(path, encoding="utf-8") as f:
        visits = [str(v).strip() for v in json.load(f)["visits"]]
    if not visits or any(not v for v in visits) or len(set(visits)) != len(visits):
        raise ValueError("study.json: 'visits' must be a list of distinct, non-blank names")
    return visits


@dataclass(frozen=True)
class Schedule:
    schedule_id: str          # e.g. "231+1": AE order 2,3,1; FE one step ahead
    order: tuple              # forms in AE rotation order
    fe_offset: int            # how many steps FE is ahead of AE in the rotation

    def form(self, visit_index: int, role: str) -> str:
        step = visit_index + (self.fe_offset if role == "fellow" else 0)
        return self.order[step % len(self.order)]


def all_schedules(forms: Sequence[str]) -> List[Schedule]:
    forms = list(forms)
    schedules = []
    for order in itertools.permutations(forms):
        for offset in range(1, len(forms)):
            schedules.append(Schedule(f"{''.join(order)}+{offset}", tuple(order), offset))
    return schedules


def subject_key(subject_id: str) -> str:
    # The Mac's file system ignores case, so "s01" and "S01" are the same files.
    return subject_id.strip().casefold()


def assignments_path(folder: str) -> str:
    return os.path.join(folder, ASSIGNMENTS_FILE)


def read_assignments(folder: str) -> List[Dict[str, str]]:
    return core.read_rows(assignments_path(folder))


def get_assignment(folder: str, subject_id: str) -> Optional[Dict[str, object]]:
    """The participant's saved schedule, or None if they don't have one yet.

    Returns {"schedule_id": str, "forms": {(visit, role): form}}.
    """
    key = subject_key(subject_id)
    rows = [r for r in read_assignments(folder) if subject_key(r.get("subject_id", "")) == key]
    if not rows:
        return None
    return {
        "schedule_id": rows[0].get("schedule_id", ""),
        "forms": {(r["visit"], r["eye_role"]): r["form"] for r in rows},
    }


def scheduled_form(assignment: Optional[Dict[str, object]], visit: str, role: str) -> Optional[str]:
    if not assignment:
        return None
    return assignment["forms"].get((visit, role))


def choose_schedule(schedules: List[Schedule], used_ids_in_order: List[str],
                    rng: random.Random) -> Schedule:
    """Blocked randomisation: each block of len(schedules) participants gets
    every schedule once, in random order."""
    block = len(schedules)
    in_current_block = used_ids_in_order[len(used_ids_in_order) // block * block:]
    remaining = [s for s in schedules if s.schedule_id not in in_current_block]
    return rng.choice(remaining or schedules)


def assign_schedule(folder: str, subject_id: str, visits: Sequence[str],
                    forms: Sequence[str], ra_initials: str = "",
                    rng: Optional[random.Random] = None) -> Dict[str, object]:
    """Give a new participant a schedule and save it. Returns it as get_assignment does."""
    existing = get_assignment(folder, subject_id)
    if existing:
        return existing
    rows = read_assignments(folder)
    used: List[str] = []
    seen = set()
    for r in rows:  # one schedule id per participant, in the order they were assigned
        key = subject_key(r.get("subject_id", ""))
        if key not in seen:
            seen.add(key)
            used.append(r.get("schedule_id", ""))

    schedule = choose_schedule(all_schedules(forms), used, rng or random.SystemRandom())
    stamp = core.now_iso()
    for i, visit in enumerate(visits):
        for role in ROLES:
            rows.append({
                "subject_id": subject_id.strip(),
                "schedule_id": schedule.schedule_id,
                "visit_number": str(i + 1),
                "visit": visit,
                "eye_role": role,
                "form": schedule.form(i, role),
                "assigned_at": stamp,
                "ra_initials": ra_initials,
                "app_version": core.APP_VERSION,
            })
    os.makedirs(folder, exist_ok=True)
    core.write_rows(assignments_path(folder), ASSIGNMENT_COLUMNS, rows)
    return get_assignment(folder, subject_id)
