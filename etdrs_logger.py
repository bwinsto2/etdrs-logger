#!/usr/bin/env python3
"""ETDRS Logger: log letter-by-letter ETDRS acuity responses and score logMAR.

Run with:  python3 etdrs_logger.py
Scoring, the stop rule and CSV saving live in etdrs_core.py.
"""

from __future__ import annotations

import os
import sys

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - depends on the Python install
    sys.exit("This Python has no tkinter. Install Python 3 from python.org "
             "(it includes tkinter) and try again.")

import etdrs_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS_PATH = os.path.join(HERE, "charts.json")

FAMILY = "Helvetica"
FONT = (FAMILY, 18)
FONT_BOLD = (FAMILY, 18, "bold")
FONT_SMALL = (FAMILY, 14)
FONT_TITLE = (FAMILY, 28, "bold")
FONT_BIG = (FAMILY, 24, "bold")

BG = "#ffffff"
ROLE_COLORS = {"amblyopic": "#5b2a86", "fellow": "#00695c"}
STOP_RED = "#c62828"

# Letter colours on the chart: (text, background)
UNMARKED = ("#111111", BG)
CORRECT = ("#1b7d1b", "#c9f2c7")
WRONG = ("#c00000", "#ffd3d3")
CURSOR_COLOR = "#1f6feb"

# Smallest line is drawn at this fraction of the largest, so the bottom of the
# chart shrinks like the real one but stays readable on a laptop.
SMALLEST_LINE_RATIO = 0.4
MAX_LETTER_PX = 64
MIN_LETTER_PX = 15


def eye_label(eye: str, amblyopic_eye: str) -> str:
    role = "amblyopic" if eye == amblyopic_eye else "fellow"
    return f"Testing: {core.EYE_NAMES[eye]} eye ({role})"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ETDRS Logger")
        self.configure(bg=BG)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1300, sw - 40), min(860, sh - 80)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+10")
        self.minsize(1000, 680)
        self.option_add("*TCombobox*Listbox.font", FONT)

        self.charts = core.load_charts(CHARTS_PATH)
        self.config_data = core.load_config()
        self.screen: tk.Frame | None = None
        self.chart_screen: ChartScreen | None = None

        # Current session
        self.subject_id = ""
        self.session = ""
        self.amblyopic_eye = ""
        self.ra_initials = ""
        self.data_folder = self.config_data.get("data_folder", core.DEFAULT_DATA_FOLDER)
        self.forms_used: dict[str, str] = {}

        self.bind("<KeyPress>", self.on_key)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_setup()

    # --- navigation ----------------------------------------------------

    def show(self, frame: tk.Frame) -> None:
        if self.screen is not None:
            self.screen.destroy()
        self.screen = frame
        self.chart_screen = frame if isinstance(frame, ChartScreen) else None
        frame.pack(fill="both", expand=True)

    def show_setup(self, keep=None) -> None:
        self.forms_used = {}
        self.show(SetupScreen(self, keep or {}))

    @property
    def eye_order(self) -> list[str]:
        return [self.amblyopic_eye, core.other_eye(self.amblyopic_eye)]

    def show_form_select(self, order: int) -> None:
        self.show(FormScreen(self, order))

    def show_chart(self, order: int, form: str) -> None:
        self.show(ChartScreen(self, order, form))

    def show_summary(self) -> None:
        self.show(SummaryScreen(self))

    def start_session(self, subject_id, session, amblyopic_eye, ra_initials, folder):
        self.subject_id, self.session = subject_id, session
        self.amblyopic_eye, self.ra_initials = amblyopic_eye, ra_initials
        self.data_folder = folder
        self.forms_used = {}
        self.config_data["data_folder"] = folder
        core.save_config(self.config_data)

        saved = core.saved_eyes(folder, subject_id, session)
        start_order = 0
        if saved:
            others = {r.get("amblyopic_eye") for r in saved.values()} - {amblyopic_eye}
            if others and not messagebox.askyesno(
                    "Check amblyopic eye",
                    f"Data already saved for subject {subject_id}, session {session} "
                    f"says the amblyopic eye is {others.pop()}, but you entered "
                    f"{amblyopic_eye}.\n\nContinue anyway?", icon="warning"):
                return
            amb, fel = self.eye_order
            if amb in saved and fel not in saved:
                form = saved[amb].get("form", "?")
                if messagebox.askyesno(
                        "Amblyopic eye already saved",
                        f"The amblyopic eye ({core.EYE_NAMES[amb]}) is already saved "
                        f"for this session (form {form}).\n\n"
                        f"Yes = go on to the fellow eye.\n"
                        f"No = test the amblyopic eye again."):
                    start_order = 1
            elif amb in saved and fel in saved:
                if not messagebox.askyesno(
                        "Session already saved",
                        f"Both eyes are already saved for subject {subject_id}, "
                        f"session {session}.\n\nTest again? You will be asked "
                        f"before anything is overwritten.", icon="warning"):
                    return
        self.show_form_select(start_order)

    # --- events ----------------------------------------------------------

    def on_key(self, event) -> None:
        # Typing in a text box (notes, subject ID...) must never grade letters.
        if isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry)):
            return
        if self.chart_screen is not None:
            self.chart_screen.on_key(event)

    def on_close(self) -> None:
        if (self.chart_screen is not None and self.chart_screen.has_unsaved_data()
                and not messagebox.askyesno(
                    "Quit?", "This eye has NOT been saved.\n\nQuit anyway and lose it?",
                    icon="warning")):
            return
        self.destroy()


