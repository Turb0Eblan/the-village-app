"""One 'Calculate' = one Run: loads -> energy -> network -> economy -> KPIs."""
import time
from .calc import Log
from .data import Profiles
from .network import run_network
from .energy import run_village_energy, run_eco_energy
from .geo import apply_map_lengths


def run(p, setup, progress=None, label=None):
    t0 = time.time()
    p = p.snapshot()
    S = dict(setup)
    log = Log()
    say = progress or (lambda m: None)

    apply_map_lengths(p, log)
    say("Building load curves")
    prof = Profiles(p, S, log)

    say("Village energy system")
    ev = run_village_energy(p, S, prof, log, say)

    say("Network study")
    bc = ev["best"]["case"]
    dg = [("PV plant", bc.get("pv", 0)),
          ("River hydro", ev["hydro"]["Pr"] if bc.get("hydro") else 0),
          ("Biogas CHP", bc.get("bio", 0))]
    net = run_network(p, S, prof, log, export_kw=ev["best"]["gen"] if S["vil_res"] else None,
                      dg=dg if S["vil_res"] else None)
    _system_elements(net["elements"]["village"], ev["best"], ev["res"], p)

    eco = None
    if S["eco"]:
        say("Eco-district energy system")
        eco = run_eco_energy(p, S, prof, log, conn=net.get("eco_conn"), progress=say)
        if "iso" in eco:
            _system_elements(net["elements"]["eco"], eco["iso"]["best"], eco["res"], p, "isolated: ")
        if "grid" in eco:
            _system_elements(net["elements"]["eco"], eco["grid"]["best"], eco["res"], p, "grid: ")

    k = {}
    k["Year"] = S["year"]
    k["Village peak (kW)"] = round(float(prof.vil_P.max()), 1)
    k["Ski peak (kW)"] = round(float(prof.ski_P.max()), 1)
    k["Village energy (MWh/yr)"] = round(float(prof.vil_P.sum()) / 1000, 1)
    k["Ski energy (MWh/yr)"] = round(float(prof.ski_P.sum()) / 1000, 1)
    k["T1 village"] = f"{net['trv']['count']} x {net['trv']['row']['Sn_kVA']} kVA"
    k["T2 ski"] = " + ".join(f"{t['row']['Sn_kVA']}" for _, t in net["ski_trs"]) + " kVA"
    k["L1 conductor"] = f"{net['L1']['name']} ({net['L1']['type']})"
    k["dU to village LV (%)"] = round(net["dU_village"], 2)
    k["dU to ski LV (%)"] = round(net["dU_ski"], 2)
    k["Isc village MV Q1 (kA)"] = round(net["isc"]["Q1"], 2)
    k["Isc ski LV Q4 (kA)"] = round(net["isc"]["Q4"], 2)
    fd = net["feeder"]
    k["LV feeder F1"] = f"{fd['cable']['name']}, {fd['L']:.0f} m, dU {fd['cable']['dU']:.2f} %"
    h = net.get("harm")
    k["THDv ski LV after filter (%)"] = round(h["thd_v1"], 2) if h else "-"
    k["Filter (kvar)"] = h["Q_filter"] if h else "-"
    k["New network CAPEX (EUR)"] = round(net["capex_new"])
    k["Ski connection capitalised (EUR)"] = round(net["ski_conn_cap"])
    b = ev["best"]
    k["Village DG system"] = b["label"]
    k["Village NPC (EUR)"] = round(b["NPC"])
    k["Village LCOE (EUR/kWh)"] = round(b["LCOE"], 4)
    k["Village renewable (%)"] = round(b["REN"], 1)
    k["EDF option / subscription"] = f"{b['tariff']['option']} / {b['P_sub']:.0f} kW"
    k["Grid import (MWh/yr)"] = round(b["imp"] / 1000, 1)
    k["Grid export (MWh/yr)"] = round(b["exp"] / 1000, 1)
    k["CO2 (t/yr)"] = round(b["co2"], 1)
    k["Saving vs grid only (EUR NPC)"] = round(ev["base"]["NPC"] - b["NPC"])
    if eco:
        if "iso" in eco:
            k["Eco isolated system"] = eco["iso"]["best"]["label"]
            k["Eco isolated NPC (EUR)"] = round(eco["iso"]["best"]["NPC"])
            k["Eco isolated LCOE (EUR/kWh)"] = round(eco["iso"]["best"]["LCOE"], 3)
        if "grid" in eco:
            k["Eco grid system"] = eco["grid"]["best"]["label"]
            k["Eco grid NPC (EUR)"] = round(eco["grid"]["best"]["NPC"])
        if "breakeven_km" in eco:
            k["Break-even distance (km)"] = round(eco["breakeven_km"], 1)
            k["Break-even, HOMER cost (km)"] = round(eco["breakeven_km_homer"], 1)
            k["Eco decision"] = "grid connection" if eco["decision"] == "grid" else "stand-alone"

    checks = [s for s in log.steps if s.get("status") in ("OK", "FAIL", "LOW")]
    fails = [s for s in checks if s["status"] in ("FAIL", "LOW")]
    run = dict(label=label or f"{S['year']}", setup=S, params=p, log=log, prof=prof, net=net,
               ev=ev, eco=eco, kpi=k, fails=fails, n_checks=len(checks),
               time=time.strftime("%H:%M:%S"), seconds=time.time() - t0)
    tabs = {}
    tabs.update(net["tables"])
    tabs["Village DG options (best 25)"] = ev["table"]
    tabs["EDF tariff options"] = ev["tariff_table"]
    if eco:
        if "iso" in eco:
            tabs["Eco isolated options (best 25)"] = eco["iso"]["table"]
        if "grid" in eco:
            tabs["Eco grid options (best 25)"] = eco["grid"]["table"]
    tabs["Key results"] = (["quantity", "value"], [[a, v] for a, v in k.items()])
    run["tables"] = tabs
    say(f"Done in {run['seconds']:.1f} s")
    return run


def _system_elements(lst, best, res, p, prefix=""):
    c = best["case"]
    if c.get("pv"):
        lst.append(dict(name=prefix + "PV array", kind="generator", rating=f"{c['pv']:.0f} kWp",
                        detail=f"{c['pv'] * res['pv'].sum() / 1000:.0f} MWh/yr", status=""))
    h = res["hydro"].get(c.get("hydro"))
    if h:
        lst.append(dict(name=prefix + h["name"], kind="hydro turbine", rating=f"{h['Pr']:.1f} kW",
                        detail=f"H {h['H']} m, Qd {h['Qd'] * 1000:.0f} L/s, {h['E'] / 1000:.0f} MWh/yr", status=""))
    if c.get("wind"):
        lst.append(dict(name=prefix + "Wind turbines", kind="generator",
                        rating=f"{c['wind']:.0f} x {p['wind.rated']:.0f} kW", detail="", status=""))
    if c.get("bat"):
        lst.append(dict(name=prefix + "Li-ion battery", kind="storage", rating=f"{c['bat']:.0f} kWh",
                        detail=f"converter {p['bat.c_rate'] * c['bat']:.0f} kW", status=""))
    if c.get("bio"):
        lst.append(dict(name=prefix + "Biogas CHP", kind="generator", rating=f"{c['bio']:.0f} kW",
                        detail=f"{best['E_bio'] / 1000:.0f} MWh/yr", status=""))
