"""Unit tests for etdrs_core. Run with: python3 -m unittest"""

import csv
import os
import shutil
import tempfile
import unittest

import etdrs_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS = core.load_charts(os.path.join(HERE, "charts.json"))


def new_test(form="1"):
    return core.ChartTest(CHARTS.forms[form])


def enter(test, keys):
    """Feed a string of y/h marks, as the RA would type them."""
    for k in keys:
        test.mark(k == "y")


def make_result(test, eye="L", amblyopic="L", form="1", subject="S01",
                session="1", notes=""):
    return core.EyeResult(
        subject_id=subject, session=session, eye_tested=eye,
        amblyopic_eye=amblyopic, test_order=1 if eye == amblyopic else 2,
        form=form, test=test, line_logmar=CHARTS.line_logmar,
        ra_initials="AB", notes=notes)


class ChartsTest(unittest.TestCase):
    def test_charts_shape(self):
        self.assertEqual(CHARTS.form_numbers(), ["1", "2", "3"])
        self.assertEqual(CHARTS.forms["1"][0], "COHZV")
        self.assertEqual(len(CHARTS.line_logmar), 14)
        self.assertAlmostEqual(CHARTS.line_logmar[0], 1.0)
        self.assertAlmostEqual(CHARTS.line_logmar[-1], -0.3)


class ScoringTest(unittest.TestCase):
    def test_logmar_formula(self):
        self.assertEqual(core.logmar_from_letters(0), 1.1)
        self.assertEqual(core.logmar_from_letters(5), 1.0)
        self.assertEqual(core.logmar_from_letters(37), 0.36)
        self.assertEqual(core.logmar_from_letters(55), 0.0)
        self.assertEqual(core.logmar_from_letters(70), -0.3)

    def test_no_negative_zero(self):
        self.assertEqual(core.format_logmar(core.logmar_from_letters(55)), "0.00")
        self.assertEqual(core.format_logmar(-0.0), "0.00")

    def test_running_score(self):
        t = new_test()
        enter(t, "yyyyy" "yyhyy")
        self.assertEqual(t.letters_correct, 9)
        self.assertAlmostEqual(t.logmar, 0.92)

    def test_not_read_counted_wrong(self):
        t = new_test()
        enter(t, "yyyyy" "yhhhy")  # stop rule fires on line 2
        self.assertTrue(t.stop_rule_met)
        self.assertEqual(t.marks.count(None), 60)
        self.assertEqual(t.letters_correct, 7)
        self.assertAlmostEqual(t.logmar, 1.1 - 0.02 * 7)

    def test_all_correct(self):
        t = new_test()
        enter(t, "y" * 70)
        self.assertTrue(t.chart_completed)
        self.assertEqual(t.stop_reason, core.COMPLETED_CHART)
        self.assertEqual(t.stopped_at_line, 14)
        self.assertAlmostEqual(t.logmar, -0.3)
        self.assertFalse(t.mark(True))  # nothing past the end


class StopRuleTest(unittest.TestCase):
    def test_constant(self):
        self.assertEqual(core.STOP_RULE_ERRORS, 3)

    def test_two_errors_continue(self):
        t = new_test()
        enter(t, "hhyyy")
        self.assertFalse(t.stop_rule_met)
        self.assertTrue(t.accepting_input)

    def test_three_errors_stop(self):
        t = new_test()
        enter(t, "yyyyy" "hyhyh")
        self.assertTrue(t.stop_rule_met)
        self.assertEqual(t.stop_line, 2)
        self.assertEqual(t.stopped_at_line, 2)
        self.assertEqual(t.stop_reason, core.STOP_RULE)
        self.assertFalse(t.accepting_input)
        self.assertFalse(t.mark(True))  # further y/h blocked
        self.assertEqual(t.cursor, 10)

    def test_five_errors_stop(self):
        t = new_test()
        enter(t, "hhhhh")
        self.assertEqual(t.stop_line, 1)
        self.assertEqual(t.letters_correct, 0)
        self.assertAlmostEqual(t.logmar, 1.1)

    def test_only_checked_when_line_finished(self):
        t = new_test()
        enter(t, "hhhh")  # 4 errors but line not finished yet
        self.assertFalse(t.stop_rule_met)
        self.assertTrue(t.mark(True))
        self.assertTrue(t.stop_rule_met)

    def test_right_click_edit_allowed_after_stop(self):
        t = new_test()
        enter(t, "hhhhh")
        self.assertEqual(t.cycle(20), True)  # can still edit
        self.assertEqual(t.letters_correct, 1)

    def test_right_click_fix_removes_stop(self):
        t = new_test()
        enter(t, "yyhhh")
        self.assertTrue(t.stop_rule_met)
        t.cycle(2)  # red -> unmarked
        t.cycle(2)  # unmarked -> green: now only 2 errors
        self.assertFalse(t.stop_rule_met)
        self.assertTrue(t.mark(True))

    def test_right_click_can_trigger_stop(self):
        t = new_test()
        enter(t, "yyhhy" "y")
        t.cycle(4)  # green -> red: line 1 now has 3 errors
        self.assertEqual(t.stop_line, 1)

    def test_stop_on_last_line(self):
        t = new_test()
        enter(t, "y" * 65 + "hhhyy")
        self.assertEqual(t.stop_reason, core.STOP_RULE)
        self.assertEqual(t.stopped_at_line, 14)


