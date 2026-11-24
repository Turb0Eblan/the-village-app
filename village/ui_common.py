"""Small shared UI helpers: log rendering, tables, plots."""
import csv
import re
import tkinter as tk
from tkinter import ttk, filedialog

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402

from .calc import fmt  # noqa: E402

GREEN = "#2e7d32"
RED = "#c62828"
GREY = "#666666"
MONO = ("Menlo", 11)

matplotlib.rcParams.update({
    "font.size": 9, "axes.grid": True, "grid.color": "#dddddd", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 100,
    "axes.prop_cycle": matplotlib.cycler(color=["#1f4e79", "#c55a11", "#548235", "#7f6000",
                                                "#7030a0", "#808080"]),
})


def make_text(parent):
    frame = ttk.Frame(parent)
    t = tk.Text(frame, wrap="word", font=MONO, relief="flat", padx=8, pady=6,
                background="white", foreground="#222222")
    sb = ttk.Scrollbar(frame, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    t.pack(side="left", fill="both", expand=True)
    t.tag_configure("h", font=("Menlo", 12, "bold"), spacing1=10, spacing3=4)
    t.tag_configure("title", foreground="#111111")
    t.tag_configure("f", foreground="#1f4e79")
    t.tag_configure("v", font=("Menlo", 11, "bold"))
    t.tag_configure("ok", foreground=GREEN)
    t.tag_configure("fail", foreground=RED)
    t.tag_configure("note", foreground=GREY)
    return frame, t


def _formula(t, formula):
    """Typeset formula (images) with plain-text fallback."""
    from . import mathfmt
    imgs = t.__dict__.setdefault("_imgs", [])
    for kind, txt in mathfmt.pieces(formula):
        if kind == "tex":
            try:
                img = tk.PhotoImage(data=mathfmt.png_b64(txt))
                imgs.append(img)
                t.image_create("end", image=img, align="center", padx=2, pady=3)
                continue
            except Exception:
                pass
        t.insert("end", txt, "f")


def render_log(t, steps, clear=True, typeset=True):
    t.configure(state="normal")
    if clear:
        t.delete("1.0", "end")
        t.__dict__["_imgs"] = []
    if not steps:
        t.insert("end", "Nothing calculated yet. Press Calculate.\n", "note")
    for s in steps:
        if s.get("header"):
            t.insert("end", s["title"] + "\n", "h")
            continue
        t.insert("end", "  " + s["title"] + "\n", "title")
        t.insert("end", "      ")
        if s["formula"]:
            if typeset:
                _formula(t, s["formula"])
            else:
                t.insert("end", s["formula"], "f")
        if s["value"] is not None:
            t.insert("end", "   =  " if s["formula"] else "", "f")
            t.insert("end", fmt(s["value"]) + (" " + s["unit"] if s["unit"] else ""), "v")
        st = s.get("status", "")
        if st:
            tag = "ok" if st in ("OK", "chosen", "ok") else ("fail" if st in ("FAIL", "LOW", "> limit") else "note")
            t.insert("end", f"   [{st}]", tag)
        t.insert("end", "\n")
        if s.get("note"):
            t.insert("end", "      " + s["note"] + "\n", "note")
    t.configure(state="disabled")


def make_table(parent, columns=None, height=10):
    frame = ttk.Frame(parent)
    tv = ttk.Treeview(frame, show="headings", height=height)
    sy = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    sx = ttk.Scrollbar(frame, orient="horizontal", command=tv.xview)
    tv.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tv.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    tv.tag_configure("fail", foreground=RED)
    tv.tag_configure("chosen", background="#cfe8c6", foreground="#12320f")
    tv.tag_configure("best", background="#cfe8c6", foreground="#12320f")
    if columns:
        fill_table(tv, columns, [])
    return frame, tv


# ------------------------------------------------- "which value is best"
_LOWER = re.compile(r"(npc|lcoe|capex|capitalised|cost eur|total eur|extra cost|co2|import|loss|\bdu\b|thd|"
                    r"unmet|overrun|fixed eur|energy eur)", re.I)
_HIGHER = re.compile(r"(ren\.|renewable|saving|export)", re.I)


def direction(name):
    """-1 lower is better, +1 higher is better, 0 neutral."""
    n = str(name)
    if _HIGHER.search(n):
        return 1
    if _LOWER.search(n):
        return -1
    return 0


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)          # numpy scalars
    except (TypeError, ValueError):
        return None


def _excluded(row):
    txt = " ".join(str(v) for v in row).lower()
    return "fail" in txt or row[-1] in ("no",)


_KEY = re.compile(r"(npc|lcoe|capitalised|total eur|cost eur|ren\.|co2|thd)", re.I)


