"""Main window: map in the middle, Settings / Parameters / Setup on top,
Compare / Report / Calculate at the bottom (layout from the team sketch)."""
import json
import os
import queue
import subprocess
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .params import Params, YEARS, DEFAULT_YEAR, SETUP_FIELDS, HOMER_REF, year_setup
from .engine import run as run_engine
from .data import DATA_DIR
from .calc import fmt
from .ui_dash import DashboardPage
from .ui_common import (make_text, render_log, make_table, fill_table, export_csv, Plot, GREEN, RED, GREY,
                        CellGrid, direction)
from .ui_nodes import NodeWindow, TITLES

STATE_FILE = os.path.join(os.path.expanduser("~"), ".village_dg_state.json")


class App:
    def __init__(self, root):
        self.root = root
        root.title("The Village - distribution network & distributed generation")
        root.geometry("1280x800")
        root.minsize(1000, 640)
        self.params = Params()
        self.setup = year_setup(DEFAULT_YEAR)
        self.settings = dict(auto_calc=True, remember=True)
        self.runs = []
        self.current = None
        self.q = queue.Queue()
        self.busy = False
        self._load_state()

        style = ttk.Style()
        style.configure("Treeview", rowheight=20)
        style.configure("Bar.TFrame", background="#ececec")

        # ---- top bar
        top = ttk.Frame(root, padding=(6, 6, 6, 2))
        top.pack(side="top", fill="x")
        self.page_btns = {}
        for name in ("Dashboard", "Map", "Settings", "Parameters", "Setup"):
            b = ttk.Button(top, text=name, command=lambda n=name: self.show(n))
            b.pack(side="left", padx=(0, 4))
            self.page_btns[name] = b
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(top, text="Year:").pack(side="left")
        self.year_var = tk.StringVar(value=self.setup["year"])
        cb = ttk.Combobox(top, textvariable=self.year_var, values=list(YEARS), width=8, state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.change_year())
        self.year_note = ttk.Label(top, text="", foreground=GREY)
        self.year_note.pack(side="left", padx=8)

        # ---- bottom bar
        bot = ttk.Frame(root, padding=(6, 2, 6, 6))
        bot.pack(side="bottom", fill="x")
        ttk.Button(bot, text="Compare", command=lambda: self.show("Compare")).pack(side="left", padx=(0, 4))
        ttk.Button(bot, text="Report", command=lambda: self.show("Report")).pack(side="left")
        self.calc_btn = ttk.Button(bot, text="Calculate", command=self.calculate)
        self.calc_btn.pack(side="right")
        self.status = ttk.Label(bot, text="", foreground=GREY)
        self.status.pack(side="right", padx=10)

        ttk.Separator(root).pack(side="top", fill="x")
        ttk.Separator(root).pack(side="bottom", fill="x")
        self.body = ttk.Frame(root)
        self.body.pack(fill="both", expand=True)
        self.pages = {}
        self.pages["Dashboard"] = DashboardPage(self.body, self)
        self.pages["Map"] = MapPage(self.body, self)
        self.pages["Settings"] = SettingsPage(self.body, self)
        self.pages["Parameters"] = ParamPage(self.body, self)
        self.pages["Setup"] = SetupPage(self.body, self)
        self.pages["Compare"] = ComparePage(self.body, self)
        self.pages["Report"] = ReportPage(self.body, self)
        self.show("Map")
        self.update_year_note()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll)
        root.after(300, self.calculate)

    # ------------------------------------------------------------ pages
    def show(self, name):
        for n, p in self.pages.items():
            p.frame.pack_forget()
        self.pages[name].frame.pack(fill="both", expand=True)
        self.pages[name].refresh()
        self.page = name

    def update_year_note(self):
        y = self.setup["year"]
        txt = YEARS[y]["title"] + "  -  " + YEARS[y]["note"]
        if self.setup_changed():
            txt += "   (setup modified)"
        self.year_note.configure(text=txt)

    def setup_changed(self):
        pre = year_setup(self.setup["year"])
        return any(self.setup.get(k) != pre.get(k) for k, _l, _t in SETUP_FIELDS)

    def change_year(self):
        self.setup = year_setup(self.year_var.get())
        self.update_year_note()
        self.pages["Setup"].refresh()
        if self.settings["auto_calc"]:
            self.calculate()

    # ------------------------------------------------------------ calculation
    def calculate(self, years=None):
        if self.busy:
            return
        self.busy = True
        self.calc_btn.state(["disabled"])
        jobs = []
        if years:
            for y in years:
                jobs.append(year_setup(y))
        else:
            jobs.append(dict(self.setup))
        params = self.params.snapshot()
        changed = bool(params.diff_from_default())

        def work():
            try:
                for s in jobs:
                    r = run_engine(params, s, progress=lambda m: self.q.put(("msg", m)))
                    pre = year_setup(s["year"])
                    mod = any(s.get(k) != pre.get(k) for k, _l, _t in SETUP_FIELDS)
                    r["modified"] = changed or mod
                    self.q.put(("run", r))
                self.q.put(("done", None))
            except Exception:
                self.q.put(("error", traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "msg":
                    self.status.configure(text=val)
                elif kind == "run":
                    val["label"] = f"#{len(self.runs) + 1}  {val['setup']['year']}" + ("*" if val["modified"] else "")
                    self.runs.append(val)
                    if val["setup"]["year"] == self.setup["year"]:
                        self.current = val
                    elif self.current is None:
                        self.current = val
                elif kind == "done":
                    self.busy = False
                    self.calc_btn.state(["!disabled"])
                    r = self.current
                    if r:
                        nf = len(r["fails"])
                        self.status.configure(
                            text=f"{r['label']}: {r['n_checks']} checks, "
                                 + (f"{nf} problem(s)" if nf else "all OK") + f"  ({r['seconds']:.1f} s)",
                            foreground=RED if nf else GREEN)
                    self.pages[self.page].refresh()
                elif kind == "error":
                    self.busy = False
                    self.calc_btn.state(["!disabled"])
                    self.status.configure(text="Calculation error", foreground=RED)
                    messagebox.showerror("Calculation error", val[-2000:], parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    # ------------------------------------------------------------ state
    def _load_state(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                d = json.load(f)
            self.settings.update(d.get("settings", {}))
            if self.settings.get("remember") and d.get("params"):
                self.params.load_json(d["params"])
        except Exception:
            pass

    def on_close(self):
        try:
            d = dict(settings=self.settings)
            if self.settings.get("remember"):
                d["params"] = self.params.to_json()
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except Exception:
            pass
        self.root.destroy()


# ===================================================================== Map
class MapPage:
    """Real map of Autrans (or the schematic view) + selected object + key results."""

    def __init__(self, parent, app):
        from . import ui_map
        self.ui_map = ui_map
        self.app = app
        self.frame = ttk.Frame(parent)
        pw = ttk.PanedWindow(self.frame, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw)
        pw.add(left, weight=3)
        bar = ttk.Frame(left, padding=(4, 4))
        bar.pack(fill="x")
        views = (list(ui_map.TILES) if ui_map.HAVE_MAP else []) + ["Schematic"]
        self.view_var = tk.StringVar(value=app.settings.get("map_view", views[0]))
        if self.view_var.get() not in views:
            self.view_var.set(views[0])
        ttk.Label(bar, text="View:").pack(side="left")
        cb = ttk.Combobox(bar, textvariable=self.view_var, values=views, state="readonly", width=16)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.change_view())
        ttk.Button(bar, text="Overview", command=self.overview).pack(side="left", padx=4)
        self.hint = ttk.Label(bar, text="Click a block or a line: the map zooms in and shows the equipment.",
                              foreground=GREY)
        self.hint.pack(side="left", padx=8)
        self.holder = ttk.Frame(left)
        self.holder.pack(fill="both", expand=True)
        self.geo = ui_map.GeoMap(self.holder, self) if ui_map.HAVE_MAP else None
        self.scheme = ui_map.Scheme(self.holder, self)
        self.view = None

        right = ttk.Frame(pw, padding=4)
        pw.add(right, weight=1)
        self.sel_title = ttk.Label(right, text="Selected", font=("Helvetica", 12, "bold"))
        self.sel_title.pack(anchor="w")
        self.sel = tk.Text(right, height=11, wrap="word", relief="flat", padx=6, pady=4,
                           background="white", foreground="#222222", font=("Helvetica", 11))
        self.sel.tag_configure("b", font=("Helvetica", 11, "bold"))
        self.sel.tag_configure("g", foreground=GREY)
        self.sel.tag_configure("fail", foreground=RED)
        self.sel.pack(fill="x")
        self.open_btn = ttk.Button(right, text="Open details (diagram, formulas, tables)", state="disabled")
        self.open_btn.pack(anchor="w", pady=(2, 6))
        self.res_title = ttk.Label(right, text="Key results", font=("Helvetica", 12, "bold"))
        self.res_title.pack(anchor="w")
        tf, self.tv = make_table(right, height=14)
        tf.pack(fill="both", expand=True)
        ttk.Label(right, text="Problems", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(6, 0))
        self.fails = tk.Listbox(right, height=5, foreground=RED, relief="flat", activestyle="none")
        self.fails.pack(fill="x")
        self.change_view(redraw=False)
        self._info("Nothing selected", [("Click a block (village, ski resort, eco-district, source) "
                                         "or a line on the map.", "g")], None)

    # ---------------------------------------------------------- views
    def change_view(self, redraw=True):
        v = self.view_var.get()
        self.app.settings["map_view"] = v
        new = self.scheme if v == "Schematic" or not self.geo else self.geo
        if self.view is not new:
            if self.view:
                self.view.frame.pack_forget()
            new.frame.pack(fill="both", expand=True)
            self.view = new
        if new is self.geo:
            self.geo.set_tiles(v)
        if redraw:
            self.refresh()

    def overview(self):
        self.view.overview()

    def refresh(self):
        if self.view is self.geo and self.geo.mode not in ("overview",) and self.app.current:
            self.geo.open_node(self.geo.mode)
        else:
            self.view.overview()
        r = self.app.current
        if r:
            self.res_title.configure(text=f"Key results  -  run {r['label']}")
            fill_table(self.tv, ["quantity", "value"], [[k, v] for k, v in r["kpi"].items()],
                       widths=[220, 260])
            self.fails.delete(0, "end")
            for s in r["fails"]:
                self.fails.insert("end", f"{s['tag']}: {s['title']} = {fmt(s['value'])} {s['unit']}")
            if not r["fails"]:
                self.fails.insert("end", "none")
                self.fails.itemconfigure(0, foreground=GREEN)

    # ---------------------------------------------------------- selection
    def _info(self, title, rows, open_node):
        self.sel_title.configure(text=title)
        t = self.sel
        t.configure(state="normal")
        t.delete("1.0", "end")
        for txt, tag in rows:
            t.insert("end", txt + "\n", tag)
        t.configure(state="disabled")
        if open_node:
            self.open_btn.configure(state="normal", command=lambda: NodeWindow(self.app, open_node))
        else:
            self.open_btn.configure(state="disabled")

    @staticmethod
    def _el_rows(els):
        rows = []
        for e in els:
            rows.append((f"{e['name']}  ({e['kind']})", "b"))
            rows.append(("   " + e["rating"] + (f"   [{e['status']}]" if e.get("status") else ""),
                         "fail" if e.get("status") == "FAIL" else ""))
            if e.get("detail"):
                rows.append(("   " + e["detail"].replace("\n", "  "), "g"))
        return rows

    def select(self, kind, node, item=None):
        r = self.app.current
        um = self.ui_map
        if not r:
            self._info(TITLES.get(node, node), [("Press Calculate first.", "g")], None)
            return
        p = r["params"]
        if kind == "node":
            rows = [(t, "") for t in um.node_card_lines(r, node)]
            rows.append(("", ""))
            rows += self._el_rows(r["net"]["elements"].get(node, []))
            self._info(TITLES[node], rows, node)
            if self.view is self.geo and self.geo.mode != node:
                self.geo.open_node(node)
        elif kind == "line":
            km = um.route_lengths(p)[node]
            rows = [(t, "") for t in um.line_lines(r, node)]
            rows.append((f"route on the map {km:.2f} km, length used {p['geo.' + node + '_len']} km", "g"))
            rows += self._el_rows(r["net"]["elements"].get(node, []))
            self._info(TITLES[node], rows, node)
        elif kind == "item":
            rows = [(item["lines"][0], "b")] + [(t, "") for t in item["lines"][1:]]
            st = um.sites(p).get(item["key"])
            if st:
                rows.append((f"position {st['lat']:.5f}, {st['lon']:.5f}  ({st['source']})", "g"))
            rows.append(("", ""))
            rows += self._el_rows(item["els"])
            self._info(f"{TITLES[node]}: {item['lines'][0]}", rows, node)


# ================================================================ Settings
class SettingsPage:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=16)
        f = self.frame
        ttk.Label(f, text="Settings", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.v_auto = tk.BooleanVar(value=app.settings["auto_calc"])
        self.v_rem = tk.BooleanVar(value=app.settings["remember"])
        ttk.Checkbutton(f, text="Recalculate automatically when the year is changed", variable=self.v_auto,
                        command=self.save).pack(anchor="w", pady=(10, 2))
        ttk.Checkbutton(f, text="Remember edited parameters between sessions", variable=self.v_rem,
                        command=self.save).pack(anchor="w", pady=2)
        ttk.Label(f, text=f"Settings file: {STATE_FILE}", foreground=GREY).pack(anchor="w", pady=(2, 12))
        ttk.Label(f, text="Input data (8760 h, kW / weather):", font=("Helvetica", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text=DATA_DIR, foreground=GREY).pack(anchor="w")
        files = sorted(os.listdir(DATA_DIR)) if os.path.isdir(DATA_DIR) else []
        ttk.Label(f, text=", ".join(files), foreground=GREY, wraplength=900).pack(anchor="w", pady=2)
        ttk.Button(f, text="Open data folder", command=lambda: subprocess.call(["open", DATA_DIR])).pack(anchor="w", pady=4)
        ttk.Button(f, text="Clear run history", command=self.clear).pack(anchor="w", pady=4)
        txt = ("Sources of the default values: project subject (BE-village 26-27), teacher price sheets "
               "(Tarifs/Costs.html, MV-substation_cost.html), Minera transformer catalogue, Silec cable "
               "catalogue and price list 2010, ATV66 harmonic tables, team work in TheVillage folder "
               "(Tuan_Hung network sheet, Duy tariffs, Artur/Huy load curves, Thinh meteo & biomass, "
               "eco-district HOMER results). Each parameter shows its source in Parameters.")
        ttk.Label(f, text=txt, wraplength=900, foreground=GREY).pack(anchor="w", pady=(16, 0))

    def save(self):
        self.app.settings["auto_calc"] = self.v_auto.get()
        self.app.settings["remember"] = self.v_rem.get()

    def clear(self):
        self.app.runs = [self.app.current] if self.app.current else []
        if self.app.current:
            self.app.current["label"] = "#1  " + self.app.current["setup"]["year"]

    def refresh(self):
        pass


# ============================================================== Parameters
class ParamPage:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=6)
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="Parameters", font=("Helvetica", 14, "bold")).pack(side="left")
        ttk.Label(bar, text="  double-click a value to edit, then press Calculate", foreground=GREY).pack(side="left")
        ttk.Button(bar, text="Reset all to defaults", command=self.reset).pack(side="right")
        ttk.Button(bar, text="Load...", command=self.load).pack(side="right", padx=4)
        ttk.Button(bar, text="Save...", command=self.save).pack(side="right")
        self.changed_lbl = ttk.Label(bar, text="", foreground=RED)
        self.changed_lbl.pack(side="right", padx=10)
        pw = ttk.PanedWindow(self.frame, orient="horizontal")
        pw.pack(fill="both", expand=True, pady=4)
        self.sec = tk.Listbox(pw, width=34, activestyle="none", exportselection=False, relief="flat")
        pw.add(self.sec, weight=0)
        self.items = []
        for name, title, _ in app.params.sections:
            self.items.append(("sec", name, title))
        for name, t in app.params.tables.items():
            self.items.append(("tab", name, "Catalogue: " + t["title"].split("(")[0].strip()))
        for _k, _n, title in self.items:
            self.sec.insert("end", title)
        self.sec.bind("<<ListboxSelect>>", lambda e: self.show_sel())
        right = ttk.Frame(pw)
        pw.add(right, weight=1)
        self.src = ttk.Label(right, text="", foreground=GREY)
        self.src.pack(anchor="w")
        tf, self.tv = make_table(right, height=24)
        tf.pack(fill="both", expand=True)
        self.tv.tag_configure("changed", foreground="#1f4e79", font=("Helvetica", 12, "bold"))
        self.tv.bind("<Double-1>", self.edit)
        rb = ttk.Frame(right)
        rb.pack(fill="x", pady=4)
        self.add_btn = ttk.Button(rb, text="Add row", command=self.add_row)
        self.del_btn = ttk.Button(rb, text="Delete row", command=self.del_row)
        self.sec.selection_set(0)
        self.cur = self.items[0]

    def refresh(self):
        self.show_sel()

    def show_sel(self):
        sel = self.sec.curselection()
        if sel:
            self.cur = self.items[sel[0]]
        kind, name, _ = self.cur
        P = self.app.params
        base = Params()
        if kind == "sec":
            items = next(i for n, _t, i in P.sections if n == name)
            bitems = next(i for n, _t, i in base.sections if n == name)
            self.tv.delete(*self.tv.get_children())
            fill_table(self.tv, ["parameter", "value", "unit", "source"], [], widths=[330, 230, 110, 360])
            for it, b in zip(items, bitems):
                tag = ("changed",) if it["value"] != b["value"] else ()
                self.tv.insert("", "end", iid=it["key"], values=[it["label"], str(it["value"]), it["unit"],
                                                                it["source"]], tags=tag)
            self.src.configure(text="Scalar parameters")
            self.add_btn.pack_forget()
            self.del_btn.pack_forget()
        else:
            t = P.tables[name]
            fill_table(self.tv, t["columns"], [], widths=[100] * len(t["columns"]))
            for j, row in enumerate(t["rows"]):
                self.tv.insert("", "end", iid=str(j), values=[str(v) for v in row])
            self.src.configure(text=t["title"] + "   |   source: " + t["source"])
            self.add_btn.pack(side="left")
            self.del_btn.pack(side="left", padx=4)
        n = len(P.diff_from_default())
        self.changed_lbl.configure(text=f"{n} value(s) changed from defaults" if n else "")

    def edit(self, ev):
        row = self.tv.identify_row(ev.y)
        col = self.tv.identify_column(ev.x)
        if not row:
            return
        kind, name, _ = self.cur
        ci = int(col[1:]) - 1
        if kind == "sec":
            ci = 1
        x, y, w, h = self.tv.bbox(row, f"#{ci + 1}")
        old = self.tv.item(row, "values")[ci]
        e = ttk.Entry(self.tv)
        e.insert(0, old)
        e.select_range(0, "end")
        e.place(x=x, y=y, width=max(w, 80), height=h)
        e.focus_set()

        def conv(s, ref):
            if isinstance(ref, bool):
                return s.lower() in ("1", "true", "yes")
            if isinstance(ref, int) and not isinstance(ref, bool):
                try:
                    return int(float(s))
                except ValueError:
                    return ref
            if isinstance(ref, float):
                try:
                    return float(s.replace(",", "."))
                except ValueError:
                    return ref
            return s

        def done(_e=None):
            val = e.get()
            e.destroy()
            P = self.app.params
            if kind == "sec":
                ref = P[f"{name}.{row}"]
                P.set(f"{name}.{row}", conv(val, ref))
            else:
                r = P.tables[name]["rows"][int(row)]
                r[ci] = conv(val, r[ci]) if not isinstance(r[ci], str) else val
            self.show_sel()
        e.bind("<Return>", done)
        e.bind("<FocusOut>", done)
        e.bind("<Escape>", lambda _e: e.destroy())

    def add_row(self):
        kind, name, _ = self.cur
        if kind == "tab":
            rows = self.app.params.tables[name]["rows"]
            rows.append(list(rows[-1]) if rows else [0] * len(self.app.params.tables[name]["columns"]))
            self.show_sel()

    def del_row(self):
        kind, name, _ = self.cur
        sel = self.tv.selection()
        if kind == "tab" and sel:
            rows = self.app.params.tables[name]["rows"]
            if len(rows) > 1:
                del rows[int(sel[0])]
            self.show_sel()

    def reset(self):
        if messagebox.askyesno("Reset", "Reset all parameters and catalogues to the project defaults?",
                               parent=self.frame):
            self.app.params = Params()
            self.show_sel()

    def save(self):
        path = filedialog.asksaveasfilename(parent=self.frame, defaultextension=".json",
                                            initialfile="village_parameters.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.app.params.to_json())

    def load(self):
        path = filedialog.askopenfilename(parent=self.frame, filetypes=[("JSON", "*.json")])
        if path:
            with open(path, encoding="utf-8") as f:
                self.app.params.load_json(f.read())
            self.show_sel()


# =================================================================== Setup
class SetupPage:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=16)
        f = self.frame
        ttk.Label(f, text="Setup - what exists in the system", font=("Helvetica", 14, "bold")).pack(anchor="w")
        ttk.Label(f, text="A year loads a preset (the team's story). Any switch can be changed afterwards; "
                          "press Calculate to see the effect.", foreground=GREY).pack(anchor="w", pady=(0, 10))
        yb = ttk.Frame(f)
        yb.pack(anchor="w", pady=(0, 10))
        for y in YEARS:
            ttk.Button(yb, text=YEARS[y]["title"], command=lambda y=y: self.preset(y)).pack(side="left", padx=(0, 4))
        self.grid = ttk.Frame(f)
        self.grid.pack(anchor="w")
        self.vars = {}
        for r, (key, label, typ) in enumerate(SETUP_FIELDS):
            ttk.Label(self.grid, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 20))
            if typ == "bool":
                v = tk.BooleanVar()
                w = ttk.Checkbutton(self.grid, variable=v, command=self.store)
            elif typ == "num":
                v = tk.StringVar()
                w = ttk.Entry(self.grid, textvariable=v, width=8)
                w.bind("<FocusOut>", lambda e: self.store())
                w.bind("<Return>", lambda e: self.store())
            else:
                v = tk.StringVar()
                w = ttk.Combobox(self.grid, textvariable=v, values=typ, state="readonly", width=22)
                w.bind("<<ComboboxSelected>>", lambda e: self.store())
            w.grid(row=r, column=1, sticky="w")
            self.vars[key] = (v, typ)
        self.note = ttk.Label(f, text="", foreground=GREY, wraplength=900)
        self.note.pack(anchor="w", pady=12)

    def preset(self, y):
        self.app.year_var.set(y)
        self.app.change_year()
        self.refresh()

    def store(self):
        for k, (v, typ) in self.vars.items():
            val = v.get()
            if typ == "num":
                try:
                    val = float(val)
                except ValueError:
                    val = 0.0
            self.app.setup[k] = val
        self.app.update_year_note()

    def refresh(self):
        for k, (v, typ) in self.vars.items():
            v.set(self.app.setup.get(k, False if typ == "bool" else ""))
        y = self.app.setup["year"]
        self.note.configure(text=f"{YEARS[y]['title']}: {YEARS[y]['note']}")


# ================================================================= Compare
class ComparePage:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=6)
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="Compare runs", font=("Helvetica", 14, "bold")).pack(side="left")
        ttk.Button(bar, text="Calculate all years (current parameters)",
                   command=lambda: app.calculate(years=list(YEARS))).pack(side="left", padx=12)
        ttk.Button(bar, text="Export CSV", command=self.export).pack(side="right")
        ttk.Button(bar, text="Remove last run", command=self.remove).pack(side="right", padx=4)
        pw = ttk.PanedWindow(self.frame, orient="vertical")
        pw.pack(fill="both", expand=True, pady=4)
        top = ttk.Frame(pw)
        pw.add(top, weight=3)
        ttk.Label(top, text="\u2605 green = best run for this quantity, red = worst "
                            "(lower is better for costs, CO2, import, dU, THD; higher for renewable share, "
                            "savings, export; other rows are not ranked)",
                  foreground=GREY).pack(anchor="w", pady=(2, 2))
        self.grid = CellGrid(top)
        self.grid.pack(fill="both", expand=True)
        bottom = ttk.Frame(pw)
        pw.add(bottom, weight=2)
        nb = ttk.Notebook(bottom)
        nb.pack(fill="both", expand=True)
        g = ttk.Frame(nb)
        nb.add(g, text="Chart")
        cb = ttk.Frame(g)
        cb.pack(fill="x")
        ttk.Label(cb, text="Quantity:").pack(side="left")
        self.kpi = tk.StringVar()
        self.kpi_cb = ttk.Combobox(cb, textvariable=self.kpi, width=40, state="readonly")
        self.kpi_cb.pack(side="left", padx=4)
        self.kpi_cb.bind("<<ComboboxSelected>>", lambda e: self.chart())
        self.plot = Plot(g, 9, 2.8, toolbar=False)
        self.plot.pack(fill="both", expand=True)
        h = ttk.Frame(nb)
        nb.add(h, text="Team HOMER results vs this app")
        tf2, self.tv2 = make_table(h, height=6)
        tf2.pack(fill="both", expand=True)
        self.cols, self.rows = [], []

    def refresh(self):
        runs = self.app.runs
        keys = []
        for r in runs:
            for k in r["kpi"]:
                if k not in keys and k != "Year":
                    keys.append(k)
        self.cols = ["quantity"] + [r["label"] for r in runs]
        self.rows = [[k] + [r["kpi"].get(k, "-") for r in runs] for k in keys]
        marks = {}
        for i, row in enumerate(self.rows):
            d = direction(row[0])
            vals = [(j, v) for j, v in enumerate(row[1:], 1) if isinstance(v, (int, float))
                    and not isinstance(v, bool)]
            if not d or len(vals) < 2 or len({v for _, v in vals}) < 2:
                continue
            b = (max if d > 0 else min)(v for _, v in vals)
            w = (min if d > 0 else max)(v for _, v in vals)
            for j, v in vals:
                if v == b:
                    marks[(i, j)] = "good"
                elif v == w:
                    marks[(i, j)] = "bad"
        widths = [260] + [max(150, min(330, 8 * max([len(str(r[j])) for r in self.rows] + [len(self.cols[j])]) + 40))
                          for j in range(1, len(self.cols))]
        self.grid.fill(self.cols, self.rows, widths, marks)
        num = [k for k in keys if any(isinstance(r["kpi"].get(k), (int, float)) for r in runs)]
        self.kpi_cb["values"] = num
        if num and self.kpi.get() not in num:
            self.kpi.set("Village NPC (EUR)" if "Village NPC (EUR)" in num else num[0])
        self.chart()
        self.homer()

    def chart(self):
        fig = self.plot.fig
        fig.clear()
        runs = self.app.runs
        k = self.kpi.get()
        if not runs or not k:
            self.plot.draw()
            return
        ax = fig.add_subplot(111)
        vals = [r["kpi"].get(k) if isinstance(r["kpi"].get(k), (int, float)) else 0 for r in runs]
        d = direction(k)
        b = ((max if d > 0 else min)(vals) if d and len(set(vals)) > 1 else None)
        cols = ["#2a78d6" if (b is not None and v == b) else "#b7b6b1" if b is not None else "#2a78d6"
                for v in vals]
        ax.bar([r["label"] for r in runs], vals, color=cols, width=0.6)
        for j, v in enumerate(vals):
            ax.text(j, v, ("\u2605 best  " if v == b else "") + fmt(v), ha="center", va="bottom", fontsize=8,
                    fontweight="bold" if v == b else "normal")
        ax.set_xlim(-0.6, max(len(vals), 6) - 0.4)
        ax.set_title(k + ("   (lower is better)" if d < 0 else "   (higher is better)" if d > 0 else ""), fontsize=9)
        self.plot.draw()

    def homer(self):
        def latest(year):
            for r in reversed(self.app.runs):
                if r["setup"]["year"] == year:
                    return r
            return None
        rows = []
        for ref in HOMER_REF:
            r = latest(ref["year"])
            app_v = "-"
            if r:
                if "isolated" in ref["case"] and r.get("eco") and "iso" in r["eco"]:
                    b = r["eco"]["iso"]["best"]
                    app_v = f"NPC {b['NPC']:,.0f}, LCOE {b['LCOE']:.3f}: {b['label']}"
                elif "+ grid" in ref["case"] and r.get("eco") and "grid" in r["eco"]:
                    b = r["eco"]["grid"]["best"]
                    app_v = f"NPC {b['NPC']:,.0f} (incl. L2 line), {b['label']}"
                elif "Break-even" in ref["case"] and r.get("eco") and "breakeven_km" in r["eco"]:
                    app_v = (f"{r['eco']['breakeven_km_homer']:.1f} km with HOMER cost, "
                             f"{r['eco']['breakeven_km']:.1f} km with designed L2")
                elif "net-zero" in ref["case"]:
                    b = r["ev"]["best"]
                    app_v = f"NPC {b['NPC']:,.0f}, LCOE {b['LCOE']:.4f}, ren. {b['REN']:.1f} %: {b['label']}"
            val = (f"NPC {ref['NPC']:,.0f}, LCOE {ref['LCOE']}, ren. {ref['REN']} %"
                   if ref.get("NPC") else f"{ref.get('dist_km')} km")
            rows.append([ref["case"], ref["year"], ref["arch"], val, app_v, ref["src"]])
        fill_table(self.tv2, ["case", "year", "HOMER architecture", "HOMER result", "this app (latest run)",
                              "source file"], rows, widths=[230, 50, 300, 230, 380, 380])

    def export(self):
        if self.rows:
            export_csv(self.cols, self.rows, self.frame, "comparison")

    def remove(self):
        if self.app.runs:
            r = self.app.runs.pop()
            if self.app.current is r:
                self.app.current = self.app.runs[-1] if self.app.runs else None
            self.refresh()