class SetupScreen(tk.Frame):
    def __init__(self, app: App, keep: dict):
        super().__init__(app, bg=BG, padx=40, pady=30)
        self.app = app
        tk.Label(self, text="ETDRS Logger", font=FONT_TITLE, bg=BG).pack(anchor="w")
        tk.Label(self, text="New session", font=FONT, bg=BG, fg="#555").pack(anchor="w", pady=(0, 20))

        form = tk.Frame(self, bg=BG)
        form.pack(anchor="w")
        self.subject = tk.StringVar(value=keep.get("subject", ""))
        self.session = tk.StringVar(value=keep.get("session", ""))
        self.eye = tk.StringVar(value=keep.get("eye", ""))
        self.ra = tk.StringVar(value=keep.get("ra", ""))
        self.folder = tk.StringVar(value=app.data_folder)

        def row(r, label):
            tk.Label(form, text=label, font=FONT_BOLD, bg=BG).grid(
                row=r, column=0, sticky="w", pady=10, padx=(0, 20))

        row(0, "Subject ID")
        first = tk.Entry(form, textvariable=self.subject, font=FONT, width=20)
        first.grid(row=0, column=1, sticky="w")
        row(1, "Visit / session")
        tk.Entry(form, textvariable=self.session, font=FONT, width=10).grid(row=1, column=1, sticky="w")
        row(2, "Amblyopic eye")
        ttk.Combobox(form, textvariable=self.eye, values=list(core.EYES), state="readonly",
                     font=FONT, width=5).grid(row=2, column=1, sticky="w")
        row(3, "RA initials")
        tk.Entry(form, textvariable=self.ra, font=FONT, width=6).grid(row=3, column=1, sticky="w")
        row(4, "Data folder")
        folder_row = tk.Frame(form, bg=BG)
        folder_row.grid(row=4, column=1, sticky="w")
        tk.Label(folder_row, textvariable=self.folder, font=FONT_SMALL, bg="#f2f2f2",
                 anchor="w", width=55, padx=6, pady=4).pack(side="left")
        tk.Button(folder_row, text="Choose…", font=FONT_SMALL,
                  command=self.choose_folder).pack(side="left", padx=10)

        tk.Button(self, text="Start testing  ▶", font=FONT_BIG, padx=20, pady=10,
                  command=self.start).pack(anchor="w", pady=30)
        tk.Label(self, text="The amblyopic eye is tested first, then the fellow eye.",
                 font=FONT_SMALL, bg=BG, fg="#555").pack(anchor="w")
        first.focus_set()

    def choose_folder(self) -> None:
        start = self.folder.get()
        path = filedialog.askdirectory(
            parent=self, title="Choose the folder to save data in",
            initialdir=start if os.path.isdir(start) else os.path.expanduser("~"))
        if path:
            self.folder.set(path)

    def start(self) -> None:
        subject, session = self.subject.get().strip(), self.session.get().strip()
        eye, ra = self.eye.get().strip(), self.ra.get().strip().upper()
        folder = self.folder.get().strip()
        missing = [name for name, value in (("Subject ID", subject), ("Visit / session", session),
                                            ("Amblyopic eye", eye), ("RA initials", ra),
                                            ("Data folder", folder)) if not value]
        if missing:
            messagebox.showerror("Missing information", "Please fill in:\n\n" + "\n".join(missing))
            return
        if not os.path.isdir(folder):
            if not messagebox.askyesno("Create folder?", f"The folder\n\n{folder}\n\n"
                                       "does not exist. Create it?"):
                return
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Could not create folder", str(e))
                return
        self.app.start_session(subject, session, eye, ra, folder)


