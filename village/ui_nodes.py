"""Windows that open when a node or a line is clicked on the map:
'what is inside' = single-line diagram, element list, calculation steps
with formulas, curves and the selection tables."""
import tkinter as tk
from tkinter import ttk
import numpy as np

from .ui_common import (make_text, render_log, make_table, fill_table, export_csv, Plot,
                        GREEN, RED)

TITLES = {"source": "Source substation 63/20 kV", "village": "Village", "ski": "Ski resort",
          "eco": "Eco-district", "L0": "Line L0  source -> village", "L1": "Line L1  village -> ski",
          "L2": "Line L2  village -> eco-district"}
LOG_TAGS = {"source": ("source",), "village": ("village", "loads", "feeder"), "ski": ("ski",),
            "eco": ("eco", "energy-eco"), "L0": ("L0",), "L1": ("L1",), "L2": ("L2",)}
MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def monthly(x):
    d = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    out, k = [], 0
    for n in d:
        out.append(float(np.sum(x[k:k + n * 24])))
        k += n * 24
    return np.array(out)


# ----------------------------------------------------------- single line
INK = "#111111"


class _Ink:
    """Canvas proxy: every item gets an explicit colour (the macOS dark theme
    would otherwise draw default items white on the white diagram)."""

    def __init__(self, canvas):
        self._c = canvas

    def __getattr__(self, k):
        return getattr(self._c, k)

    def create_line(self, *a, **k):
        k.setdefault("fill", INK)
        return self._c.create_line(*a, **k)

    def create_text(self, *a, **k):
        k.setdefault("fill", INK)
        return self._c.create_text(*a, **k)

    def create_oval(self, *a, **k):
        k.setdefault("outline", INK)
        k.setdefault("fill", "white")
        return self._c.create_oval(*a, **k)

    def create_rectangle(self, *a, **k):
        k.setdefault("outline", INK)
        return self._c.create_rectangle(*a, **k)


def cb_label(q, rating):
    """'Q2' + 'Masterpact NW40H1  4000 A / 65 kA' -> two lines."""
    model, _, r = rating.partition("  ")
    return f"{q}  {model}\n{r}" if r else f"{q}  {rating}"