def best_cells(columns, rows):
    """{(row, col)} of the best value of every 'better' column (failed rows excluded)."""
    out = set()
    if len(rows) < 2:
        return out
    for j, c in enumerate(columns):
        d = direction(c)
        if not d or not _KEY.search(str(c)):
            continue
        vals = [(i, _num(r[j])) for i, r in enumerate(rows) if j < len(r) and not _excluded(r)]
        vals = [(i, v) for i, v in vals if v is not None]
        if len(vals) < 2 or len({v for _, v in vals}) < 2:
            continue
        b = (max if d > 0 else min)(v for _, v in vals)
        out |= {(i, j) for i, v in vals if v == b}
    return out


def fill_table(tv, columns, rows, widths=None):
    tv.delete(*tv.get_children())
    best = best_cells(columns, rows)
    tv["columns"] = [str(c) for c in columns]
    for j, c in enumerate(columns):
        w = (widths[j] if widths else None) or max(70, min(320, 8 * len(str(c)) + 20))
        if rows and j < len(rows[0]):
            w = max(w, min(360, 7 * max(len(fmt(r[j]) if not isinstance(r[j], str) else r[j]) for r in rows) + 16
                           + (18 if any(jj == j for _, jj in best) else 0)))
        tv.heading(str(c), text=str(c))
        tv.column(str(c), width=w, anchor="w" if j <= 1 else "e", stretch=False)
    for i, r in enumerate(rows):
        vals = [("\u2605 " if (i, j) in best else "") + (fmt(v) if not isinstance(v, str) else v)
                for j, v in enumerate(r)]
        txt = " ".join(str(v) for v in r).lower()
        tag = "chosen" if "chosen" in txt else ("fail" if ("fail" in txt or " no:" in " " + txt) else "")
        tv.insert("", "end", values=vals, tags=(tag,))


def export_csv(columns, rows, parent=None, name="table"):
    path = filedialog.asksaveasfilename(parent=parent, defaultextension=".csv",
                                        initialfile=name.replace(" ", "_") + ".csv",
                                        filetypes=[("CSV", "*.csv")])
    if not path:
        return None
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columns)
        w.writerows(rows)
    return path


class Plot(ttk.Frame):
    def __init__(self, parent, w=7, h=3.6, toolbar=True):
        super().__init__(parent)
        self.fig = Figure(figsize=(w, h))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        if toolbar:
            tb = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
            tb.update()
            tb.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def draw(self):
        self.fig.tight_layout()
        self.canvas.draw_idle()


# ------------------------------------------------------------ cell grid
class CellGrid(ttk.Frame):
    """Table drawn on a canvas so single cells can be coloured
    (Treeview can only colour whole rows). Used for comparisons."""
    SURF, INK, MUTED, LINE = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
    HEAD = "#eeede9"
    GOOD_BG, GOOD_FG = "#cfe8c6", "#12320f"
    BAD_BG, BAD_FG = "#f6d5d3", "#5c1311"

    def __init__(self, parent, rowh=24):
        super().__init__(parent)
        self.rowh = rowh
        self.c = tk.Canvas(self, background=self.SURF, highlightthickness=0)
        sy = ttk.Scrollbar(self, orient="vertical", command=self.c.yview)
        sx = ttk.Scrollbar(self, orient="horizontal", command=self.c.xview)
        self.c.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.c.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.c.bind("<MouseWheel>", lambda e: self.c.yview_scroll(int(-e.delta), "units"))

    def fill(self, columns, rows, widths, marks=None):
        """marks: {(i, j): 'good' | 'bad'}"""
        c, h = self.c, self.rowh
        marks = marks or {}
        c.delete("all")
        xs = [0]
        for w in widths:
            xs.append(xs[-1] + w)
        c.create_rectangle(0, 0, xs[-1], h, fill=self.HEAD, outline="")
        for j, col in enumerate(columns):
            c.create_text(xs[j] + 8 if j == 0 else xs[j + 1] - 8, h / 2, text=str(col),
                          anchor="w" if j == 0 else "e", fill=self.INK, font=("Helvetica", 11, "bold"))
        for i, r in enumerate(rows):
            y = (i + 1) * h
            for j, v in enumerate(r):
                m = marks.get((i, j))
                if m:
                    c.create_rectangle(xs[j] + 1, y + 1, xs[j + 1] - 1, y + h - 1, outline="",
                                       fill=self.GOOD_BG if m == "good" else self.BAD_BG)
                txt = fmt(v) if not isinstance(v, str) else v
                if m == "good":
                    txt = "\u2605 " + txt
                fg = self.GOOD_FG if m == "good" else self.BAD_FG if m == "bad" else (
                    self.INK if j == 0 else self.INK)
                c.create_text(xs[j] + 8 if j == 0 else xs[j + 1] - 8, y + h / 2, text=txt,
                              anchor="w" if j == 0 else "e", fill=fg,
                              font=("Helvetica", 11, "bold" if m == "good" else "normal"))
            c.create_line(0, y + h, xs[-1], y + h, fill=self.LINE)
        c.configure(scrollregion=(0, 0, xs[-1] + 4, (len(rows) + 1) * h + 4))