class UndoTest(unittest.TestCase):
    def test_undo_clears_last_mark(self):
        t = new_test()
        enter(t, "yh")
        self.assertTrue(t.undo())
        self.assertEqual(t.cursor, 1)
        self.assertEqual(t.marks[:2], [True, None])
        self.assertTrue(t.undo())
        self.assertEqual(t.cursor, 0)
        self.assertFalse(t.undo())  # nothing left

    def test_undo_reverses_stop(self):
        t = new_test()
        enter(t, "yyhhh")
        self.assertTrue(t.stop_rule_met)
        t.undo()
        self.assertFalse(t.stop_rule_met)
        t.mark(True)
        self.assertFalse(t.stop_rule_met)
        self.assertEqual(t.letters_correct, 3)

    def test_cycle_order(self):
        t = new_test()
        self.assertEqual(t.cycle(7), True)
        self.assertEqual(t.cycle(7), False)
        self.assertEqual(t.cycle(7), None)

    def test_end_early(self):
        t = new_test()
        enter(t, "yyyyy" "yy")
        t.end_early()
        self.assertEqual(t.stop_reason, core.ENDED_EARLY)
        self.assertEqual(t.stopped_at_line, 2)
        self.assertFalse(t.mark(True))
        self.assertFalse(t.undo())

    def test_resume_after_end_early(self):
        t = new_test()
        enter(t, "yyyyy" "yy")
        t.end_early()
        self.assertTrue(t.resume())
        self.assertFalse(t.is_over)
        self.assertIsNone(t.stop_reason)
        self.assertTrue(t.mark(True))  # carries on at line 2, letter 3
        self.assertEqual(t.cursor, 8)
        self.assertTrue(t.undo())

    def test_resume_only_undoes_end_early(self):
        t = new_test()
        self.assertFalse(t.resume())  # never ended
        enter(t, "hhhhh")
        self.assertFalse(t.resume())  # stop rule is not something to resume from
        self.assertTrue(t.stop_rule_met)


class CsvTestBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self, which, subject="S01", session="1"):
        path = core.file_paths(self.dir, subject, session)[which]
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))