def eye_header(parent, app: App, eye: str) -> tk.Frame:
    role = "amblyopic" if eye == app.amblyopic_eye else "fellow"
    bar = tk.Frame(parent, bg=ROLE_COLORS[role], padx=20, pady=10)
    tk.Label(bar, text=eye_label(eye, app.amblyopic_eye), font=FONT_TITLE,
             bg=ROLE_COLORS[role], fg="white").pack(side="left")
    tk.Label(bar, text=f"Subject {app.subject_id}   ·   Session {app.session}   ·   RA {app.ra_initials}",
             font=FONT, bg=ROLE_COLORS[role], fg="white").pack(side="right")
    return bar


class FormScreen(tk.Frame):
    def __init__(self, app: App, order: int):
        super().__init__(app, bg=BG)
        self.app, self.order = app, order
        self.eye = app.eye_order[order]
        eye_header(self, app, self.eye).pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=40, pady=30)
        body.pack(fill="both", expand=True)
        step = "Eye 1 of 2" if order == 0 else "Eye 2 of 2"
        tk.Label(body, text=f"{step}: choose the chart form", font=FONT_BIG, bg=BG).pack(anchor="w")
        tk.Label(body, text="Match the first line to the physical chart. "
                 "Each eye must use a different form.",
                 font=FONT, bg=BG, fg="#555").pack(anchor="w", pady=(4, 20))

        self.blocked = core.blocked_forms(self.eye, app.data_folder, app.subject_id,
                                          app.session, app.forms_used)
        for form in app.charts.form_numbers():
            first_line = " ".join(app.charts.forms[form][0])
            text = f"Form {form}   —   {first_line}"
            if form in self.blocked:
                text += f"\n(already used for {core.EYE_NAMES[self.blocked[form]]} eye)"
            tk.Button(body, text=text, font=(FAMILY, 30, "bold"), width=26, pady=12,
                      state="disabled" if form in self.blocked else "normal",
                      command=lambda f=form: self.choose(f)).pack(anchor="w", pady=8)

        tk.Button(body, text="◀  Back to start", font=FONT_SMALL,
                  command=self.back).pack(anchor="w", pady=(30, 0))

    def choose(self, form: str) -> None:
        try:
            core.check_form_allowed(form, self.eye, self.app.data_folder, self.app.subject_id,
                                    self.app.session, self.app.forms_used)
        except core.FormAlreadyUsedError as e:
            messagebox.showerror("Form already used", str(e))
            return
        self.app.show_chart(self.order, form)

    def back(self) -> None:
        msg = "Go back to the start screen?"
        if self.order == 1:
            msg += "\n\nThe first eye is already saved."
        if messagebox.askyesno("Back to start", msg):
            self.app.show_setup(self.keep())

    def keep(self):
        return {"subject": self.app.subject_id, "session": self.app.session,
                "eye": self.app.amblyopic_eye, "ra": self.app.ra_initials}


