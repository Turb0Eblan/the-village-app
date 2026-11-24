"""Dashboard page: key figures of one run as tiles plus six small charts
(energy mix, typical days, NPC breakdown, network margins, trends)."""
import tkinter as tk
from tkinter import ttk
import numpy as np

from .ui_common import Plot, direction
from .ui_nodes import monthly, MONTHS
from .params import YEARS

# light dashboard surface (explicit colours, readable in macOS dark mode too)
SURF, CARD, LINE = "#f4f3ef", "#fcfcfb", "#e3e2de"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#7b7a75"
GOOD, WARN, BAD = "#2e7d32", "#b26a00", "#c62828"
# energy sources (validated categorical order: yellow, blue, aqua, violet) + neutral grid
C_PV, C_HY, C_BIO, C_BAT, C_GRID = "#eda100", "#2a78d6", "#1baf7a", "#6250d6", "#9a9994"
C_MAIN, C_DIM = "#2a78d6", "#c9c8c3"


def _money(v):
    v = float(v)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f} M EUR"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f} k EUR"
    return f"{v:.0f} EUR"


class Tile(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, background=CARD, highlightbackground=LINE, highlightthickness=1,
                         padx=12, pady=8)
        self.t = tk.Label(self, background=CARD, foreground=INK2, font=("Helvetica", 11), anchor="w")
        self.v = tk.Label(self, background=CARD, foreground=INK, font=("Helvetica", 22, "bold"), anchor="w")
        self.s = tk.Label(self, background=CARD, foreground=MUTED, font=("Helvetica", 10), anchor="w",
                          justify="left")
        self.t.pack(fill="x")
        self.v.pack(fill="x")
        self.s.pack(fill="x")

    def set(self, title, value, sub="", color=INK):
        self.t.configure(text=title)
        self.v.configure(text=value, foreground=color)
        self.s.configure(text=sub)