# ================================================================== Report
class ReportPage:
    SECTIONS = ["all", "loads", "source", "L0", "village", "L1", "ski", "L2", "eco",
                "energy-village", "energy-eco"]

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=6)
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="Report", font=("Helvetica", 14, "bold")).pack(side="left")
        ttk.Label(bar, text="   run:").pack(side="left")
        self.run_var = tk.StringVar()
        self.run_cb = ttk.Combobox(bar, textvariable=self.run_var, width=16, state="readonly")
        self.run_cb.pack(side="left", padx=4)
        self.run_cb.bind("<<ComboboxSelected>>", lambda e: self.show())
        ttk.Label(bar, text="   section:").pack(side="left")
        self.sec_var = tk.StringVar(value="all")
        sc = ttk.Combobox(bar, textvariable=self.sec_var, values=self.SECTIONS, width=16, state="readonly")
        sc.pack(side="left", padx=4)
        sc.bind("<<ComboboxSelected>>", lambda e: self.show())
        ttk.Button(bar, text="Export all tables (CSV)...", command=self.export_all).pack(side="right")
        nb = ttk.Notebook(self.frame)
        nb.pack(fill="both", expand=True, pady=4)
        f1 = ttk.Frame(nb)
        nb.add(f1, text="Calculation log")
        tfr, self.txt = make_text(f1)
        tfr.pack(fill="both", expand=True)
        f2 = ttk.Frame(nb)
        nb.add(f2, text="Tables")
        tb = ttk.Frame(f2)
        tb.pack(fill="x")
        self.tab_var = tk.StringVar()
        self.tab_cb = ttk.Combobox(tb, textvariable=self.tab_var, width=40, state="readonly")
        self.tab_cb.pack(side="left", pady=4)
        self.tab_cb.bind("<<ComboboxSelected>>", lambda e: self.show_table())
        ttk.Button(tb, text="Export CSV", command=self.export_one).pack(side="right")
        tf, self.tv = make_table(f2, height=20)
        tf.pack(fill="both", expand=True)
        f3 = ttk.Frame(nb)
        nb.add(f3, text="Inputs of this run")
        tfr3, self.txt3 = make_text(f3)
        tfr3.pack(fill="both", expand=True)

    def run(self):
        lab = self.run_var.get()
        for r in self.app.runs:
            if r["label"] == lab:
                return r
        return self.app.current

    def refresh(self):
        labels = [r["label"] for r in self.app.runs]
        self.run_cb["values"] = labels
        if self.app.current and self.run_var.get() not in labels:
            self.run_var.set(self.app.current["label"])
        self.show()

    def show(self):
        r = self.run()
        if not r:
            render_log(self.txt, [])
            return
        sec = self.sec_var.get()
        steps = r["log"].steps if sec == "all" else r["log"].for_tags(sec)
        render_log(self.txt, steps)
        names = list(r["tables"])
        self.tab_cb["values"] = names
        if self.tab_var.get() not in names:
            self.tab_var.set(names[0])
        self.show_table()
        t = self.txt3
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", f"Run {r['label']}  calculated at {r['time']}\n\n", "h")
        t.insert("end", "Setup\n", "h")
        for k, lab, _ in SETUP_FIELDS:
            t.insert("end", f"  {lab:55s} {r['setup'].get(k)}\n")
        t.insert("end", "\nParameters changed from project defaults\n", "h")
        diff = r["params"].diff_from_default()
        if not diff:
            t.insert("end", "  none - project task values\n", "note")
        for k, a, b in diff:
            lab, unit = r["params"].label(k)
            t.insert("end", f"  {lab:55s} {a} -> {b} {unit}\n")
        t.configure(state="disabled")

    def show_table(self):
        r = self.run()
        if r and self.tab_var.get() in r["tables"]:
            cols, rows = r["tables"][self.tab_var.get()]
            fill_table(self.tv, cols, rows)

    def export_one(self):
        r = self.run()
        if r and self.tab_var.get() in r["tables"]:
            cols, rows = r["tables"][self.tab_var.get()]
            export_csv(cols, rows, self.frame, f"{r['setup']['year']}_{self.tab_var.get()}")

    def export_all(self):
        import csv
        r = self.run()
        if not r:
            return
        d = filedialog.askdirectory(parent=self.frame, title="Folder for CSV files")
        if not d:
            return
        for name, (cols, rows) in r["tables"].items():
            fn = os.path.join(d, f"{r['setup']['year']}_" + "".join(ch if ch.isalnum() else "_" for ch in name) + ".csv")
            with open(fn, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
        with open(os.path.join(d, f"{r['setup']['year']}_calculation_log.txt"), "w", encoding="utf-8") as f:
            for s in r["log"].steps:
                if s.get("header"):
                    f.write(f"\n== {s['title']}\n")
                else:
                    f.write(f"  {s['title']}: {s['formula']} = {fmt(s['value'])} {s['unit']} "
                            f"{('[' + s['status'] + ']') if s['status'] else ''} {s['note']}\n")
        messagebox.showinfo("Export", f"{len(r['tables'])} tables and the log written to\n{d}", parent=self.frame)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
