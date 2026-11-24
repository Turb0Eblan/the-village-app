"""Hourly energy model of the village (grid-connected) and of the eco-district
(isolated or grid-connected). A simplified HOMER: resource -> production ->
load-following dispatch -> costs (NPC, LCOE) -> search over component sizes.
"""
import itertools
import math
import numpy as np
from .calc import crf, pwf, npc_component

RHO_G = 1000 * 9.81
NU = 1.0e-6  # water kinematic viscosity, m2/s


# ------------------------------------------------------------- resources
def pv_per_kwp(p, prof):
    G = prof.ghi  # kW/m2 average in the hour
    Tc = prof.temp + (p["pv.noct"] - 20) / 0.8 * G
    return np.clip(p["pv.derate"] * G * (1 + p["pv.tcoef"] / 100 * (Tc - 25)), 0, None)


def wind_per_turbine(p, prof):
    v = prof.wind10 * (p["wind.hub"] / 10) ** p["wind.alpha"]
    vin, vr, vout, Pr = p["wind.v_in"], p["wind.v_r"], p["wind.v_out"], p["wind.rated"]
    P = np.where((v >= vin) & (v < vr), Pr * ((v - vin) / (vr - vin)) ** 3, 0.0)
    P = np.where((v >= vr) & (v <= vout), Pr, P)
    return P


def head_loss(Q, D, L, rough_mm):
    if Q <= 0:
        return 0.0
    A = math.pi * D ** 2 / 4
    v = Q / A
    Re = v * D / NU
    f = 0.25 / math.log10(rough_mm / 1000 / (3.7 * D) + 5.74 / Re ** 0.9) ** 2
    return f * L / D * v ** 2 / (2 * 9.81)


def hydro_site(p, site):
    """site: 'village', 'A', 'B'. Returns dict with hourly kW and costs."""
    fl = p.table("flows")
    if site == "village":
        H, D, L, eta = p["hyd.v_head"], p["hyd.v_D"], p["hyd.v_L"], p["hyd.v_eta"] / 100
        Qd = p["hyd.v_Qd"]
        flows = np.array([r["river_m3s"] for r in fl])
        name = "River (village)"
    else:
        H, D, L = p[f"hyd.e{site}_head"], p[f"hyd.e{site}_D"], p[f"hyd.e{site}_L"]
        eta = p["hyd.e_eta"] / 100
        Qd = p["hyd.e_Qd"] / 1000
        flows = np.array([r["stream_Ls"] for r in fl]) / 1000
        name = f"Stream intake {site}"
    avail = flows * (1 - p["hyd.reserved"] / 100)
    Qm = np.where(avail >= p["hyd.min_ratio"] / 100 * Qd, np.minimum(avail, Qd), 0.0)
    Pm = np.array([eta * RHO_G * q * (H - head_loss(q, D, L, p["hyd.rough"])) / 1000 for q in Qm])
    hf_d = head_loss(Qd, D, L, p["hyd.rough"])
    Pr = eta * RHO_G * Qd * (H - hf_d) / 1000
    capex = p["hyd.capex_kw"] * Pr + p["hyd.pipe_eur_m"] * L * D
    month = np.repeat(np.arange(12), np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]) * 24)
    hourly = Pm[month]
    v = Qd / (math.pi * D ** 2 / 4)
    return dict(site=site, name=name, H=H, D=D, L=L, eta=eta, Qd=Qd, hf=hf_d, v=v, Pr=Pr,
                capex=capex, om=p["hyd.om_pct"] / 100 * capex, hourly=hourly,
                monthly_kw=Pm, Qm=Qm, E=float(hourly.sum()))


def bio_daily_kwh(p, prof):
    return prof.biomass_tpd * p["bio.collect"] / 100 * p["bio.yield"] * p["bio.lhv"] * p["bio.eta_el"] / 100


# ------------------------------------------------------------- tariff
def periods(prof):
    m, h, wd = prof.month, prof.hour, prof.wday
    winter = np.isin(m, [10, 11, 0, 1, 2])
    off = (h >= 22) | (h < 6) | (wd == 6)
    peakh = np.isin(m, [11, 0, 1]) & np.isin(h, [9, 10, 18, 19]) & (wd < 5)
    per = np.where(winter, np.where(peakh, 0, np.where(off, 2, 1)), np.where(off, 4, 3))
    return per


