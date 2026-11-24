"""Hourly input data (8760 h, year 2010) and the load profiles for each year.

Measured curves (team files, kW):
  Vil.txt       village before EV           Vil_EV.txt  village + EV (94 kW installed)
  Ski.txt       ski resort before renovation Ski_lift.txt / Ski_EV.txt
  Eco.txt       eco-district forecast
The EV and lift changes are rebuilt from these files with the current
parameters, so changing a charger or lift power changes the curves.
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "data")
_cache = {}

EV_VIL_BASE = 94.0   # kW installed in Vil_EV.txt (README_methodology.md)
EV_SKI_BASE = 44.0   # kW installed in Ski_EV.txt


def load(name):
    if name not in _cache:
        _cache[name] = np.loadtxt(os.path.join(DATA_DIR, name + ".txt"))
    return _cache[name]


def month_of_hour():
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    m = np.repeat(np.arange(12), np.array(days) * 24)
    return m


def hour_of_day():
    return np.tile(np.arange(24), 365)


def weekday_of_hour():
    # 1 Jan 2010 was a Friday (0 = Monday)
    d = (np.arange(365) + 4) % 7
    return np.repeat(d, 24)


def tanphi(pf):
    pf = min(max(pf, 0.05), 1.0)
    return np.tan(np.arccos(pf))


class Profiles:
    """All hourly P/Q curves for a given parameter set and year setup."""

    def __init__(self, p, setup, log=None):
        vil = load("Vil")
        vil_ev = load("Vil_EV")
        ski = load("Ski")
        ski_lift = load("Ski_lift")
        ski_ev = load("Ski_EV")
        self.eco_P = load("Eco").copy()

        # ---- village
        ev_shape = np.clip(vil_ev - vil, 0, None)          # kW for 94 kW installed
        ev_kw = p["vil.ev_fast"] + p["vil.ev_dual"]
        self.vil_ev = ev_shape * (ev_kw / EV_VIL_BASE) if setup["ev_village"] else 0 * vil
        self.vil_base = vil.copy()
        self.vil_P = self.vil_base + self.vil_ev
        self.vil_Q = self.vil_base * tanphi(p["vil.pf"]) + self.vil_ev * tanphi(p["vil.ev_pf"])

        # ---- ski resort: split measured curve into subscribers + 2 lifts
        base = float(ski.min())
        excess = ski - base
        meas = p["ski.lift_meas"]
        l1 = excess * p["ski.lift1_kw"] / (2 * meas)
        l2_kw = p["ski.lift2_new_kw"] if setup["lift2_vfd"] else meas
        l2 = excess * l2_kw / (2 * meas)
        ev_ski_shape = np.clip(ski_ev - ski_lift, 0, None)
        self.ski_ev = ev_ski_shape * (p["ski.ev_dual"] / EV_SKI_BASE) if setup["ev_ski"] else 0 * ski
        self.ski_sub = np.full(8760, base)
        self.ski_l1, self.ski_l2 = l1, l2
        self.ski_lifts_P = l1 + l2
        self.ski_other_P = self.ski_sub + self.ski_ev
        self.ski_P = self.ski_lifts_P + self.ski_other_P
        pf2 = p["ski.pf_vfd"] if setup["lift2_vfd"] else p["ski.pf_slip"]
        self.ski_lifts_Q = l1 * tanphi(p["ski.pf_slip"]) + l2 * tanphi(pf2)
        self.ski_other_Q = self.ski_sub * tanphi(p["ski.pf_sub"]) + self.ski_ev * tanphi(p["vil.ev_pf"])
        self.ski_Q = self.ski_lifts_Q + self.ski_other_Q
        self.eco_Q = self.eco_P * tanphi(p["eco.pf"])

        # ---- weather
        self.ghi = load("ghi_kWh_m2")          # kWh/m2 in the hour = mean kW/m2
        self.temp = load("temperature_C")
        self.wind10 = load("wind_10m")
        self.biomass_tpd = load("biomass_tpd")
        self.month = month_of_hour()
        self.hour = hour_of_day()
        self.wday = weekday_of_hour()

        if log is not None:
            T = "loads"
            log.head(T, "Load curves for this year")
            log.add(T, "Ski: subscriber baseline", "P_base = min(P_ski,measured)", base, "kW")
            log.add(T, "Ski: lift share of measured curve", "P_lifts(t) = P_ski(t) - P_base;  max",
                    float(excess.max()), "kW", note=f"~ 2 x {meas:.0f} kW lifts at full load")
            log.add(T, "Ski: lift 1 curve", f"P_L1 = P_lifts x {p['ski.lift1_kw']:.0f}/(2 x {meas:.0f})",
                    float(l1.max()), "kW peak")
            log.add(T, "Ski: lift 2 curve", f"P_L2 = P_lifts x {l2_kw:.0f}/(2 x {meas:.0f})",
                    float(l2.max()), "kW peak",
                    note="VFD renovation" if setup["lift2_vfd"] else "original slip-ring")
            if setup["ev_village"]:
                log.add(T, "Village EV curve", f"P_EV = (Vil_EV - Vil) x {ev_kw:.0f}/{EV_VIL_BASE:.0f}",
                        float(self.vil_ev.max()), "kW peak")
            if setup["ev_ski"]:
                log.add(T, "Ski EV curve", f"P_EV = (Ski_EV - Ski_lift) x {p['ski.ev_dual']:.0f}/{EV_SKI_BASE:.0f}",
                        float(self.ski_ev.max()), "kW peak")
            for name, P_ in (("Village", self.vil_P), ("Ski resort", self.ski_P), ("Eco-district", self.eco_P)):
                log.add(T, f"{name}: peak / mean / energy",
                        "max P, mean P, sum P x 1 h",
                        f"{P_.max():.1f} kW / {P_.mean():.1f} kW / {P_.sum() / 1000:.1f} MWh")

    def subscribed(self, p):
        vil = p["vil.n6"] * 6 + p["vil.n9"] * 9 + p["vil.n12"] * 12 + p["vil.S_mun"] + p["vil.S_saw"]
        ski = p["ski.n3"] * 3 + p["ski.n12"] * 12
        eco = p["eco.n6"] * 6 + p["eco.n9"] * 9 + p["eco.n3"] * 3
        return vil, ski, eco