class CsvOutputTest(CsvTestBase):
    def test_file_names_sanitized(self):
        paths = core.file_paths(self.dir, "S 01/../x", "2")
        self.assertEqual(os.path.basename(paths["summary"]), "S_01_.._x_session2_summary.csv")
        self.assertEqual(os.path.dirname(paths["summary"]), self.dir)
        self.assertEqual(core.sanitize_filename_part("  "), "blank")

    def test_summary_and_letters(self):
        t = new_test("2")
        enter(t, "yyyyy" "yhhhy")
        core.save_eye_result(self.dir, make_result(t, form="2", notes="tired, line 2"))

        summary = self.read("summary")
        self.assertEqual(len(summary), 1)
        row = summary[0]
        self.assertEqual(list(row), core.SUMMARY_COLUMNS)
        self.assertEqual(row["subject_id"], "S01")
        self.assertEqual(row["eye_tested"], "L")
        self.assertEqual(row["eye_role"], "amblyopic")
        self.assertEqual(row["test_order"], "1")
        self.assertEqual(row["retest"], "no")
        self.assertEqual(row["form"], "2")
        self.assertEqual(row["letters_correct"], "7")
        self.assertEqual(row["letters_total"], "70")
        self.assertEqual(row["logmar"], "0.96")
        self.assertEqual(row["stopped_at_line"], "2")
        self.assertEqual(row["stop_reason"], "stop_rule")
        self.assertEqual(row["ra_initials"], "AB")
        self.assertEqual(row["notes"], "tired, line 2")
        self.assertEqual(row["app_version"], core.APP_VERSION)
        self.assertRegex(row["timestamp"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

        letters = self.read("letters")
        self.assertEqual(len(letters), 70)
        self.assertEqual(list(letters[0]), core.LETTER_COLUMNS)
        self.assertEqual(letters[0]["letter"], "Z")
        self.assertEqual(letters[0]["line_logmar"], "1.0")
        self.assertEqual(letters[0]["result"], "correct")
        self.assertEqual(letters[6]["line"], "2")
        self.assertEqual(letters[6]["position"], "2")
        self.assertEqual(letters[6]["result"], "incorrect")
        self.assertEqual(letters[69]["line_logmar"], "-0.3")
        self.assertEqual(letters[69]["result"], "not_read")
        self.assertEqual(sum(r["result"] == "not_read" for r in letters), 60)


class OverwriteAppendTest(CsvTestBase):
    def test_append_other_eye(self):
        a = new_test("1"); enter(a, "hhhhh")
        f = new_test("3"); enter(f, "y" * 70)
        core.save_eye_result(self.dir, make_result(a, eye="R", amblyopic="R", form="1"))
        core.save_eye_result(self.dir, make_result(f, eye="L", amblyopic="R", form="3"))
        summary = self.read("summary")
        self.assertEqual([r["eye_tested"] for r in summary], ["R", "L"])
        self.assertEqual([r["eye_role"] for r in summary], ["amblyopic", "fellow"])
        letters = self.read("letters")
        self.assertEqual(len(letters), 140)
        self.assertEqual({r["eye_tested"] for r in letters[:70]}, {"R"})

    def test_existing_eye_needs_confirmation(self):
        t = new_test(); enter(t, "hhhhh")
        core.save_eye_result(self.dir, make_result(t))
        with self.assertRaises(core.EyeAlreadySavedError):
            core.save_eye_result(self.dir, make_result(t))

    def test_overwrite_replaces_only_that_eye(self):
        a = new_test("1"); enter(a, "hhhhh")
        f = new_test("2"); enter(f, "y" * 70)
        core.save_eye_result(self.dir, make_result(a, eye="L", form="1"))
        core.save_eye_result(self.dir, make_result(f, eye="R", form="2"))

        redo = new_test("3"); enter(redo, "yyyyy" "hhhhh")
        core.save_eye_result(self.dir, make_result(redo, eye="L", form="3"), overwrite=True)

        summary = self.read("summary")
        self.assertEqual(len(summary), 2)
        by_eye = {r["eye_tested"]: r for r in summary}
        self.assertEqual(by_eye["L"]["form"], "3")
        self.assertEqual(by_eye["L"]["letters_correct"], "5")
        self.assertEqual(by_eye["L"]["retest"], "yes")
        self.assertEqual(by_eye["R"]["letters_correct"], "70")
        self.assertEqual(by_eye["R"]["retest"], "no")
        letters = self.read("letters")
        self.assertEqual(len(letters), 140)
        self.assertEqual({r["form"] for r in letters if r["eye_tested"] == "L"}, {"3"})
        self.assertEqual({r["form"] for r in letters if r["eye_tested"] == "R"}, {"2"})

    def test_saved_eyes(self):
        t = new_test(); enter(t, "hhhhh")
        self.assertEqual(core.saved_eyes(self.dir, "S01", "1"), {})
        core.save_eye_result(self.dir, make_result(t))
        self.assertEqual(list(core.saved_eyes(self.dir, "S01", "1")), ["L"])
        self.assertEqual(core.saved_eyes(self.dir, "S01", "2"), {})


class SameFormTest(CsvTestBase):
    def test_in_memory_rejection(self):
        with self.assertRaises(core.FormAlreadyUsedError):
            core.check_form_allowed("2", "R", self.dir, "S01", "1", in_memory={"L": "2"})
        core.check_form_allowed("3", "R", self.dir, "S01", "1", in_memory={"L": "2"})

    def test_rejection_from_saved_file_after_restart(self):
        t = new_test("2"); enter(t, "hhhhh")
        core.save_eye_result(self.dir, make_result(t, eye="L", form="2"))
        # Fresh start: nothing in memory, but the summary file knows.
        self.assertEqual(core.blocked_forms("R", self.dir, "S01", "1"), {"2": "L"})
        with self.assertRaises(core.FormAlreadyUsedError):
            core.check_form_allowed("2", "R", self.dir, "S01", "1")
        # A different session is unaffected.
        core.check_form_allowed("2", "R", self.dir, "S01", "2")

    def test_save_rejects_same_form(self):
        a = new_test("2"); enter(a, "hhhhh")
        core.save_eye_result(self.dir, make_result(a, eye="L", form="2"))
        b = new_test("2"); enter(b, "hhhhh")
        with self.assertRaises(core.FormAlreadyUsedError):
            core.save_eye_result(self.dir, make_result(b, eye="R", form="2"))
        self.assertEqual(len(self.read("summary")), 1)

    def test_retesting_same_eye_may_reuse_its_form(self):
        a = new_test("2"); enter(a, "hhhhh")
        core.save_eye_result(self.dir, make_result(a, eye="L", form="2"))
        self.assertEqual(core.blocked_forms("L", self.dir, "S01", "1"), {})


class ConfigTest(CsvTestBase):
    def test_round_trip_and_missing(self):
        path = os.path.join(self.dir, "cfg.json")
        self.assertEqual(core.load_config(path), {})
        core.save_config({"data_folder": "/x"}, path)
        self.assertEqual(core.load_config(path), {"data_folder": "/x"})
        with open(path, "w") as f:
            f.write("not json")
        self.assertEqual(core.load_config(path), {})


if __name__ == "__main__":
    unittest.main()