def grid_bill(imp, p, prof):
    per = periods(prof)
    over_price = p["econ.overrun"]
    srt = np.sort(imp)[::-1]
    csum = np.cumsum(srt)
    top = max(10.0, math.ceil(imp.max() / 10) * 10)
    cands = np.arange(0, top + 10, 10.0)
    # overrun(P) = sum max(0, imp - P)
    idx = np.searchsorted(-srt, -cands, side="left")       # number of hours with imp > P
    over = np.where(idx > 0, csum[np.maximum(idx - 1, 0)] - cands * idx, 0.0)
    res = []
    for r in p.table("tariff"):
        rates = np.array([r["WinterPeak"], r["WinterFull"], r["WinterOff"], r["SummerFull"], r["SummerOff"]]) / 100
        energy = float(np.sum(imp * rates[per]))
        tot = r["fixed"] * cands + energy + over_price * over
        k = int(np.argmin(tot))
        hours = int(np.sum(imp > cands[k]))
        res.append(dict(option=r["option"], P_sub=float(cands[k]), fixed=r["fixed"] * cands[k],
                        energy=energy, over_kwh=float(over[k]), overrun=over_price * float(over[k]),
                        hours_over=hours, total=float(tot[k]), util=float(imp.sum() / max(cands[k], 1))))
    best = min(res, key=lambda d: d["total"])
    return best, res


