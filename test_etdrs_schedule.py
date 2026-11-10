"""Unit tests for etdrs_schedule. Run with: python3 -m unittest"""

import os
import random
import shutil
import tempfile
import unittest
from collections import Counter

import etdrs_core as core
import etdrs_schedule as sched

HERE = os.path.dirname(os.path.abspath(__file__))
VISITS = sched.load_visits(os.path.join(HERE, "study.json"))
FORMS = core.load_charts(os.path.join(HERE, "charts.json")).form_numbers()
SCHEDULES = sched.all_schedules(FORMS)


def sequence(schedule, role, n=len(VISITS)):
    return [schedule.form(v, role) for v in range(n)]


class StudyFileTest(unittest.TestCase):
    def test_visits(self):
        self.assertEqual(VISITS, ["prep1a", "S2 prep", "2-weeks S2", "4-weeks S2", "8-weeks S2"])

    def test_bad_study_file(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "study.json")
            with open(path, "w") as f:
                f.write('{"visits": ["a", "a"]}')
            with self.assertRaises(ValueError):
                sched.load_visits(path)
        finally:
            shutil.rmtree(d)


class ScheduleDesignTest(unittest.TestCase):
    def test_twelve_distinct_schedules(self):
        self.assertEqual(len(SCHEDULES), 12)
        full = {tuple(sequence(s, "amblyopic") + sequence(s, "fellow")) for s in SCHEDULES}
        self.assertEqual(len(full), 12)

    def test_eyes_differ_within_each_visit(self):
        for s in SCHEDULES:
            for v in range(len(VISITS)):
                self.assertNotEqual(s.form(v, "amblyopic"), s.form(v, "fellow"), s)

    def test_no_eye_repeats_a_form_at_consecutive_visits(self):
        for s in SCHEDULES:
            for role in sched.ROLES:
                seq = sequence(s, role)
                for a, b in zip(seq, seq[1:]):
                    self.assertNotEqual(a, b, (s, role))

    def test_each_eye_uses_forms_as_evenly_as_possible(self):
        for s in SCHEDULES:
            for role in sched.ROLES:
                counts = Counter(sequence(s, role))
                self.assertEqual(sorted(counts.values()), [1, 2, 2], (s, role))

    def test_repeats_are_as_far_apart_as_possible(self):
        for s in SCHEDULES:
            for role in sched.ROLES:
                seq = sequence(s, role)
                for form in set(seq):
                    visits = [i for i, f in enumerate(seq) if f == form]
                    for a, b in zip(visits, visits[1:]):
                        self.assertEqual(b - a, 3, (s, role, form))

    def test_consecutive_visits_share_only_one_form(self):
        for s in SCHEDULES:
            for v in range(len(VISITS) - 1):
                this = {s.form(v, r) for r in sched.ROLES}
                nxt = {s.form(v + 1, r) for r in sched.ROLES}
                self.assertEqual(len(this & nxt), 1, s)

    def test_whole_set_is_balanced_across_participants(self):
        # Over one block of 12, each form appears equally often at every visit and eye.
        for v in range(len(VISITS)):
            for role in sched.ROLES:
                counts = Counter(s.form(v, role) for s in SCHEDULES)
                self.assertEqual(set(counts.values()), {4}, (v, role))


class AssignmentTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.rng = random.Random(1)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def assign(self, subject):
        return sched.assign_schedule(self.dir, subject, VISITS, FORMS, "AB", self.rng)

    def test_new_subject_gets_saved_schedule(self):
        self.assertIsNone(sched.get_assignment(self.dir, "S01"))
        a = self.assign("S01")
        self.assertEqual(len(a["forms"]), 10)
        rows = sched.read_assignments(self.dir)
        self.assertEqual(len(rows), 10)
        self.assertEqual(list(rows[0]), sched.ASSIGNMENT_COLUMNS)
        self.assertEqual(rows[0]["visit"], "prep1a")
        self.assertEqual(rows[0]["eye_role"], "amblyopic")
        self.assertEqual(rows[-1]["visit_number"], "5")
        self.assertEqual(sched.get_assignment(self.dir, "S01"), a)

    def test_schedule_is_fixed_once_assigned(self):
        a = self.assign("S01")
        self.assertEqual(self.assign("S01"), a)
        self.assertEqual(self.assign("  s01 "), a)  # same participant, typed differently
        self.assertEqual(len(sched.read_assignments(self.dir)), 10)

    def test_scheduled_form_lookup(self):
        a = self.assign("S01")
        s = next(x for x in SCHEDULES if x.schedule_id == a["schedule_id"])
        self.assertEqual(sched.scheduled_form(a, "S2 prep", "fellow"), s.form(1, "fellow"))
        self.assertIsNone(sched.scheduled_form(a, "not a visit", "fellow"))
        self.assertIsNone(sched.scheduled_form(None, "prep1a", "amblyopic"))

    def test_blocked_randomisation(self):
        ids = [self.assign(f"S{i:02d}")["schedule_id"] for i in range(24)]
        self.assertEqual(len(set(ids[:12])), 12)   # first block uses every schedule once
        self.assertEqual(len(set(ids[12:])), 12)   # and so does the second
        self.assertNotEqual(ids[:12], ids[12:])    # in a fresh random order

    def test_order_is_random(self):
        other = tempfile.mkdtemp()
        try:
            first = [self.assign(f"S{i}")["schedule_id"] for i in range(12)]
            rng2 = random.Random(2)
            second = [sched.assign_schedule(other, f"S{i}", VISITS, FORMS, "", rng2)["schedule_id"]
                      for i in range(12)]
            self.assertNotEqual(first, second)
        finally:
            shutil.rmtree(other)


class ScheduledFormColumnTest(unittest.TestCase):
    def test_summary_records_scheduled_form(self):
        d = tempfile.mkdtemp()
        try:
            charts = core.load_charts(os.path.join(HERE, "charts.json"))
            t = core.ChartTest(charts.forms["2"])
            for _ in range(5):
                t.mark(False)
            result = core.EyeResult(
                subject_id="S01", session="prep1a", eye_tested="L", amblyopic_eye="L",
                test_order=1, form="2", test=t, line_logmar=charts.line_logmar,
                ra_initials="AB", scheduled_form="3")
            core.save_eye_result(d, result)
            row = core.read_rows(core.file_paths(d, "S01", "prep1a")["summary"])[0]
            self.assertEqual(row["form"], "2")
            self.assertEqual(row["scheduled_form"], "3")
            self.assertEqual(os.path.basename(core.file_paths(d, "S01", "S2 prep")["summary"]),
                             "S01_sessionS2_prep_summary.csv")
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