class DashboardPage:
    def __init__(self, parent, app):
        self.app = app
        self.frame = tk.Frame(parent, background=SURF)
        bar = tk.Frame(self.frame, background=SURF)
        bar.pack(fill="x", padx=10, pady=(8, 4))
        self.title = tk.Label(bar, text="Dashboard", background=SURF, foreground=INK,
                              font=("Helvetica", 16, "bold"))
        self.title.pack(side="left")
        self.run_var = tk.StringVar()
        self.run_cb = ttk.Combobox(bar, textvariable=self.run_var, width=24, state="readonly")
        self.run_cb.pack(side="right")
        self.run_cb.bind("<<ComboboxSelected>>", lambda e: self.draw())
        tk.Label(bar, text="run:", background=SURF, foreground=INK2).pack(side="right", padx=4)
        tiles = tk.Frame(self.frame, background=SURF)
        tiles.pack(fill="x", padx=10)
        self.tiles = []
        for k in range(8):
            t = Tile(tiles)
            t.grid(row=k // 4, column=k % 4, sticky="nsew", padx=4, pady=4)
            tiles.columnconfigure(k % 4, weight=1, uniform="t")
            self.tiles.append(t)
        self.plot = Plot(self.frame, 12, 6.2, toolbar=False)
        self.plot.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.plot.fig.set_facecolor(SURF)

    # ------------------------------------------------------------------
    def refresh(self):
        runs = self.app.runs
        labels = [f"{r['label']}  ({r['time']})" for r in runs]
        self.run_cb["values"] = labels
        cur = self.app.current
        if cur in runs:
            self.run_var.set(labels[runs.index(cur)])
        elif labels:
            self.run_var.set(labels[-1])
        self.draw()

    def run(self):
        runs = self.app.runs
        vals = list(self.run_cb["values"])
        if self.run_var.get() in vals:
            return runs[vals.index(self.run_var.get())]
        return self.app.current

    def draw(self):
        r = self.run()
        fig = self.plot.fig
        fig.clear()
        if not r:
            self.title.configure(text="Dashboard  -  press Calculate")
            for t in self.tiles:
                t.set("", "-")
            self.plot.draw()
            return
        y = r["setup"]["year"]
        self.title.configure(text=f"Dashboard  -  {r['label']}   {YEARS.get(y, {}).get('title', '')}")
        self.fill_tiles(r)
        axs = fig.subplots(2, 3)
        self.ch_monthly(axs[0][0], r)
        self.ch_days(axs[0][1], r)
        self.ch_npc(axs[0][2], r)
        self.ch_margins(axs[1][0], r)
        self.ch_trend(axs[1][1], "Village NPC (EUR)", "Village NPC by run", 1e6, "M EUR")
        self.ch_trend(axs[1][2], "Village renewable (%)", "Renewable share by run", 1, "%")
        for ax in fig.axes:
            ax.set_facecolor(CARD)
            ax.tick_params(colors=INK2, labelsize=8)
            for sp in ax.spines.values():
                sp.set_color(LINE)
            ax.grid(True, axis="y", color=LINE, linewidth=0.6)
            ax.set_axisbelow(True)
        fig.tight_layout(pad=1.2, h_pad=1.6, w_pad=1.6)
        self.plot.canvas.draw_idle()

    # ------------------------------------------------------------------ tiles
    def fill_tiles(self, r):
        k, b, ev = r["kpi"], r["ev"]["best"], r["ev"]
        save = ev["base"]["NPC"] - b["NPC"]
        self.tiles[0].set("Village + ski system NPC", _money(b["NPC"]),
                          f"{'saves' if save >= 0 else 'costs'} {_money(abs(save))} vs grid only\n{b['label']}")
        self.tiles[1].set("Cost of energy (LCOE)", f"{b['LCOE']:.3f} EUR/kWh",
                          f"EDF {b['tariff']['option']}, subscription {b['P_sub']:.0f} kW")
        self.tiles[2].set("Renewable share", f"{b['REN']:.1f} %",
                          "net-zero target" + (" met" if b["REN"] >= 99.9 else " not met")
                          if r["setup"].get("net_zero") else f"renewables {b['E_ren'] / 1e3:,.0f} MWh/yr",
                          GOOD if b["REN"] >= 50 else INK)
        self.tiles[3].set("CO2 from grid import", f"{b['co2']:.0f} t/yr",
                          f"import {b['imp'] / 1e3:,.0f} MWh, export {b['exp'] / 1e3:,.0f} MWh")
        self.tiles[4].set("Peak load village / ski", f"{k['Village peak (kW)']:.0f} / {k['Ski peak (kW)']:.0f} kW",
                          f"T1 {k['T1 village']}, T2 {k['T2 ski']}")
        net = r["net"]
        self.tiles[5].set("Voltage drop village / ski", f"{net['dU_village']:.1f} / {net['dU_ski']:.1f} %",
                          f"limit {r['params']['geo.dU_tot_max']:.0f} %, L1 {net['L1']['name']}",
                          GOOD if max(net["dU_village"], net["dU_ski"]) <= r["params"]["geo.dU_tot_max"] else BAD)
        eco = r.get("eco")
        if eco and eco.get("decision"):
            d = eco["decision"]
            best = eco["grid" if d == "grid" else "iso"]["best"]
            self.tiles[6].set("Eco-district", "grid connection" if d == "grid" else "stand-alone",
                              f"NPC {_money(best['NPC'])}, break-even {eco.get('breakeven_km', 0):.1f} km\n{best['label']}")
        elif eco and "iso" in eco:
            self.tiles[6].set("Eco-district", "stand-alone", f"NPC {_money(eco['iso']['best']['NPC'])}")
        else:
            self.tiles[6].set("Eco-district", "not built", "only from 2026")
        fails = [x for x in r["fails"] if x["status"] == "FAIL"]
        warns = [x for x in r["fails"] if x["status"] != "FAIL"]
        nf = len(fails)
        sub = ("fails: " + ", ".join(x["title"] for x in fails[:2]) + ("..." if nf > 2 else "")) if nf else (
            "\u26a0 " + "; ".join(x["title"] for x in warns[:2]) if warns else "all limits respected")
        self.tiles[7].set("Design checks", ("\u2717 " if nf else "\u26a0 " if warns else "\u2713 ")
                          + f"{r['n_checks'] - nf} / {r['n_checks']} pass", sub,
                          BAD if nf else WARN if warns else GOOD)

    # ------------------------------------------------------------------ charts
    def _parts(self, r):
        ev = r["ev"]
        b, res, load = ev["best"], ev["res"], ev["load"]
        c, d = b["case"], b["d"]
        pv = c.get("pv", 0) * res["pv"]
        hy = res["hydro"].get(c.get("hydro"))
        hyd = hy["hourly"] if hy else np.zeros_like(load)
        gen = b["gen"]
        used = np.minimum(gen, load)
        with np.errstate(divide="ignore", invalid="ignore"):
            fpv = np.where(gen > 0, pv / gen, 0)
        return load, [("PV", used * fpv, C_PV), ("hydro", used * (1 - fpv), C_HY),
                      ("biogas", d["bio"], C_BIO), ("battery", d["dis"], C_BAT), ("grid import", d["imp"], C_GRID)], pv, hyd

    def ch_monthly(self, ax, r):
        load, parts, _, _ = self._parts(r)
        x = np.arange(12)
        bottom = np.zeros(12)
        for nm, v, col in parts:
            m = monthly(v) / 1e3
            if m.sum() <= 0:
                continue
            ax.bar(x, m, bottom=bottom, color=col, width=0.72, label=nm, edgecolor=CARD, linewidth=1)
            bottom += m
        ax.plot(x, monthly(load) / 1e3, "_", color=INK, markersize=14, markeredgewidth=2, label="load")
        ax.set_xticks(x, MONTHS)
        ax.set_ylabel("MWh", color=INK2, fontsize=8)
        ax.set_title("Monthly supply of the load", fontsize=10, color=INK, loc="left")
        ax.legend(fontsize=7, ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1))

    def ch_days(self, ax, r):
        load, parts, pv, hyd = self._parts(r)
        ren = pv + hyd
        L = load.reshape(365, 24)
        R = ren.reshape(365, 24)
        h = np.arange(24)
        for (a, z), ls, nm in (((0, 31), "-", "Jan"), ((181, 212), "--", "Jul")):
            ax.plot(h, L[a:z].mean(0), ls, color=INK, lw=1.6, label=f"load {nm}")
            ax.plot(h, R[a:z].mean(0), ls, color=C_MAIN, lw=1.6, label=f"PV + hydro {nm}")
        ax.set_xlim(0, 23)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_ylabel("kW", color=INK2, fontsize=8)
        ax.set_title("Average day: load vs local generation", fontsize=10, color=INK, loc="left")
        ax.legend(fontsize=7, ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1))

    def ch_npc(self, ax, r):
        comps = r["ev"]["best"]["comps"]
        items = sorted(((k, v[0]) for k, v in comps.items()), key=lambda kv: kv[1])
        names = [k for k, _ in items]
        vals = [v / 1e6 for _, v in items]
        ax.barh(names, vals, color=C_MAIN, height=0.6)
        for i, v in enumerate(vals):
            ax.text(v, i, f"  {v:.2f}", va="center", fontsize=8, color=INK)
        ax.set_xlabel("M EUR over the project life", color=INK2, fontsize=8)
        ax.set_title("NPC breakdown of the chosen system", fontsize=10, color=INK, loc="left")
        ax.grid(False)
        ax.set_xlim(0, max(vals + [0.01]) * 1.25)

    def ch_margins(self, ax, r):
        p, net = r["params"], r["net"]
        rows = [("dU village", net["dU_village"], p["geo.dU_tot_max"], "%"),
                ("dU ski", net["dU_ski"], p["geo.dU_tot_max"], "%"),
                ("T1 loading", net["trv"]["loading"] * 100, p["geo.tr_max_load"], "%"),
                ("T2 loading", net["ski_trs"][0][1]["loading"] * 100, p["geo.tr_max_load"], "%"),
                ("L1 current", net["L1"]["I_des"], net["L1"]["Imax"], "A"),
                ("LV feeder dU", net["feeder"]["cable"]["dU"], p["lvf.dU_max"], "%")]
        h = net.get("harm")
        if h:
            rows.append(("THDv ski", h["thd_v1"], 8.0, "%"))
        rows = rows[::-1]
        pct = [v / lim * 100 for _, v, lim, _ in rows]
        cols = [GOOD if q <= 80 else WARN if q <= 100 else BAD for q in pct]
        ax.barh([n for n, *_ in rows], pct, color=cols, height=0.6)
        for i, ((n, v, lim, u), q) in enumerate(zip(rows, pct)):
            mark = "✓" if q <= 100 else "✗"
            ax.text(q, i, f"  {mark} {v:.1f} / {lim:g} {u}", va="center", fontsize=7.5, color=INK)
        ax.axvline(100, color=BAD, lw=1, ls="--")
        ax.set_xlim(0, max(pct + [100]) * 1.55)
        ax.set_xlabel("% of the limit (green < 80 %, amber < 100 %)", color=INK2, fontsize=8)
        ax.set_title("Network margins", fontsize=10, color=INK, loc="left")
        ax.grid(False)

    def ch_trend(self, ax, key, title, scale, unit):
        runs = [x for x in self.app.runs if isinstance(x["kpi"].get(key), (int, float))]
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        if not runs:
            return
        vals = [x["kpi"][key] / scale for x in runs]
        d = direction(key)
        b = (max if d > 0 else min)(vals) if len(set(vals)) > 1 else None
        cur = self.run()
        cols = [C_MAIN if (b is None or v == b) else C_DIM for v in vals]
        labels = [x["label"].replace("  ", "\n", 1) for x in runs]
        bars = ax.bar(range(len(vals)), vals, color=cols, width=0.62)
        for i, (x, v) in enumerate(zip(runs, vals)):
            ax.text(i, v, ("★ " if v == b else "") + (f"{v:.2f}" if scale > 1 else f"{v:.1f}"),
                    ha="center", va="bottom", fontsize=7.5, color=INK,
                    fontweight="bold" if x is cur else "normal")
            if x is cur:
                bars[i].set_edgecolor(INK)
                bars[i].set_linewidth(1.2)
        ax.set_xticks(range(len(vals)), labels, fontsize=7)
        ax.set_ylabel(unit, color=INK2, fontsize=8)
        ax.set_ylim(0, max(vals) * 1.2 if max(vals) > 0 else 1)
        ax.set_xlim(-0.6, max(len(vals), 4) - 0.4)