# ------------------------------------------------------------- dispatch
def dispatch(load, gen, grid, p, bat_kwh=0.0, bio_kw=0.0, bio_day=None):
    """Load following: renewables -> battery -> biogas -> grid (or unmet)."""
    n = len(load)
    net = gen - load
    if bat_kwh <= 0 and bio_kw <= 0:
        sur = np.clip(net, 0, None)
        de = np.clip(-net, 0, None)
        z = np.zeros(n)
        return dict(imp=de if grid else z, exp=sur if grid else z, curt=z if grid else sur,
                    unmet=z if grid else de, bio=z, dis=z, ch=z, soc=z)
    eff = math.sqrt(p["bat.eff"] / 100)
    pmax = p["bat.c_rate"] * bat_kwh
    smin = p["bat.soc_min"] / 100 * bat_kwh
    soc = bat_kwh
    budget = 0.0
    imp = [0.0] * n; exp = [0.0] * n; curt = [0.0] * n; unmet = [0.0] * n
    bio = [0.0] * n; dis = [0.0] * n; ch = [0.0] * n; socs = [0.0] * n
    netl = net.tolist()
    for t in range(n):
        if t % 24 == 0 and bio_day is not None:
            budget = float(bio_day[t // 24])
        x = netl[t]
        if x >= 0:
            c = min(x, pmax, (bat_kwh - soc) / eff) if bat_kwh > 0 else 0.0
            soc += c * eff
            ch[t] = c
            r = x - c
            if grid:
                exp[t] = r
            else:
                curt[t] = r
        else:
            d = -x
            if bat_kwh > 0:
                dd = min(d, pmax, (soc - smin) * eff)
                if dd > 0:
                    soc -= dd / eff
                    dis[t] = dd
                    d -= dd
            if d > 0 and bio_kw > 0 and budget > 0:
                b = min(d, bio_kw, budget)
                budget -= b
                bio[t] = b
                d -= b
            if d > 0:
                if grid:
                    imp[t] = d
                else:
                    unmet[t] = d
        socs[t] = soc
    A = np.array
    return dict(imp=A(imp), exp=A(exp), curt=A(curt), unmet=A(unmet), bio=A(bio), dis=A(dis),
                ch=A(ch), soc=A(socs))


# ------------------------------------------------------------- evaluation
def evaluate(case, load, res, p, prof, mode, extra=None):
    """mode: 'village' (grid with EDF tariff), 'iso', 'grid_simple' (retail price)."""
    i, n = p["econ.i"] / 100, int(p["econ.n"])
    gen = np.zeros(len(load))
    comps = {}
    pv_capex = p["pv.capex_eco"] if mode != "village" else p["pv.capex"]
    if case["pv"] > 0:
        gen = gen + case["pv"] * res["pv"]
        comps["PV"] = npc_component(case["pv"] * pv_capex, case["pv"] * p["pv.om"], p["pv.life"], i, n)
    if case.get("wind", 0) > 0:
        gen = gen + case["wind"] * res["wind"]
        comps["Wind"] = npc_component(case["wind"] * p["wind.capex"], case["wind"] * p["wind.om"],
                                      p["wind.life"], i, n)
    hy = res["hydro"].get(case.get("hydro"))
    if hy:
        gen = gen + hy["hourly"]
        comps["Hydro"] = npc_component(hy["capex"], hy["om"], p["hyd.life"], i, n)
    bat = case.get("bat", 0)
    bio = case.get("bio", 0)
    d = dispatch(load, gen, mode != "iso", p, bat, bio, res["bio_day"] if bio else None)
    if bat > 0:
        comps["Battery"] = npc_component(bat * p["bat.capex"], bat * p["bat.om"], p["bat.life"], i, n)
        conv = p["bat.c_rate"] * bat
        comps["Converter"] = npc_component(conv * p["bat.conv_capex"], 0, p["bat.conv_life"], i, n)
    E_bio = float(d["bio"].sum())
    if bio > 0:
        comps["Biogas"] = npc_component(bio * p["bio.capex"], E_bio * p["bio.om"], p["bio.life"], i, n)
    imp, exp = float(d["imp"].sum()), float(d["exp"].sum())
    E_load = float(load.sum())
    unmet = float(d["unmet"].sum())
    out = dict(case=case, imp=imp, exp=exp, unmet=unmet, curt=float(d["curt"].sum()),
               E_load=E_load, E_ren=float(gen.sum()) + E_bio, E_bio=E_bio, d=d, gen=gen)
    grid_ann = 0.0
    if mode == "village":
        best, opts = grid_bill(d["imp"], p, prof)
        out["tariff"], out["tariff_all"] = best, opts
        grid_ann = best["total"] - exp * p["econ.sell"]
        out["P_sub"] = best["P_sub"]
    elif mode == "grid_simple":
        grid_ann = imp * p["econ.retail"] - exp * p["econ.sell"]
    if mode != "iso":
        comps["Grid"] = (grid_ann * pwf(i, n), dict(capex=0, om=grid_ann * pwf(i, n), repl=0, salvage=0))
    if extra:
        for k, v in extra.items():
            comps[k] = v
    npc = sum(v[0] for v in comps.values())
    capex = sum(v[1]["capex"] for v in comps.values())
    served = E_load - unmet
    out.update(comps=comps, NPC=npc, CAPEX=capex, grid_ann=grid_ann,
               LCOE=npc * crf(i, n) / max(served + exp, 1),
               REN=100 * (1 - imp / max(served + exp, 1)),
               unmet_pct=100 * unmet / E_load,
               co2=imp * p["econ.co2_grid"] / 1e6,
               peak_imp=float(d["imp"].max()) if mode != "iso" else 0.0)
    return out


def describe(case):
    parts = []
    if case.get("pv"):
        parts.append(f"PV {case['pv']:.0f} kWp")
    if case.get("hydro"):
        parts.append({"village": "river hydro", "A": "hydro A", "B": "hydro B"}[case["hydro"]])
    if case.get("wind"):
        parts.append(f"{case['wind']:.0f} x wind")
    if case.get("bat"):
        parts.append(f"bat {case['bat']:.0f} kWh")
    if case.get("bio"):
        parts.append(f"biogas {case['bio']:.0f} kW")
    return " + ".join(parts) if parts else "grid only"


def optimise(name, load, res, p, prof, mode, space, constraints, progress=None, extra=None):
    keys = list(space)
    combos = list(itertools.product(*[space[k] for k in keys]))
    results = []
    for j, vals in enumerate(combos):
        case = dict(zip(keys, vals))
        r = evaluate(case, load, res, p, prof, mode, extra)
        feas = True
        why = []
        if mode == "iso" and r["unmet_pct"] > constraints.get("max_unmet", 0.1):
            feas = False
            why.append(f"unmet {r['unmet_pct']:.2f} %")
        if constraints.get("net_zero") and r["exp"] < r["imp"]:
            feas = False
            why.append("export < import")
        if r["REN"] < constraints.get("min_ren", 0):
            feas = False
            why.append("ren. fraction")
        r["feasible"], r["why"] = feas, ", ".join(why)
        r["label"] = describe(case)
        results.append(r)
        if progress and j % 4 == 0:
            progress(f"{name}: {j + 1}/{len(combos)}")
    results.sort(key=lambda r: (not r["feasible"], r["NPC"]))
    return results


def bound_warn(best, space, log, tag):
    """Like HOMER: warn when the winner sits on the upper edge of the search space."""
    for k, vals in space.items():
        nums = [v for v in vals if isinstance(v, (int, float))]
        if len(nums) > 1 and best["case"].get(k) == max(nums) and max(nums) > 0:
            log.add(tag, f"Search space: '{k}' at upper bound", "optimum may be larger",
                    best["case"][k], "", status="LOW", note="widen the list in Parameters > Optimisation")


def table_of(results, mode, top=25):
    cols = ["#", "system", "NPC EUR", "CAPEX EUR", "LCOE EUR/kWh", "ren. %", "import MWh",
            "export MWh", "unmet %", "CO2 t/yr", "feasible"]
    if mode == "village":
        cols.insert(8, "subscr. kW")
    rows = []
    for k, r in enumerate(results[:top]):
        row = [k + 1, r["label"], round(r["NPC"]), round(r["CAPEX"]), round(r["LCOE"], 4),
               round(r["REN"], 1), round(r["imp"] / 1000, 1), round(r["exp"] / 1000, 1),
               round(r["unmet_pct"], 2), round(r["co2"], 1), "yes" if r["feasible"] else "no: " + r["why"]]
        if mode == "village":
            row.insert(8, r["P_sub"])
        rows.append(row)
    return cols, rows


# ------------------------------------------------------------- top level
def resources(p, prof, log, tag):
    pv = pv_per_kwp(p, prof)
    wind = wind_per_turbine(p, prof)
    log.head(tag, "Renewable resources")
    log.add(tag, "PV yield", "P = derate x G x (1 + a (Tc - 25)),  Tc = Ta + (NOCT-20)/0.8 x G",
            float(pv.sum()), "kWh/kWp/yr", note="GHI from village meteo file (open-meteo)")
    log.add(tag, "Wind turbine yield", "v_hub = v10 (h/10)^alpha, cubic power curve",
            float(wind.sum()), "kWh/turbine/yr",
            note=f"mean wind at 10 m {prof.wind10.mean():.2f} m/s (weak site)")
    bio = bio_daily_kwh(p, prof)
    log.add(tag, "Biogas electricity available", "E = t/day x yield x LHV x eta_el",
            float(bio.mean()), "kWh/day", note="cows 150 + pigs 50 + food waste (Thinh biomass file)")
    return pv, wind, bio


def log_hydro(h, log, tag):
    log.add(tag, f"{h['name']}: head loss at design flow",
            "hf = f L/D v^2/(2g), f Swamee-Jain", h["hf"], "m",
            note=f"Qd = {h['Qd'] * 1000:.1f} L/s, v = {h['v']:.2f} m/s, D = {h['D']} m, L = {h['L']:.0f} m")
    log.add(tag, f"{h['name']}: rated power", "P = eta rho g Qd (H - hf)", h["Pr"], "kW",
            note=f"H = {h['H']} m, eta = {h['eta']:.2f}")
    log.add(tag, f"{h['name']}: annual energy", "monthly flow x (1 - reserved), limited to Qd",
            h["E"], "kWh/yr", note=f"capacity factor {h['E'] / 8760 / max(h['Pr'], 1e-9) * 100:.0f} %")
    log.add(tag, f"{h['name']}: capital cost", "C = c_kW x P + c_pipe x L x D", h["capex"], "EUR")


def run_village_energy(p, S, prof, log, progress=None):
    tag = "energy-village"
    load = prof.vil_P + prof.ski_P
    pv, wind, bio = resources(p, prof, log, tag)
    hy = hydro_site(p, "village")
    log.head(tag, "River hydro plant (village site)")
    log_hydro(hy, log, tag)
    res = dict(pv=pv, wind=wind, bio_day=bio, hydro={"village": hy})
    space = dict(pv=p.list("opt.vil_pv") if S["vil_res"] else [0.0],
                 hydro=[None, "village"] if (S["vil_res"] and S["vil_hydro"]) else [None],
                 bat=p.list("opt.vil_bat") if S["vil_res"] else [0.0],
                 bio=p.list("opt.vil_bio") if (S["vil_res"] and S["vil_bio"]) else [0.0])
    cons = dict(net_zero=S["net_zero"], min_ren=float(S.get("min_ren", 0) or 0))
    results = optimise("Village", load, res, p, prof, "village", space, cons, progress)
    base = evaluate(dict(pv=0, hydro=None, bat=0, bio=0), load, res, p, prof, "village")
    best = results[0]
    log.head(tag, "Village + ski system optimisation (grid-connected)")
    log.add(tag, "Search space", "all combinations", len(results), "systems",
            note=", ".join(f"{k}: {v}" for k, v in space.items()))
    log.add(tag, "Objective", "min NPC = sum (CAPEX + O&M x PWF + replacements - salvage) + grid bill x PWF",
            None, note="constraints: " + (", ".join(k for k, v in cons.items() if v) or "none"))
    log.add(tag, "Grid only (reference)", "NPC of grid bill", base["NPC"], "EUR",
            note=f"subscription {base['P_sub']:.0f} kW, option {base['tariff']['option']}")
    bound_warn(best, space, log, tag)
    log.add(tag, "Best system", best["label"], best["NPC"], "EUR",
            status="OK" if best["feasible"] else "FAIL",
            note=f"LCOE {best['LCOE']:.4f} EUR/kWh, ren. {best['REN']:.1f} %")
    t = best["tariff"]
    log.head(tag, "EDF supply contract (subscription choice)")
    log.add(tag, "Rule", "for each option: min over P_sub of fixed x P_sub + energy + overrun x kWh above P_sub",
            None, note="kWh above subscription are very expensive -> P_sub close to peak import")
    for o in best["tariff_all"]:
        log.add(tag, f"Option {o['option']}", f"P_sub {o['P_sub']:.0f} kW | fixed {o['fixed']:,.0f} | "
                f"energy {o['energy']:,.0f} | overrun {o['overrun']:,.0f} ({o['hours_over']} h)",
                o["total"], "EUR/yr", status="chosen" if o is t else "")
    return dict(load=load, results=results, best=best, base=base, res=res, hydro=hy,
                table=table_of(results, "village"),
                tariff_table=(["option", "P_sub kW", "fixed EUR", "energy EUR", "overrun EUR",
                               "hours over", "total EUR/yr"],
                              [[o["option"], o["P_sub"], round(o["fixed"]), round(o["energy"]),
                                round(o["overrun"]), o["hours_over"], round(o["total"])]
                               for o in best["tariff_all"]]))


def run_eco_energy(p, S, prof, log, conn=None, progress=None):
    tag = "energy-eco"
    load = prof.eco_P
    i, n = p["econ.i"] / 100, int(p["econ.n"])
    pv, wind, bio = resources(p, prof, log, tag)
    hA, hB = hydro_site(p, "A"), hydro_site(p, "B")
    log.head(tag, "Stream hydro (two mutually exclusive intakes)")
    log_hydro(hA, log, tag)
    log_hydro(hB, log, tag)
    res = dict(pv=pv, wind=wind, bio_day=bio, hydro={"A": hA, "B": hB})
    out = dict(load=load, res=res, hA=hA, hB=hB)
    modes = ["iso", "grid"] if S["eco_mode"] == "compare" else (["iso"] if S["eco_mode"] == "isolated" else ["grid"])
    if "grid" in modes and conn is None:
        modes.remove("grid")
    if "iso" in modes:
        space = dict(pv=p.list("opt.eco_pv"), hydro=[None, "A", "B"], wind=p.list("opt.eco_wind"),
                     bat=p.list("opt.eco_bat"), bio=p.list("opt.eco_bio"))
        r = optimise("Eco isolated", load, res, p, prof, "iso", space,
                     dict(max_unmet=p["opt.max_unmet"]), progress)
        out["iso"] = dict(results=r, best=r[0], table=table_of(r, "iso"))
        log.head(tag, "Eco-district isolated (stand-alone microgrid)")
        log.add(tag, "Search space", "all combinations", len(r), "systems",
                note=", ".join(f"{k}: {v}" for k, v in space.items()))
        log.add(tag, "Constraint", "unmet load <= max", p["opt.max_unmet"], "%")
        b = r[0]
        bound_warn(b, space, log, tag)
        log.add(tag, "Best isolated system", b["label"], b["NPC"], "EUR",
                status="OK" if b["feasible"] else "FAIL",
                note=f"LCOE {b['LCOE']:.3f} EUR/kWh, unmet {b['unmet_pct']:.2f} %, curtailed "
                     f"{b['curt'] / 1000:.0f} MWh")
    if "grid" in modes:
        fixed = conn["fixed_capex"]
        extra = {"Connection (substation + T3)": npc_component(fixed, p["cost.net_om"] / 100 * fixed, 40, i, n)}
        space = dict(pv=p.list("opt.eco_pv"), hydro=[None, "A", "B"], bat=[0.0])
        r = optimise("Eco grid", load, res, p, prof, "grid_simple", space, {}, progress, extra)
        L = p["geo.L2_len"]
        line_km = conn["line_capex_km"] + conn["line_om_km"] * pwf(i, n)
        line_npc = line_km * L + conn["loss_cost"] * pwf(i, n)
        for x in r:
            x["NPC_line"] = x["NPC"] + line_npc
            x["NPC"] = x["NPC_line"]
            x["LCOE"] = x["NPC"] * crf(i, n) / max(x["E_load"] + x["exp"], 1)
        r.sort(key=lambda x: x["NPC"])
        b = r[0]
        out["grid"] = dict(results=r, best=b, table=table_of(r, "grid"), line_npc=line_npc, line_km=line_km)
        log.head(tag, "Eco-district connected to the village by L2")
        log.add(tag, "Line cost per km (NPC)", "c_km = CAPEX/km + O&M/km x PWF", line_km, "EUR/km",
                note=f"L2 = {conn['line']['name']}, {L} km")
        log.add(tag, "Best grid-connected system", b["label"], b["NPC"], "EUR",
                note=f"retail {p['econ.retail']} EUR/kWh, export {p['econ.sell']} EUR/kWh")
    if "iso" in out and "grid" in out:
        iso, gr = out["iso"]["best"]["NPC"], out["grid"]["best"]
        npc_wo_line = gr["NPC"] - out["grid"]["line_npc"]
        lk = out["grid"]["line_km"]
        D = (iso - npc_wo_line) / lk if lk > 0 else float("nan")
        out["breakeven_km"] = D
        # HOMER grid-extension parameters (team)
        lk_h = p["econ.ext_eur_km"] + p["econ.ext_om_km"] * pwf(i, n)
        npc_grid_energy = load.sum() * p["econ.retail"] * pwf(i, n)
        D_h = (iso - npc_grid_energy) / lk_h
        out["breakeven_km_homer"] = D_h
        log.head(tag, "Break-even distance: stand-alone vs grid extension")
        log.add(tag, "With designed L2 line", "D = (NPC_iso - NPC_grid without line) / NPC_line per km",
                D, "km", note=f"({iso:,.0f} - {npc_wo_line:,.0f}) / {lk:,.0f}")
        log.add(tag, "With HOMER grid-extension cost", "D = (NPC_iso - E x price x PWF) / (C_cap + C_om x PWF)",
                D_h, "km", note=f"{p['econ.ext_eur_km']:,.0f} EUR/km, {p['econ.ext_om_km']:,.0f} EUR/yr/km")
        log.add(tag, "Decision", f"actual distance {p['geo.L2_len']} km",
                "grid connection" if p["geo.L2_len"] < D else "stand-alone",
                note="the cheaper option for the real distance")
        out["decision"] = "grid" if p["geo.L2_len"] < D else "iso"
    return out