class ChartScreen(tk.Frame):
    def __init__(self, app: App, order: int, form: str):
        super().__init__(app, bg=BG)
        self.app, self.order, self.form = app, order, form
        self.eye = app.eye_order[order]
        self.test = core.ChartTest(app.charts.forms[form])
        self.started = False
        self.saved = False
        self.was_over = False
        self.boxes: list[tuple[int, int, int, int]] = []

        eye_header(self, app, self.eye).pack(fill="x")
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)

        # Right-hand control panel
        panel = tk.Frame(main, bg="#f5f5f5", padx=18, pady=14, width=380)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)
        tk.Label(panel, text=f"Form {form}", font=FONT_BIG, bg="#f5f5f5").pack(anchor="w")

        self.go_btn = tk.Button(panel, text="Go", font=(FAMILY, 30, "bold"), width=8,
                                command=self.go)
        self.go_btn.pack(anchor="w", pady=(8, 8))
        self.status = tk.Label(panel, text="Press Go when the participant is ready.",
                               font=FONT_BOLD, bg="#f5f5f5", wraplength=340,
                               justify="left", anchor="w")
        self.status.pack(anchor="w", fill="x")

        self.totals = tk.Label(panel, text="", font=FONT_BIG, bg="#f5f5f5", justify="left")
        self.totals.pack(anchor="w", pady=10)

        tk.Label(panel, font=FONT_SMALL, bg="#f5f5f5", justify="left", fg="#333",
                 text="y  = correct (green)\n"
                      "h  = wrong (red)\n"
                      "Backspace / delete  = undo last\n"
                      "Right-click or Ctrl-click a letter\n"
                      "     = change it (blank → green → red)").pack(anchor="w")

        self.end_btn = tk.Button(panel, text="End test early…", font=FONT_SMALL,
                                 command=self.end_early, state="disabled")
        self.end_btn.pack(anchor="w", pady=(10, 10))

        tk.Label(panel, text="Notes", font=FONT_BOLD, bg="#f5f5f5").pack(anchor="w")
        self.notes = tk.Text(panel, font=FONT_SMALL, height=4, width=30, wrap="word",
                             state="disabled", bg="#eeeeee")
        self.notes.pack(anchor="w", fill="x")
        self.submit_btn = tk.Button(panel, text="Submit this eye  ✔", font=FONT_BIG,
                                    command=self.submit, state="disabled")
        self.submit_btn.pack(anchor="w", pady=12)

        # Chart
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        self.banner = tk.Label(left, text="", font=FONT_BIG, bg=BG, fg="white")
        self.banner.pack(fill="x")
        self.canvas = tk.Canvas(left, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            self.canvas.bind(seq, self.on_right_click)
        self.update_panel()

    # --- drawing ---------------------------------------------------------

    def layout(self, width: int, height: int):
        """Letter pixel heights for each line, sized to fit the canvas."""
        ratio = SMALLEST_LINE_RATIO ** (1 / (core.NUM_LINES - 1))
        pitch_factor = 1.45  # line pitch / letter height
        rel = [ratio ** i for i in range(core.NUM_LINES)]
        by_height = (height - 10) / (pitch_factor * sum(rel))
        by_width = (width - 120) / 10  # 5 letters + 5 letter-widths of gaps
        top = max(MIN_LETTER_PX / SMALLEST_LINE_RATIO, min(MAX_LETTER_PX, by_height, by_width))
        return [max(MIN_LETTER_PX, int(top * r)) for r in rel], pitch_factor

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        sizes, pitch_factor = self.layout(w, h)
        logmar_font = tkfont.Font(family=FAMILY, size=-15)
        cx = 70 + (w - 70) / 2
        y = 5
        self.boxes = []
        cursor_idx = self.test.cursor if (self.started and self.test.accepting_input) else None
        for line, px in enumerate(sizes):
            pitch = px * pitch_factor
            font = tkfont.Font(family=FAMILY, size=-px, weight="bold")
            mid = y + pitch / 2
            c.create_text(8, mid, text=f"{self.app.charts.line_logmar[line]:+.1f}".replace("+", " "),
                          anchor="w", font=logmar_font, fill="#888")
            step = px * 2  # letter width + one letter-width gap, like ETDRS spacing
            for pos in range(core.LETTERS_PER_LINE):
                idx = line * core.LETTERS_PER_LINE + pos
                x = cx + (pos - 2) * step
                half = px * 0.68
                box = (int(x - half), int(mid - half), int(x + half), int(mid + half))
                self.boxes.append(box)
                mark = self.test.marks[idx]
                fg, bg = UNMARKED if mark is None else (CORRECT if mark else WRONG)
                if bg != BG:
                    c.create_rectangle(*box, fill=bg, outline="")
                c.create_text(x, mid, text=self.test.letters[idx], font=font, fill=fg)
                if idx == cursor_idx:
                    c.create_rectangle(box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3,
                                       outline=CURSOR_COLOR, width=4)
            if self.test.stop_line == line + 1:
                c.create_text(w - 4, mid, text="◀ STOP", anchor="e", font=FONT_BOLD, fill=STOP_RED)
            y += pitch

    def update_panel(self) -> None:
        t = self.test
        self.totals.config(text=f"Correct: {t.letters_correct} / {core.TOTAL_LETTERS}\n"
                                f"logMAR:  {core.format_logmar(t.logmar)}")
        if t.is_over:
            if t.stop_reason == core.STOP_RULE:
                msg = f"STOP — {core.STOP_RULE_ERRORS}+ wrong on line {t.stop_line}. Test over for this eye."
                self.banner.config(text=msg, bg=STOP_RED)
            elif t.stop_reason == core.COMPLETED_CHART:
                self.banner.config(text="All 14 lines read — test complete.", bg="#2e7d32")
            else:
                self.banner.config(text="Test ended early.", bg="#ef6c00")
            self.status.config(text="Check the marks (right-click to fix), add notes, then Submit.",
                               fg="#000")
            self.notes.config(state="normal", bg="white")
            self.submit_btn.config(state="normal")
            self.end_btn.config(state="disabled")
        else:
            self.banner.config(text="", bg=BG)
            self.submit_btn.config(state="disabled")
            self.notes.config(state="disabled", bg="#eeeeee")
            if self.started:
                line = t.cursor // core.LETTERS_PER_LINE + 1
                self.status.config(text=f"Testing line {line} of 14", fg=CURSOR_COLOR)
                self.end_btn.config(state="normal")

    def refresh(self) -> None:
        self.redraw()
        self.update_panel()
        over = self.test.is_over
        if over and not self.was_over:
            self.was_over = True
            self.after_idle(self.announce_end)
        elif not over:
            self.was_over = False

    def announce_end(self) -> None:
        t = self.test
        if t.stop_reason == core.STOP_RULE:
            messagebox.showwarning(
                "STOP TESTING",
                f"{t.line_errors(t.stop_line - 1)} letters wrong on line {t.stop_line}.\n\n"
                f"STOP TESTING — the task is over for this eye.\n\n"
                f"Letters correct: {t.letters_correct}    logMAR: {core.format_logmar(t.logmar)}",
                parent=self)
        elif t.stop_reason == core.COMPLETED_CHART:
            messagebox.showinfo(
                "Test complete",
                f"All 14 lines read — the test is over for this eye.\n\n"
                f"Letters correct: {t.letters_correct}    logMAR: {core.format_logmar(t.logmar)}",
                parent=self)

    # --- input -----------------------------------------------------------

    def go(self) -> None:
        self.started = True
        self.go_btn.config(state="disabled")
        self.canvas.focus_set()
        self.refresh()

    def on_key(self, event) -> None:
        if not self.started:
            return
        key = event.keysym.lower()
        if key in ("y", "h"):
            if self.test.mark(key == "y"):
                self.refresh()
            else:
                self.bell()
        elif key in ("backspace", "delete"):
            if self.test.undo():
                self.refresh()

    def on_right_click(self, event) -> str:
        if not self.started:
            return "break"
        for idx, (x0, y0, x1, y1) in enumerate(self.boxes):
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self.test.cycle(idx)
                self.refresh()
                break
        return "break"

    def end_early(self) -> None:
        if messagebox.askyesno("End test early?",
                               "End the test for this eye now?\n\n"
                               "Letters not yet read will count as wrong.", parent=self):
            self.test.end_early()
            self.refresh()

    def has_unsaved_data(self) -> bool:
        return self.started and not self.saved

    def submit(self) -> None:
        app = self.app
        result = core.EyeResult(
            subject_id=app.subject_id, session=app.session, eye_tested=self.eye,
            amblyopic_eye=app.amblyopic_eye, test_order=self.order + 1, form=self.form,
            test=self.test, line_logmar=app.charts.line_logmar,
            ra_initials=app.ra_initials, notes=self.notes.get("1.0", "end").strip())
        try:
            try:
                core.save_eye_result(app.data_folder, result)
            except core.EyeAlreadySavedError:
                if not messagebox.askyesno(
                        "Overwrite?",
                        f"The {core.EYE_NAMES[self.eye]} eye is already saved for subject "
                        f"{app.subject_id}, session {app.session}.\n\n"
                        f"Replace the saved {core.EYE_NAMES[self.eye]} eye data with this test?\n"
                        f"(The other eye's data is kept.)", icon="warning", parent=self):
                    return
                core.save_eye_result(app.data_folder, result, overwrite=True)
        except core.FormAlreadyUsedError as e:
            messagebox.showerror("Form already used", str(e), parent=self)
            return
        except OSError as e:
            messagebox.showerror("Could not save",
                                 f"The data could NOT be saved:\n\n{e}\n\n"
                                 "Check the data folder and try again.", parent=self)
            return
        self.saved = True
        app.forms_used[self.eye] = self.form
        if self.order == 0:
            app.show_form_select(1)
        else:
            app.show_summary()


class SummaryScreen(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app, bg=BG, padx=40, pady=30)
        self.app = app
        tk.Label(self, text="Session complete", font=FONT_TITLE, bg=BG).pack(anchor="w")
        tk.Label(self, text=f"Subject {app.subject_id}   ·   Session {app.session}   ·   "
                 f"Amblyopic eye {app.amblyopic_eye}   ·   RA {app.ra_initials}",
                 font=FONT, bg=BG).pack(anchor="w", pady=(4, 20))

        table = tk.Frame(self, bg=BG)
        table.pack(anchor="w")
        headings = ["Eye", "Role", "Form", "Letters correct", "logMAR", "Stopped", "Line"]
        for col, text in enumerate(headings):
            tk.Label(table, text=text, font=FONT_BOLD, bg=BG, padx=12).grid(row=0, column=col, sticky="w")
        saved = core.saved_eyes(app.data_folder, app.subject_id, app.session)
        reasons = {core.STOP_RULE: "stop rule", core.COMPLETED_CHART: "completed chart",
                   core.ENDED_EARLY: "ended early"}
        for r, eye in enumerate(app.eye_order, start=1):
            row = saved.get(eye)
            values = ([core.EYE_NAMES[eye], row.get("eye_role", ""), row.get("form", ""),
                       f"{row.get('letters_correct', '')} / {row.get('letters_total', '')}",
                       row.get("logmar", ""), reasons.get(row.get("stop_reason"), ""),
                       row.get("stopped_at_line", "")]
                      if row else [core.EYE_NAMES[eye], "not saved", "", "", "", "", ""])
            for col, text in enumerate(values):
                tk.Label(table, text=text, font=(FAMILY, 24 if col == 4 else 18), bg=BG,
                         padx=12, pady=6).grid(row=r, column=col, sticky="w")

        paths = core.file_paths(app.data_folder, app.subject_id, app.session)
        tk.Label(self, text="Saved to:\n" + paths["summary"] + "\n" + paths["letters"],
                 font=FONT_SMALL, bg=BG, fg="#555", justify="left").pack(anchor="w", pady=20)
        tk.Button(self, text="Next participant  ▶", font=FONT_BIG, padx=20, pady=10,
                  command=lambda: app.show_setup({"ra": app.ra_initials})).pack(anchor="w")


def main() -> None:
    try:
        app = App()
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f"Could not start ETDRS Logger: {e}")
    app.mainloop()


if __name__ == "__main__":
    main()