class SLD:
    """Draws a simple single-line diagram of one node on a Canvas."""

    def __init__(self, canvas):
        self.c = _Ink(canvas)

    def cb(self, x, y, label=""):
        self.c.create_rectangle(x - 6, y - 6, x + 6, y + 6, outline="black", width=1.5, fill="white")
        self.c.create_line(x - 6, y - 6, x + 6, y + 6)
        self.c.create_line(x - 6, y + 6, x + 6, y - 6)
        if label:
            self.c.create_text(x + 10, y, text=label, anchor="w", font=("Helvetica", 9))

    def tr(self, x, y, label=""):
        self.c.create_oval(x - 13, y - 22, x + 13, y + 4, width=1.5)
        self.c.create_oval(x - 13, y - 4, x + 13, y + 22, width=1.5)
        if label:
            self.c.create_text(x + 18, y, text=label, anchor="w", font=("Helvetica", 9))

    def box(self, x, y, title, sub="", status="", sym=""):
        w = 172
        col = RED if status == "FAIL" else "black"
        self.c.create_line(x, y - 26, x, y)
        if sym == "M":
            self.c.create_oval(x - 13, y, x + 13, y + 26, width=1.5, outline=col)
            self.c.create_text(x, y + 13, text="M", font=("Helvetica", 10, "bold"), fill=col)
            y0 = y + 30
        elif sym == "G":
            self.c.create_oval(x - 13, y, x + 13, y + 26, width=1.5, outline=col)
            self.c.create_text(x, y + 13, text="G", font=("Helvetica", 10, "bold"), fill=col)
            y0 = y + 30
        elif sym == "C":
            self.c.create_line(x - 12, y + 8, x + 12, y + 8, width=2)
            self.c.create_line(x - 12, y + 14, x + 12, y + 14, width=2)
            self.c.create_line(x, y, x, y + 8)
            y0 = y + 18
        elif sym == "VFD+M":      # drive with its motor in series underneath
            self.c.create_rectangle(x - 22, y, x + 22, y + 22, width=1.5, outline=col)
            self.c.create_text(x, y + 11, text="VFD", font=("Helvetica", 8, "bold"), fill=col)
            self.c.create_line(x, y + 22, x, y + 36)
            self.c.create_oval(x - 13, y + 36, x + 13, y + 62, width=1.5, outline=col)
            self.c.create_text(x, y + 49, text="M", font=("Helvetica", 10, "bold"), fill=col)
            y0 = y + 66
        elif sym == "load":
            self.c.create_line(x, y, x, y + 16, arrow="last", width=1.5)
            y0 = y + 20
        else:
            self.c.create_rectangle(x - 22, y, x + 22, y + 22, width=1.5, outline=col)
            self.c.create_text(x, y + 11, text=sym or "", font=("Helvetica", 8, "bold"), fill=col)
            y0 = y + 26
        self.c.create_text(x, y0 + 2, text=title, anchor="n", width=w, font=("Helvetica", 9, "bold"),
                           fill=col, justify="center")
        if sub:
            self.c.create_text(x, y0 + 30, text=sub, anchor="n", width=w, font=("Helvetica", 8),
                               fill="#444444", justify="center")

    def draw(self, node, run, variant=None):
        c = self.c
        c.delete("all")
        c.configure(background="white")
        if run is None:
            c.create_text(20, 20, text="Press Calculate to see the equipment.", anchor="nw")
            return
        E = run["net"]["elements"]
        S = run["setup"]
        els = E.get(node, [])
        if node == "eco" and run.get("eco"):
            eco = run["eco"]
            variant = variant or eco.get("decision") or ("iso" if "iso" in eco else "grid")
            if variant == "iso":
                els = [dict(e, name=e["name"].replace("isolated: ", "")) for e in els
                       if e["name"].startswith("isolated: ") or e["kind"] == "load"]
            else:
                els = [dict(e, name=e["name"].replace("grid: ", "")) for e in els
                       if not e["name"].startswith("isolated: ")]
        if node in ("L0", "L1", "L2"):
            self.draw_line(node, run)
            return
        if node == "source":
            c.create_text(30, 20, text="63 kV grid  (S_sc = %.0f MVA)" % run["params"]["grid.Ssc"], anchor="w")
            self.tr(200, 80, "T0 63/20 kV")
            c.create_line(200, 30, 200, 58)
            c.create_line(200, 102, 200, 140)
            self.cb(200, 125, cb_label("Q0", next((e["rating"] for e in els if e["name"] == "CB Q0"), "")))
            c.create_line(80, 160, 420, 160, width=3)
            c.create_text(430, 160, text="20 kV", anchor="w")
            c.create_line(200, 140, 200, 160)
            c.create_line(320, 160, 320, 210, arrow="last")
            c.create_text(320, 215, text="L0 to village (%s km)" % run["params"]["geo.L0_len"], anchor="n")
            return
        trs = [e for e in els if e["kind"].startswith("transformer 20/0.4")]
        ups = [e for e in els if e["kind"].startswith("transformer 0.4/20")]
        cbs = {e["name"]: e for e in els if e["kind"] == "circuit breaker"}
        lv = [e for e in els if e["kind"] not in ("circuit breaker",) and not e["kind"].startswith("transformer")]
        feeder_cb = cbs.pop("CB F1 feeder breaker", None)
        if feeder_cb:   # shown with the feeder itself
            lv = [dict(e, detail=e["detail"] + "\n" + feeder_cb["rating"]) if e["kind"] == "LV cable" else e
                  for e in lv]
        if ups:  # village plants are drawn on the MV side with their step-up transformer
            lv = [e for e in lv if not ("generator" in e["kind"] or "hydro" in e["kind"])]
        # groups of LV items per transformer
        motor2 = next((e for e in lv if e["name"] == "Lift 2 motor"), None)
        if motor2 and any("drive" in e["kind"] for e in lv):   # motor is drawn under its drive
            lv = [e for e in lv if e is not motor2]
        groups = [[] for _ in trs] or [[]]
        for e in lv:
            g = 0
            if len(trs) == 2 and not any(k in e["name"] for k in ("Lift", "ATV", "filter", "motor")):
                g = 1
            groups[g].append(e)
        width_per = [max(1, len(g)) * 190 for g in groups]
        x = 40
        y_mv = 50
        n_out = sum(1 for ln in ("L1", "L2") if node == "village" and E.get(ln))
        total_w = sum(width_per) + 210 * len(ups) + 110 * n_out + 160
        c.configure(scrollregion=(0, 0, max(900, total_w), 520))
        inc = {"village": "from L0 (source)", "ski": "from L1 (village)", "eco": "from L2 (village)"}[node]
        if trs:
            c.create_line(x, y_mv, total_w - 60, y_mv, width=3)
            c.create_text(x + 290, y_mv - 10, text="20 kV bus   " + inc, anchor="w", font=("Helvetica", 9, "bold"))
            qin = {"village": "CB Q1", "ski": "CB Q3", "eco": "CB Q5"}[node]
            if qin in cbs:
                self.cb(x + 20, y_mv - 26, cb_label(qin[3:], cbs[qin]["rating"]))
        else:
            c.create_text(x, 20, text="Isolated microgrid (no MV connection) - LV 400 V bus", anchor="w")
        xs = x + 60
        lv_cbs = [k for k in cbs if k in ("CB Q2", "CB Q4", "CB Q4b", "CB Q6")]
        for gi, g in enumerate(groups):
            wgrp = width_per[gi]
            xt = xs + wgrp / 2 - 75
            y_lv = 230
            if trs:
                t = trs[gi]
                c.create_line(xt, y_mv, xt, y_mv + 45)
                self.cb(xt, y_mv + 25)
                self.tr(xt, y_mv + 75, t["name"] + "\n" + t["rating"])
                c.create_line(xt, y_mv + 97, xt, y_lv)
                if gi < len(lv_cbs):
                    self.cb(xt, y_lv - 30, cb_label(lv_cbs[gi][3:], cbs[lv_cbs[gi]]["rating"]))
            c.create_line(xs, y_lv, xs + wgrp - 20, y_lv, width=2.5)
            c.create_text(xs, y_lv - 12, text="0.4 kV", anchor="w", font=("Helvetica", 8))
            for j, e in enumerate(g):
                xe = xs + 80 + j * 190
                k = e["kind"]
                sym = ("F1" if k == "LV cable" else "CB" if k == "service" else
                       "M" if k == "motor" else "VFD" if "drive" in k else "C" if k == "filter"
                       else "G" if ("generator" in k or "hydro" in k) else "BAT" if k == "storage" else "load")
                if "PV" in e["name"]:
                    sym = "PV"
                sub = e["rating"] + ("\n" + e["detail"] if e["detail"] else "")
                if "drive" in k and motor2:
                    # drive -> motor in series: motor symbol under the drive, motor named in the text
                    sym = "VFD+M"
                    sub = f"{e['rating']} drive -> motor {motor2['rating']}" + ("\n" + e["detail"] if e["detail"] else "")
                self.box(xe, y_lv + 26, e["name"], sub, e.get("status", ""), sym)
            xs += wgrp
        for u in ups:
            c.create_line(xs + 40, y_mv, xs + 40, y_mv + 45)
            self.tr(xs + 40, y_mv + 75, u["name"] + "\n" + u["rating"])
            self.box(xs + 40, y_mv + 125, u["name"].replace(" step-up", ""), u["detail"], "", "G")
            xs += 210
        if node == "village":
            j = 0
            for ln, txt in (("L1", "to ski resort"), ("L2", "to eco-district")):
                if E.get(ln):
                    xx = xs + 40 + j * 110
                    j += 1
                    c.create_line(xx, y_mv, xx, y_mv + 60, arrow="last")
                    c.create_text(xx, y_mv + 64, text=f"{ln}\n{txt}", anchor="n", font=("Helvetica", 8))

    def draw_line(self, node, run):
        c = self.c
        e = run["net"]["elements"][node]
        if not e:
            c.create_text(20, 20, text="Line not used in this configuration.", anchor="nw")
            return
        e = e[0]
        c.create_line(60, 80, 600, 80, width=3 if "overhead" in e["kind"] else 2,
                      dash=() if "overhead" in e["kind"] else (6, 3))
        for xx in (60, 600):
            c.create_line(xx, 60, xx, 100, width=3)
        a, b = {"L0": ("source 20 kV", "village"), "L1": ("village", "ski resort"),
                "L2": ("village", "eco-district")}[node]
        c.create_text(60, 110, text=a, anchor="n")
        c.create_text(600, 110, text=b, anchor="n")
        c.create_text(330, 60, text=f"{e['name']}  ({e['kind']})", font=("Helvetica", 11, "bold"))
        c.create_text(330, 100, text=e["rating"] + "   |   " + e["detail"],
                      fill=GREEN if e["status"] == "OK" else RED)


# ---------------------------------------------------------- node window
class NodeWindow(tk.Toplevel):
    def __init__(self, app, node):
        super().__init__(app.root)
        self.app, self.node = app, node
        run = app.current
        self.title(TITLES[node] + (f"  -  {run['label']}" if run else ""))
        self.geometry("1100x720")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.nb = nb

        # --- what is inside
        f = ttk.Frame(nb)
        nb.add(f, text="What is inside")
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True)
        cf = ttk.Frame(pw)
        cv = tk.Canvas(cf, background="white", height=380, highlightthickness=0)
        sx = ttk.Scrollbar(cf, orient="horizontal", command=cv.xview)
        cv.configure(xscrollcommand=sx.set)
        sx.pack(side="bottom", fill="x")
        cv.pack(fill="both", expand=True)
        pw.add(cf, weight=3)
        tf, tv = make_table(pw, height=8)
        pw.add(tf, weight=2)
        sld = SLD(cv)
        sld.draw(node, run)
        if node == "eco" and run and run.get("eco") and len([k for k in ("iso", "grid") if k in run["eco"]]) == 2:
            bar = ttk.Frame(f)
            bar.pack(before=pw, fill="x")
            ttk.Label(bar, text="Variant shown:").pack(side="left", padx=4)
            for k, t in (("iso", "isolated microgrid"), ("grid", "connected by L2")):
                ttk.Button(bar, text=t, command=lambda k=k: sld.draw("eco", run, k)).pack(side="left", padx=2)
            d = run["eco"].get("decision")
            ttk.Label(bar, text=f"   cheaper at {run['params']['geo.L2_len']} km: "
                               + ("connected" if d == "grid" else "isolated"), foreground="#666666").pack(side="left")
        if run:
            els = run["net"]["elements"].get(node, [])
            fill_table(tv, ["element", "type", "rating", "details", "check"],
                       [[e["name"], e["kind"], e["rating"], e["detail"], e["status"]] for e in els],
                       widths=[200, 170, 200, 420, 60])

        # --- calculation
        f2 = ttk.Frame(nb)
        nb.add(f2, text="Calculation (formulas)")
        tfr, txt = make_text(f2)
        tfr.pack(fill="both", expand=True)
        steps = run["log"].for_tags(*LOG_TAGS[node]) if run else []
        render_log(txt, steps)

        if not run:
            return
        # --- curves
        if node in ("village", "ski", "eco", "source", "L0"):
            self.tab_curves(run)
        if node == "ski" and run["net"].get("harm"):
            self.tab_harmonics(run)
        if node == "village":
            self.tab_energy_village(run)
        if node == "eco" and run.get("eco"):
            self.tab_energy_eco(run)
        names = {"L1": ["L1 conductor choice"], "L2": ["L2 conductor choice"],
                 "ski": ["Harmonic compliance steps", "Harmonic filter design", "Ski transformer options",
                         "Filter sizing iterations"],
                 "source": ["Breakers", "Short-circuit currents"],
                 "village": ["LV feeder cable choice", "Breakers", "Network costs"]}
        for nm in names.get(node, []):
            if nm in run["tables"]:
                self.tab_table(nm, *run["tables"][nm])

    def tab_table(self, name, cols, rows):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=name)
        tf, tv = make_table(f, height=14)
        tf.pack(fill="both", expand=True)
        fill_table(tv, cols, rows)
        ttk.Button(f, text="Export CSV", command=lambda: export_csv(cols, rows, self, name)).pack(anchor="e", pady=4)

    def tab_curves(self, run):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Load curve")
        pr = run["prof"]
        pl = Plot(f, 9, 5.2)
        pl.pack(fill="both", expand=True)
        ax1 = pl.fig.add_subplot(211)
        ax2 = pl.fig.add_subplot(212)
        t = np.arange(8760) / 24
        node = self.node
        if node == "ski":
            ax1.stackplot(t, pr.ski_sub, pr.ski_l1, pr.ski_l2, pr.ski_ev,
                          labels=["subscribers", "lift 1", "lift 2", "EV"], linewidth=0)
            P = pr.ski_P
        elif node == "eco":
            ax1.plot(t, pr.eco_P, lw=0.5, label="eco-district")
            P = pr.eco_P
        elif node == "village":
            ax1.stackplot(t, pr.vil_base, pr.vil_ev, labels=["village", "EV"], linewidth=0)
            P = pr.vil_P
        else:
            P = pr.vil_P + pr.ski_P
            ax1.plot(t, P, lw=0.5, label="village + ski")
        ax1.set_ylabel("kW")
        ax1.set_xlim(0, 365)
        ax1.legend(loc="upper right", fontsize=8, ncol=4)
        ax1.set_title(f"Hourly power, peak {P.max():.1f} kW, mean {P.mean():.1f} kW", fontsize=9)
        d = P.reshape(365, 24)
        ax2.plot(np.arange(365), d.sum(1), lw=0.8, label="energy per day (kWh)")
        ax2.set_ylabel("kWh/day")
        ax2.set_xlabel("day of year")
        ax3 = ax2.twinx()
        tt = pr.temp.reshape(365, 24)
        ax3.plot(np.arange(365), tt.mean(1), lw=0.6, color="#c55a11", label="mean temperature")
        ax3.set_ylabel("degC")
        ax3.grid(False)
        ax2.set_xlim(0, 365)
        ax2.legend(loc="upper left", fontsize=8)
        ax3.legend(loc="upper right", fontsize=8)
        pl.draw()

    def tab_harmonics(self, run):
        h = run["net"]["harm"]
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Harmonics")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text=(f"ATV66{h['drive']['model']} {h['drive']['P_kW']} kW   R_sce = {h['Rsce']:.1f}   "
                             f"filter {h['Q_filter']:.0f} kvar   THDi {h['thd_i']:.1f} -> {h['thd_i1']:.1f} %   "
                             f"THDv {h['thd_v0']:.2f} -> {h['thd_v1']:.2f} %"),
                  font=("Helvetica", 11, "bold")).pack(anchor="w", padx=6, pady=4)
        if "steps_table" in h:
            st = h["steps_table"][1]
            txt = "Lecture DG7 method:   " + "   ->   ".join(
                f"step {r[0]} ({r[2] or r[1]}): {r[-1]}" for r in (st[0], *[x for x in st if x[0].startswith("2")][-1:], st[-1]))
            ttk.Label(top, text=txt, foreground="#2e7d32" if h["ok"] else "#c62828").pack(anchor="w", padx=6)
        tf, tv = make_table(f, height=5)
        tf.pack(fill="x")
        fill_table(tv, *h["table"])
        pl = Plot(f, 9, 3.6)
        pl.pack(fill="both", expand=True)
        ax = pl.fig.add_subplot(111)
        hh, z, zn = h["scan"]
        ax.semilogy(hh, zn * 1000, lw=1, label="network only")
        ax.semilogy(hh, z * 1000, lw=1.2, label="network // filter")
        for k in (5, 7, 11, 13):
            ax.axvline(k, color="#bbbbbb", lw=0.6)
        ax.set_xlabel("harmonic order h")
        ax.set_ylabel("|Z| seen by the drive (mohm)")
        ax.set_title("Impedance scan at the ski LV bus (parallel resonance below each tuned branch)", fontsize=9)
        ax.legend(fontsize=8)
        pl.draw()

    def _monthly_plot(self, parent, best, load, title):
        d = best["d"]
        pl = Plot(parent, 9, 3.4)
        pl.pack(fill="both", expand=True)
        ax = pl.fig.add_subplot(111)
        x = np.arange(12)
        gen = best["gen"]
        bars = [("renewables used", monthly(np.minimum(gen, load))),
                ("battery", monthly(d["dis"])), ("biogas", monthly(d["bio"])),
                ("grid import", monthly(d["imp"]))]
        bottom = np.zeros(12)
        for nm, v in bars:
            if v.sum() > 0:
                ax.bar(x, v / 1000, bottom=bottom / 1000, label=nm, width=0.7)
                bottom += v
        ax.plot(x, monthly(load) / 1000, "k_", markersize=22, label="load")
        if d["exp"].sum() > 0:
            ax.plot(x, -monthly(d["exp"]) / 1000, "s", color="#7030a0", markersize=4, label="export (neg.)")
        if d["unmet"].sum() > 0:
            ax.plot(x, monthly(d["unmet"]) / 1000, "x", color=RED, label="unmet")
        ax.set_xticks(x, MONTHS)
        ax.set_ylabel("MWh / month")
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=8, ncol=3)
        pl.draw()

    def tab_energy_village(self, run):
        ev = run["ev"]
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Energy & subscription")
        b = ev["best"]
        ttk.Label(f, text=(f"Best: {b['label']}   NPC {b['NPC']:,.0f} EUR   LCOE {b['LCOE']:.4f} EUR/kWh   "
                           f"renewable {b['REN']:.1f} %   EDF {b['tariff']['option']} {b['P_sub']:.0f} kW"),
                  font=("Helvetica", 11, "bold")).pack(anchor="w", padx=6, pady=4)
        self._monthly_plot(f, b, ev["load"], "Village + ski: monthly energy balance of the chosen system")
        tf, tv = make_table(f, height=6)
        tf.pack(fill="both", expand=True)
        fill_table(tv, *ev["table"])
        tf2, tv2 = make_table(f, height=4)
        tf2.pack(fill="x")
        fill_table(tv2, *ev["tariff_table"])
        f3 = ttk.Frame(self.nb)
        self.nb.add(f3, text="Energy calculation")
        tfr, txt = make_text(f3)
        tfr.pack(fill="both", expand=True)
        render_log(txt, run["log"].for_tags("energy-village"))

    def tab_energy_eco(self, run):
        eco = run["eco"]
        for key, title in (("iso", "Isolated microgrid"), ("grid", "Grid-connected")):
            if key not in eco:
                continue
            f = ttk.Frame(self.nb)
            self.nb.add(f, text=title)
            b = eco[key]["best"]
            ttk.Label(f, text=f"Best: {b['label']}   NPC {b['NPC']:,.0f} EUR   LCOE {b['LCOE']:.3f} EUR/kWh"
                              f"   unmet {b['unmet_pct']:.2f} %", font=("Helvetica", 11, "bold")).pack(anchor="w", padx=6, pady=4)
            self._monthly_plot(f, b, eco["load"], f"Eco-district {title.lower()}: monthly balance")
            tf, tv = make_table(f, height=8)
            tf.pack(fill="both", expand=True)
            fill_table(tv, *eco[key]["table"])
        if "breakeven_km" in eco:
            self.nb.select(self.nb.index("end") - 1)
