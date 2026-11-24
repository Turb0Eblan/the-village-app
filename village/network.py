"""Electrical network study: transformers, lines, voltage drop, short-circuit
currents, breakers, harmonics of the renovated lift and network costs.

Method follows the team's spreadsheet (Tuan_Hung Deliverable.xlsx) and the
course: impedances are added in series from the source, Isc = c Un / (sqrt3 Z),
dU% = (P R + Q X) / U^2 x 100.
"""
import math
import numpy as np
from .calc import fmt, ok, pwf, std_up

SQ3 = math.sqrt(3)


# ------------------------------------------------------------------ helpers
def isc_kA(c, U_kV, R, X):
    return c * U_kV * 1e3 / (SQ3 * math.hypot(R, X)) / 1e3


def tr_RX(row, U_kV):
    """Transformer R, X referred to the LV side (ohm)."""
    Sn = row["Sn_kVA"] * 1e3
    U = U_kV * 1e3
    Z = row["uk_pct"] / 100 * U ** 2 / Sn
    R = row["Pk_W"] * U ** 2 / Sn ** 2
    X = math.sqrt(max(Z ** 2 - R ** 2, 0))
    return R, X, Z


def tr_losses_kwh(row, S_kva):
    S = np.asarray(S_kva)
    return row["P0_W"] * 8760 / 1000 + row["Pk_W"] / 1000 * float(np.sum((S / row["Sn_kVA"]) ** 2))


def peak(P, Q):
    S = np.hypot(P, Q)
    k = int(np.argmax(S))
    return k, float(S[k]), float(P[k]), float(Q[k])


def pick_breaker(I_A, Isc, rows, margin):
    need = I_A * margin
    for r in sorted(rows, key=lambda r: (r["In_A"], r["Icu_kA"])):
        if r["In_A"] >= need and r["Icu_kA"] >= Isc:
            return r, need
    return None, need


# ------------------------------------------------------------- line choice
def eval_line(c, L_km, P, Q, U_kV, dU_up, Isc_start, p, i, n):
    R = c["R_ohm_km"] * L_km
    X = c["X_ohm_km"] * L_km
    k, S_pk, P_pk, Q_pk = peak(P, Q)
    U = U_kV * 1e3
    I_pk = S_pk * 1e3 / (SQ3 * U)
    I_des = I_pk * p["geo.line_margin"]
    dU = (P_pk * 1e3 * R + Q_pk * 1e3 * X) / U ** 2 * 100
    kf = p["geo.k_cable"] if c["type"] == "UG" else p["geo.k_ohl"]
    S_th = Isc_start * 1e3 * math.sqrt(p["geo.t_fault"]) / kf
    loss = float(np.sum((np.hypot(P, Q) * 1e3) ** 2 / U ** 2 * R)) / 1000  # kWh
    if c["type"] == "OHL":
        capex = p["cost.ohl_eur_km"] * L_km + c["eur_m"] * L_km * 1000
        cform = f"{p['cost.ohl_eur_km']:.0f} EUR/km x {L_km} km + {c['eur_m']} EUR/m metal"
    else:
        capex = (c["eur_m"] + p["cost.cable_lay"]) * L_km * 1000
        cform = f"({c['eur_m']} + {p['cost.cable_lay']:.0f}) EUR/m x {L_km * 1000:.0f} m"
    om = p["cost.net_om"] / 100 * capex
    annual = loss * p["cost.loss_price"] + om
    cap = capex + annual * pwf(i, n)
    feas = (I_des <= c["Imax_A"]) and (dU_up + dU <= p["geo.dU_mv_max"]) and (c["S_mm2"] >= S_th)
    return dict(name=c["name"], type=c["type"], S=c["S_mm2"], R=R, X=X, I_des=I_des,
                Imax=c["Imax_A"], dU=dU, dU_cum=dU_up + dU, S_th=S_th, loss=loss,
                capex=capex, cform=cform, om=om, cap=cap, feasible=feas,
                ok_I=I_des <= c["Imax_A"], ok_dU=dU_up + dU <= p["geo.dU_mv_max"],
                ok_th=c["S_mm2"] >= S_th, peak_hour=k, S_pk=S_pk)


def choose_line(tag, name, L_km, P, Q, ltype, dU_up, Isc_start, p, log, i, n):
    cands = [c for c in p.table("conductors") if ltype == "auto" or c["type"] == ltype]
    res = [eval_line(c, L_km, P, Q, p["grid.U_mv"], dU_up, Isc_start, p, i, n) for c in cands]
    feas = [r for r in res if r["feasible"]]
    best = min(feas, key=lambda r: r["cap"]) if feas else max(res, key=lambda r: r["S"])
    log.head(tag, f"{name}: conductor selection ({L_km} km, type: {ltype})")
    r0 = res[0]
    log.add(tag, "Design current", "I = S_peak / (sqrt3 x U) x margin",
            r0["I_des"], "A", note=f"S_peak = {r0['S_pk']:.1f} kVA")
    log.add(tag, "Short-circuit thermal minimum section",
            "S_min = Isc x sqrt(t) / k", None, "",
            note=f"Isc at start = {Isc_start:.2f} kA, t = {p['geo.t_fault']} s")
    log.add(tag, "Voltage drop", "dU% = (P R + Q X) / U^2 x 100, cumulative with upstream "
            f"{dU_up:.2f} %", None)
    log.add(tag, "Capitalised cost", "C = CAPEX + (E_loss x price + O&M) x PWF(i, n)", None,
            note=f"PWF = {pwf(i, n):.3f}")
    for r in res:
        st = "chosen" if r is best else ("OK" if r["feasible"] else
                                         "FAIL " + ",".join(x for x, f in (("I", r["ok_I"]), ("dU", r["ok_dU"]),
                                                                           ("Isc", r["ok_th"])) if not f))
        log.add(tag, f"  {r['name']} ({r['type']})",
                f"I {r['I_des']:.1f}/{r['Imax']} A | dU {r['dU_cum']:.2f} % | S {r['S']}>={r['S_th']:.1f} mm2"
                f" | loss {r['loss']:.0f} kWh/yr | CAPEX {r['capex']:,.0f}",
                r["cap"], "EUR", status=st)
    table = (["conductor", "type", "I design A", "Imax A", "dU cum %", "S min mm2", "loss kWh/yr",
              "CAPEX EUR", "capitalised EUR", "status"],
             [[r["name"], r["type"], round(r["I_des"], 1), r["Imax"], round(r["dU_cum"], 3),
               round(r["S_th"], 1), round(r["loss"]), round(r["capex"]), round(r["cap"]),
               "chosen" if r is best else ("ok" if r["feasible"] else "fail")] for r in res])
    return best, table


# --------------------------------------------------------- transformers
def choose_tr(tag, name, P, Q, p, log, i, n, count=1, S_min=0.0):
    k, S_pk, P_pk, Q_pk = peak(P, Q)
    if S_min > S_pk:
        log.add(tag, f"{name}: sizing power from contracts", "S = sum(contracts) x ks + EV",
                S_min, "kVA", note=f"measured share only {S_pk:.1f} kVA")
        S_pk = S_min
    S_unit = S_pk / count
    need = S_unit / (p["geo.tr_max_load"] / 100)
    rows = sorted(p.table("transformers"), key=lambda r: r["Sn_kVA"])
    row = next((r for r in rows if r["Sn_kVA"] >= need - 1e-9), rows[-1])
    loss = tr_losses_kwh(row, np.hypot(P, Q) / count) * count
    capex = p["cost.tr_eur_mva"] * row["Sn_kVA"] / 1000 * count
    log.add(tag, f"{name}: required rating",
            f"Sn >= S_peak / n / loading = {S_pk:.1f} / {count} / {p['geo.tr_max_load'] / 100:.2f}",
            need, "kVA")
    log.add(tag, f"{name}: chosen", "smallest standard Sn >= required (Minera catalogue)",
            f"{count} x {row.get('model', '')} ({row['Sn_kVA']} kVA)", "",
            status=ok(row["Sn_kVA"] >= need),
            note=f"uk {row['uk_pct']} %, P0 {row['P0_W']} W, Pk {row['Pk_W']} W, loading {S_unit / row['Sn_kVA'] * 100:.0f} %")
    log.add(tag, f"{name}: annual losses", "E = n (P0 x 8760 + Pk x sum (S/Sn)^2)", loss, "kWh/yr")
    return dict(row=row, count=count, need=need, S_pk=S_pk, P_pk=P_pk, Q_pk=Q_pk, k=k,
                loss=loss, capex=capex, loading=S_unit / row["Sn_kVA"])


# ------------------------------------------------------------- harmonics
V_LIM = {5: 6.0, 7: 5.0, 11: 3.5, 13: 3.0}     # IEC 61000-2-2 / EN 50160 compatibility levels
HS = (5, 7, 11, 13)


def harmonics(p, P_bus, Q_bus, R_up, X_up, tr_row, log, tag="ski"):
    """Lift 2 drive harmonics, method of lecture DG7 (3 steps):
    1) series inductance (line choke) of the drive by equivalence with the
       manufacturer test case, 2) oversize the transformer (higher S_sc and
       R_sce), 3) one parallel tuned filter per non-compliant harmonic."""
    U = p["grid.U_lv"] * 1e3
    V_ph = U / SQ3
    f = p["grid.f"]
    w1 = 2 * math.pi * f
    P_mech = p["ski.lift2_new_kw"]
    motors = sorted(p.table("motors"), key=lambda r: r["P_kW"])
    motor = next((m for m in motors if m["P_kW"] >= P_mech), motors[-1])
    drives = sorted(p.table("atv66"), key=lambda r: r["P_kW"])
    drive = next((d for d in drives if d["P_kW"] >= motor["P_kW"]), drives[-1])
    choke = bool(p["ski.choke"])
    P_el = P_mech / (motor["eta_pct"] / 100)
    I1 = P_el * 1e3 / (SQ3 * U * p["ski.pf_vfd"])
    spec = {h: drive[f"H{h}{'c' if choke else 'n'}"] for h in HS}
    I_line = drive["Iline_choke"] if choke else drive["Iline_nochoke"]
    Sapp = SQ3 * U * I_line / 1e3
    lim_rows = sorted(p.table("harm_limits"), key=lambda r: r["Rsce_min"])

    def limits(Rsce):
        lim = lim_rows[0]
        for r in lim_rows:
            if Rsce >= r["Rsce_min"]:
                lim = r
        return lim

    def net_of(row):
        Rt, Xt, _ = tr_RX(row, p["grid.U_lv"])
        return R_up + Rt, X_up + Xt

    def assess(R_net, X_net):
        Ssc = U ** 2 / math.hypot(R_net, X_net) / 1e6          # MVA
        Rsce = Ssc * 1e3 / Sapp
        lim = limits(Rsce)
        Vh = {h: spec[h] / 100 * I1 * h * X_net / V_ph * 100 for h in HS}
        thd_i = math.sqrt(sum(spec[h] ** 2 for h in HS))
        thd_v = math.sqrt(sum(v ** 2 for v in Vh.values()))
        bad = [h for h in HS if spec[h] > lim[f"I{h}"] or Vh[h] > V_LIM[h]]
        good = not bad and thd_i <= lim["THD"] and thd_v <= 8.0
        return dict(Ssc=Ssc, Rsce=Rsce, lim=lim, Vh=Vh, thd_i=thd_i, thd_v=thd_v, bad=bad, good=good)

    R0, X0 = net_of(tr_row)
    log.head(tag, "Lift 2 renovation: motor and drive")
    log.add(tag, "Motor", f"smallest LS motor >= {P_mech:.0f} kW mechanical",
            f"{motor.get('model', 'LS')} {motor['P_kW']} kW, eta {motor['eta_pct']} %",
            note=f"original {p['ski.motor_kw']:.0f} kW motor is too small for {P_mech:.0f} kW")
    log.add(tag, "Drive", "smallest ATV66 (constant torque, 400 V) >= motor",
            f"ATV66{drive['model']} ({drive['P_kW']} kW)",
            note="constant-torque drive: a ski lift lifts a load like an elevator")
    log.add(tag, "Electrical input", "P_el = P_mech / eta", P_el, "kW")
    log.add(tag, "Fundamental current", "I1 = P_el / (sqrt3 U cos phi)", I1, "A")
    log.add(tag, "Drive apparent power", "S_app = sqrt3 x U x I_line(catalogue)", Sapp, "kVA")
    # voltage drop at the coupling point: exact vs approximate (lecture)
    phi = math.acos(p["ski.pf_vfd"])
    Iph = complex(I1 * math.cos(phi), -I1 * math.sin(phi))
    E = V_ph + complex(R0, X0) * Iph
    dV_ex = (abs(E) - V_ph) / abs(E) * 100
    dV_ap = (R0 * math.cos(phi) + X0 * math.sin(phi)) * I1 / V_ph * 100
    log.add(tag, "Voltage drop of the drive current (approximate)", "dV = I (R cos phi + X sin phi) / V",
            dV_ap, "%", note=f"exact |E| - |V| = {dV_ex:.3f} %: equal because the angle between E and V is small")

    # ---------------- step 1: series inductance (line choke)
    log.head(tag, "Harmonics step 1 - series inductance of the drive (line choke)")
    U_lab, Isc_lab = p["ski.lab_U"], p["ski.lab_Isc"]
    X_lab = U_lab / (SQ3 * Isc_lab * 1e3)
    L_mfr = drive["L_mH"] if choke else 0.0
    X_mfr = w1 * L_mfr / 1e3
    log.add(tag, "Manufacturer test network", "X_lab = U_lab / (sqrt3 Isc_lab)", X_lab * 1e3, "mohm",
            note=f"ATV66 table conditions: {U_lab:.0f} V, Isc {Isc_lab:.0f} kA")
    log.add(tag, "Manufacturer choke", "X_ch,mfr = omega L_mfr", X_mfr * 1e3, "mohm",
            note=f"L_mfr = {L_mfr} mH (ATV66 table)")
    log.add(tag, "Our network at the coupling point (ski LV bus)",
            "X_net = X_up (U_lv/U_mv)^2 + X_T", X0 * 1e3, "mohm", note=f"R_net = {R0 * 1e3:.2f} mohm")
    X_ch = max(0.0, X_lab + X_mfr - X0)
    L_ch = X_ch / w1 * 1e3
    log.add(tag, "Our choke (same total impedance -> same harmonics as the table)",
            "X_ch = X_lab + X_ch,mfr - X_net", X_ch * 1e3, "mohm",
            note=f"L_ch = X_ch / omega = {L_ch:.3f} mH" +
                 ("  (network already stiffer than the test: no choke needed)" if X_ch == 0 else ""))
    a = assess(R0, X0)
    log.add(tag, "Short-circuit power at the coupling point", "S_sc = U^2 / |Z_net|", a["Ssc"] * 1e3, "kVA")
    log.add(tag, "Short-circuit ratio", "R_sce = S_sc / S_app", a["Rsce"], "",
            note=f"IEC 61000-3-12 limits row R_sce >= {a['lim']['Rsce_min']}")
    for h in HS:
        log.add(tag, f"h{h}: current / voltage harmonic",
                f"I{h}/I1 = {spec[h]} % (limit {a['lim'][f'I{h}']} %), V_h = h X_net I_h / V",
                f"{a['Vh'][h]:.2f} % (limit {V_LIM[h]} %)", "",
                status="ok" if h not in a["bad"] else "> limit")
    log.add(tag, "THDi (fundamental reference)", "THD_i = sqrt(sum I_h^2) / I_1", a["thd_i"], "%",
            status="ok" if a["thd_i"] <= a["lim"]["THD"] else "> limit",
            note=f"limit {a['lim']['THD']} %; dividing by I_rms instead of I_1 would be wrong")
    log.add(tag, "THDv at the coupling point", "THD_v = sqrt(sum V_h^2) / V_1", a["thd_v"], "%",
            status="ok" if a["thd_v"] <= 8 else "> limit", note="limit 8 %")
    log.add(tag, "Step 1 result", "all I_h, V_h, THD within limits?",
            "compliant -> stop" if a["good"] else f"not compliant (h = {a['bad'] or 'THD'}) -> step 2",
            status="OK" if a["good"] else "next step")
    steps = [["1 choke", tr_row.get("model", tr_row["Sn_kVA"]), f"{L_ch:.3f} mH", round(a["Rsce"], 1),
              round(a["thd_i"], 1), round(a["thd_v"], 2), "-", "pass" if a["good"] else "fail"]]

    # ---------------- step 2: oversize the transformer
    tr_new, use = None, (tr_row, R0, X0, a)
    if not a["good"]:
        log.head(tag, "Harmonics step 2 - oversize the transformer (higher S_sc)")
        fmax = p["ski.harm_tr_max"]
        cands = [r for r in sorted(p.table("transformers"), key=lambda r: r["Sn_kVA"])
                 if tr_row["Sn_kVA"] < r["Sn_kVA"] <= fmax * tr_row["Sn_kVA"]]
        log.add(tag, "Candidates", f"S_n <= {fmax:g} x {tr_row['Sn_kVA']} kVA (a bit bigger only: cost)",
                ", ".join(str(r["Sn_kVA"]) for r in cands) or "none", "kVA")
        for r in cands:
            Rn, Xn = net_of(r)
            b = assess(Rn, Xn)
            dc = p["cost.tr_eur_mva"] * (r["Sn_kVA"] - tr_row["Sn_kVA"]) / 1000
            steps.append(["2 oversize", r.get("model", r["Sn_kVA"]), "", round(b["Rsce"], 1),
                          round(b["thd_i"], 1), round(b["thd_v"], 2), round(dc), "pass" if b["good"] else "fail"])
            log.add(tag, f"{r.get('model', r['Sn_kVA'])}", "R_sce = S_sc / S_app -> new limit row",
                    f"R_sce {b['Rsce']:.0f}, I5 limit {b['lim']['I5']} %, THDv {b['thd_v']:.2f} %", "",
                    status="OK" if b["good"] else "> limit", note=f"extra cost {dc:,.0f} EUR")
            if b["good"]:
                tr_new, use = r, (r, Rn, Xn, b)
                break
        log.add(tag, "Step 2 result", "smallest oversized transformer that is compliant",
                tr_new.get("model", tr_new["Sn_kVA"]) if tr_new else "none compliant -> keep "
                + str(tr_row.get("model", tr_row["Sn_kVA"])) + ", go to step 3",
                status="chosen" if tr_new else "next step")
    row, R_net, X_net, a = use
    lim = a["lim"]

    # power-factor correction need at the bus feeding the lift (fixes the filter capacitors)
    k = int(np.argmax(np.hypot(P_bus, Q_bus)))
    Pp, Qp = float(P_bus[k]), float(Q_bus[k])
    pf0 = Pp / math.hypot(Pp, Qp)
    tg2 = math.tan(math.acos(p["ski.pf_target"]))
    Q_need = max(0.0, Qp - Pp * tg2)

    out = dict(motor=motor, drive=drive, choke=choke, L_choke=L_ch, X_lab=X_lab, P_el=P_el, I1=I1,
               Sapp=Sapp, Ssc=a["Ssc"], Rsce=a["Rsce"], lim=lim, spec=spec, thd_i=a["thd_i"],
               Q_need=Q_need, pf0=pf0, R_net=R_net, X_net=X_net, branches=[], tr_new=tr_new,
               filter_needed=not a["good"], dV=dV_ap)
    detune = p["ski.filt_detune"]
    qf = p["ski.filt_q"]
    tuned = a["bad"] or ([5] if not a["good"] else [])

    sev = {h: max(spec[h] - lim[f"I{h}"], 0.0) + 0.1 for h in tuned}

    def design(Q_tot, split="equal"):
        br = []
        for h in tuned:
            Qh = Q_tot / len(tuned) if split == "equal" else Q_tot * sev[h] / sum(sev.values())
            ht = h * detune
            C = Qh * 1e3 * (1 - 1 / ht ** 2) / (w1 * U ** 2)
            L = 1 / (C * (ht * w1) ** 2)
            R = ht * w1 * L / qf
            br.append(dict(h=h, ht=ht, Q=Qh, C=C, L=L, R=R))
        return br

    def Zf(h, br):
        if not br:
            return None
        y = 0
        for b in br:
            y += 1 / complex(b["R"], h * w1 * b["L"] - 1 / (h * w1 * b["C"]))
        return 1 / y

    def Zn(h):
        return complex(R_net, h * X_net)

    def check(br):
        rows, tv0, tv1, ti1 = [], 0.0, 0.0, 0.0
        for h in HS:
            Ih = spec[h] / 100 * I1
            zf = Zf(h, br)
            Ig = Ih if zf is None else Ih * abs(zf / (zf + Zn(h)))
            V0 = Ih * abs(Zn(h)) / V_ph * 100
            V1 = Ig * abs(Zn(h)) / V_ph * 100
            tv0, tv1, ti1 = tv0 + V0 ** 2, tv1 + V1 ** 2, ti1 + (Ig / I1 * 100) ** 2
            rows.append([h, spec[h], round(Ig / I1 * 100, 2), lim[f"I{h}"], round(V0, 3), round(V1, 3),
                         V_LIM[h], "OK" if (Ig / I1 * 100 <= lim[f"I{h}"] and V1 <= V_LIM[h]) else "FAIL"])
        tv0, tv1, ti1 = math.sqrt(tv0), math.sqrt(tv1), math.sqrt(ti1)
        good = all(r[-1] == "OK" for r in rows) and tv1 <= 8.0 and ti1 <= lim["THD"]
        return rows, tv0, tv1, ti1, good

    Q_tot, br = 0.0, []
    rows, tv0, tv1, ti1, good = check([])
    it_rows = [[0, "-", round(ti1, 2), round(tv1, 2), "pass" if good else "fail"]]
    if not good:
        log.head(tag, "Harmonics step 3 - parallel tuned filters (one per non-compliant harmonic)")
        log.add(tag, "Filters needed", "one series R-L-C branch per harmonic over the limit",
                ", ".join(f"h{h}" for h in tuned), "")
        log.add(tag, "Reactive power to compensate (fixes C)", f"Q_c = P (tan phi_1 - tan phi_2), PF {pf0:.2f} -> {p['ski.pf_target']}",
                Q_need, "kvar", note=f"P = {Pp:.1f} kW, Q = {Qp:.1f} kvar at peak; Q shared equally: Q_c / n filters")
        Q0 = max(5.0 * math.ceil(max(Q_need, 10.0) / 5.0), 10.0)
        Qmax = max(Q0, 5.0 * math.ceil(1.5 * Sapp / 5.0))
        for split in ("equal", "severity"):
            Q = Q0
            while True:
                br = design(Q, split)
                rows, tv0, tv1, ti1, good = check(br)
                it_rows.append([Q, split + ": " + "+".join(f"{b['Q']:.0f}" for b in br), round(ti1, 2),
                                round(tv1, 2), "pass" if good else "fail"])
                if good or Q >= Qmax:
                    break
                Q += 5.0
            if good:
                break
        Q_tot = Q
        out["split"] = split
        log.add(tag, "Sharing of Q between the filters",
                "equal: Q_h = Q / n;  else Q_h = Q (I_h - I_lim,h) / sum (I_h - I_lim,h)", split,
                note="equal split (lecture) tried first, up to 1.5 x S_app; " +
                     ("it passes" if split == "equal" else "it cannot pass because h5 dominates, so Q goes "
                      "where the excess current is"))
        log.add(tag, "Total filter reactive power (first passing size)",
                "start at Q_c, + 5 kvar until all limits pass", Q_tot, "kvar", status=ok(good),
                note="see table 'Filter sizing iterations'")
        for b in br:
            log.add(tag, f"Filter h{b['h']}: capacitor", "C = Q (1 - 1/h_t^2) / (omega U^2)", b["C"] * 1e6, "uF",
                    note=f"Q = {b['Q']:.1f} kvar, star connection")
            log.add(tag, f"Filter h{b['h']}: inductance (resonance)", "L = 1 / (C (h_t omega)^2)", b["L"] * 1e3, "mH",
                    note=f"tuned at h_t = {b['ht']:.2f} ({b['ht'] * f:.0f} Hz): L omega_h = 1/(C omega_h)")
            log.add(tag, f"Filter h{b['h']}: resistance (quality factor)", "R = h_t omega L / q", b["R"] * 1e3, "mohm",
                    note=f"q = {qf:g}")
        log.add(tag, "Grid side current", "I_grid,h = I_h x Z_f / (Z_f + Z_net)", None,
                note="current divider: the 50 Hz source is a short circuit for harmonics")
    out["branches"], out["Q_filter"] = br, Q_tot
    steps.append(["3 filters", row.get("model", row["Sn_kVA"]),
                  f"{Q_tot:.0f} kvar: " + ", ".join(f"h{b['h']}" for b in br) if br else "not needed",
                  round(a["Rsce"], 1), round(ti1, 2), round(tv1, 2),
                  round(Q_tot * p["cost.filter_eur_kvar"]), "pass" if good else "fail"])
    out["steps_table"] = (["step", "transformer", "measure", "R_sce", "THDi to grid %", "THDv %",
                           "extra cost EUR", "result"], steps)
    out["filter_table"] = (["filter", "tuned h_t", "Q kvar", "C uF", "L mH", "R mohm", "q"],
                           [[f"h{b['h']}", round(b["ht"], 2), round(b["Q"], 1), round(b["C"] * 1e6, 1),
                             round(b["L"] * 1e3, 4), round(b["R"] * 1e3, 3), qf] for b in br])
    out["iter_table"] = (["Q_f kvar", "split: Q per branch", "THDi to grid %", "THDv %", "result"], it_rows)
    out.update(table=(["h", "Ih/I1 % drive", "Ih/I1 % to grid", "IEC limit %", "Vh % before",
                       "Vh % after", "EN50160 Vh %", "status"], rows),
               thd_v0=tv0, thd_v1=tv1, thd_i1=ti1)
    log.head(tag, "Harmonics: final result")
    log.add(tag, "THDi to grid", "sqrt(sum (I_grid,h/I1)^2)", ti1, "%",
            status=ok(ti1 <= lim["THD"]), note=f"limit {lim['THD']} %")
    log.add(tag, "THDv at PCC before / after", "Vh = I_grid,h |Z_net(h)|, Z_net(h) = R + j h X",
            f"{tv0:.2f} % / {tv1:.2f} %", "", status=ok(tv1 <= 8.0), note="EN 50160 limit 8 %")
    hh = np.arange(1.0, 25.0, 0.02)
    zs = []
    for h in hh:
        zn, zf = Zn(h), Zf(h, br)
        zs.append(abs(zn) if zf is None else abs(zn * zf / (zn + zf)))
    out["scan"] = (hh, np.array(zs), np.array([abs(Zn(h)) for h in hh]))
    pf1 = Pp / math.hypot(Pp, Qp - Q_tot) if Q_tot else pf0
    lead = Q_tot > Qp
    out["pf1"], out["leading"] = pf1, lead
    if Q_tot:
        log.add(tag, "PF after filter", "cos phi = P / sqrt(P^2 + (Q - Q_f)^2)",
                f"{pf1:.3f}{' (leading)' if lead else ''}", "",
                status=ok(pf1 >= p["ski.pf_target"] - 1e-3),
                note="filter over-compensates: consider detuned capacitor steps" if lead else "")
    out["ok"] = good
    return out


# ------------------------------------------------------------- main study
def run_network(p, S, prof, log, export_kw=None, dg=None):
    i = p["econ.i"] / 100
    n = int(p["econ.n"])
    U = p["grid.U_mv"]
    Ulv = p["grid.U_lv"]
    c_max, c_min = p["grid.c_max"], p["grid.c_min"]
    net = dict(elements={k: [] for k in ("source", "L0", "village", "L1", "ski", "L2", "eco")},
               tables={}, costs=[], checks=[], isc={})
    E = net["elements"]

    def elem(node, name, kind, rating, detail="", status=""):
        E[node].append(dict(name=name, kind=kind, rating=rating, detail=detail, status=status))

    def cost(node, item, formula, value, new=True):
        net["costs"].append(dict(node=node, item=item, formula=formula, value=value, new=new))

    eco_grid = S["eco"] and S["eco_mode"] in ("grid", "compare")
    T = "source"
    log.head(T, "Source substation 63/20 kV")
    Zs = (U * 1e3) ** 2 / (p["grid.Ssc"] * 1e6)
    rx = p["grid.RX_src"]
    Rs, Xs = Zs * rx / math.sqrt(1 + rx ** 2), Zs / math.sqrt(1 + rx ** 2)
    log.add(T, "Source impedance", "Z_s = U^2 / S_sc", Zs, "ohm", note=f"R_s = {Rs:.4f}, X_s = {Xs:.4f} (R/X = {rx})")
    I0 = log.add(T, "Isc at Q0 (20 kV busbar)", "Isc = c U / (sqrt3 Z)", isc_kA(c_max, U, Rs, Xs), "kA")
    net["isc"]["Q0"] = I0
    elem("source", "HV/MV transformer T0", "transformer", "63/20 kV", f"S_sc = {p['grid.Ssc']:.0f} MVA")

    # ---------------- L0 (existing)
    P0 = prof.vil_P + prof.ski_P + (prof.eco_P if eco_grid else 0)
    Q0 = prof.vil_Q + prof.ski_Q + (prof.eco_Q if eco_grid else 0)
    cond = next((c for c in p.table("conductors") if c["name"] == p["geo.L0_cond"]),
                p.table("conductors")[5])
    L0 = eval_line(cond, p["geo.L0_len"], P0, Q0, U, 0.0, I0, p, i, n)
    T = "L0"
    log.head(T, f"L0 source -> village ({p['geo.L0_len']} km, existing {cond['name']})")
    log.add(T, "Peak power carried", "max sqrt(P^2+Q^2) over 8760 h", L0["S_pk"], "kVA")
    log.add(T, "Line impedance", "R = r L, X = x L", f"R {L0['R']:.3f} ohm, X {L0['X']:.3f} ohm")
    log.add(T, "Design current vs ampacity", "I = S/(sqrt3 U) x margin", L0["I_des"], "A",
            status=ok(L0["ok_I"]), note=f"Imax {cond['Imax_A']} A")
    log.add(T, "Voltage drop at peak", "dU% = (P R + Q X)/U^2 x 100", L0["dU"], "%",
            status=ok(L0["ok_dU"]))
    log.add(T, "Annual Joule losses", "E = sum 3 I^2 R", L0["loss"], "kWh/yr")
    elem("L0", cond["name"], "overhead line", f"{p['geo.L0_len']} km, {cond['S_mm2']} mm2",
         f"I {L0['I_des']:.0f}/{cond['Imax_A']} A, dU {L0['dU']:.2f} %", ok(L0["feasible"]))
    if export_kw is not None:
        Pn = P0 - export_kw
        k = int(np.argmin(Pn))
        if Pn[k] < 0:
            rise = -(Pn[k] * 1e3 * L0["R"] + Q0[k] * 1e3 * L0["X"]) / (U * 1e3) ** 2 * 100
            I_exp = math.hypot(Pn[k], Q0[k]) / (SQ3 * U)
            log.add(T, "Voltage rise at max export (DG)", "dU = -(P_net R + Q X)/U^2, P_net < 0",
                    rise, "%", status=ok(rise <= p["geo.dU_mv_max"]),
                    note=f"export {-Pn[k]:.0f} kW, I = {I_exp:.0f} A")
            net["rise"] = rise
    R1, X1 = Rs + L0["R"], Xs + L0["X"]
    I1 = log.add(T, "Isc at Q1 (village MV bus)", "Z = Z_s + Z_L0", isc_kA(c_max, U, R1, X1), "kA")
    net["isc"]["Q1"] = I1
    net["L0"] = L0

    # ---------------- village substation(s)
    T = "village"
    log.head(T, "Village MV/LV substation")
    sub_v, sub_s, sub_e = prof.subscribed(p)
    log.add(T, "Subscribed power (cross-check)", "sum of contracts", sub_v, "kVA",
            note=f"x ks {p['vil.ks']} = {sub_v * p['vil.ks']:.0f} kVA; measured peak used for sizing")
    nv = max(1, int(p["geo.n_vil_tr"]))
    trv = choose_tr(T, "T1 village", prof.vil_P, prof.vil_Q, p, log, i, n, count=nv)
    RT, XT, _ = tr_RX(trv["row"], Ulv)
    r2 = (Ulv / U) ** 2
    I2 = log.add(T, "Isc at Q2 (village LV bus)", "Z = (Z_s + Z_L0)(U_lv/U_mv)^2 + Z_T1",
                 isc_kA(c_max, Ulv, R1 * r2 + RT, X1 * r2 + XT), "kA")
    net["isc"]["Q2"] = I2
    kv = trv["k"]
    dUT = (prof.vil_P[kv] * 1e3 * RT / nv + prof.vil_Q[kv] * 1e3 * XT / nv) / (Ulv * 1e3) ** 2 * 100
    dU_v = L0["dU"] + dUT
    log.add(T, "Voltage drop T1 at village peak", "dU% = (P R_T + Q X_T)/U_lv^2", dUT, "%")
    log.add(T, "Total drop source -> village LV bus", "dU_L0 + dU_T1", dU_v, "%",
            status=ok(dU_v <= p["geo.dU_tot_max"]), note="LV feeders not included")
    elem("village", f"T1 x{nv}", "transformer 20/0.4 kV", f"{nv} x {trv['row'].get('model', trv['row']['Sn_kVA'])}",
         f"loading {trv['loading'] * 100:.0f} %, uk {trv['row']['uk_pct']} %", "OK")
    elem("village", "Residential / commercial", "load", f"{sub_v:.0f} kVA subscribed",
         f"{p['vil.n6']}x6 + {p['vil.n9']}x9 + {p['vil.n12']}x12 kVA, municipal 36, sawmill 36")
    if S["ev_village"]:
        elem("village", "EV chargers", "load (non-linear)",
             f"{p['vil.ev_fast']:.0f} kW fast + {p['vil.ev_dual']:.0f} kW dual",
             f"peak {prof.vil_ev.max():.0f} kW in curve")
    net["trv"] = trv
    net["dU_village"] = dU_v
    fd = lv_feeder(p, log, Ulv, R1 * r2 + RT, X1 * r2 + XT, I2, dU_v)
    net["feeder"] = fd
    net["tables"]["LV feeder cable choice"] = fd["table"]
    c, b = fd["cable"], fd["breaker"]
    elem("village", "LV feeder F1 (cluster 2 road)", "LV cable", f"{c['name']}, {fd['L']:.0f} m",
         f"{fd['N']} houses, I {fd['I']:.0f} A, dU {c['dU']:.2f} %, Isc end {c['Ik1']:.2f} kA", ok(c["feasible"]))
    elem("village", "CB F1 feeder breaker", "circuit breaker",
         f"{b['model']}  {b['In_A']} A / {b['Icu_kA']} kA" if b else "none in catalogue",
         f"Ir {fd['Ir']:.0f} A, Isd <= {c['Isd_max']:.0f} A", "OK" if b else "FAIL")
    elem("village", "House connection", "service", f"branch breaker {fd['house_A']} A",
         f"{p['lvf.kva']:.0f} kVA, {fd['house_ph']}, 500 mA differential")
    cost("village", f"T1 {nv} x {trv['row']['Sn_kVA']} kVA", "20 kEUR/MVA x Sn", trv["capex"], new=False)
    cost("village", "Village MV substation", "20 k + 1 CB + units",
         p["cost.sub_base"] + p["cost.sub_cb"] * (1 + nv) + p["cost.sub_unit"] * (2 + nv + (1 if eco_grid else 0)),
         new=False)

    # ---------------- DG step-up transformers (village renewables at MV)
    if dg:
        log.head(T, "Connection of village renewables (MV/LV step-up)")
        rows = sorted(p.table("transformers"), key=lambda r: r["Sn_kVA"])
        big = rows[-1]["Sn_kVA"]
        for nm, kw in dg:
            if kw <= 0:
                continue
            S_need = kw / 0.95
            cnt = max(1, math.ceil(S_need / big))
            row = next(r for r in rows if r["Sn_kVA"] >= S_need / cnt - 1e-9)
            capex = p["cost.tr_eur_mva"] * row["Sn_kVA"] / 1000 * cnt + p["cost.sub_base"] + p["cost.sub_cb"] + p["cost.sub_unit"]
            log.add(T, f"{nm}: step-up transformer", "Sn >= P / 0.95 (split into units <= largest rating)",
                    f"{cnt} x {row['Sn_kVA']} kVA", "", note=f"P = {kw:.0f} kW")
            elem("village", f"{nm} step-up", "transformer 0.4/20 kV", f"{cnt} x {row.get('model', row['Sn_kVA'])}", f"{kw:.0f} kW plant")
            cost("village", f"{nm} connection ({cnt} x {row['Sn_kVA']} kVA + cell)", "TR + 20k + CB + unit", capex)

    # ---------------- L1 village -> ski
    T = "L1"
    L1, tabL1 = choose_line(T, "L1 village -> ski", p["geo.L1_len"], prof.ski_P, prof.ski_Q,
                            S["L1_type"], L0["dU"], I1, p, log, i, n)
    net["tables"]["L1 conductor choice"] = tabL1
    net["L1"] = L1
    elem("L1", L1["name"], "overhead line" if L1["type"] == "OHL" else "underground cable",
         f"{p['geo.L1_len']} km, {L1['S']} mm2",
         f"I {L1['I_des']:.1f}/{L1['Imax']} A, dU cum {L1['dU_cum']:.2f} %", ok(L1["feasible"]))
    cost("L1", f"L1 {L1['name']}", L1["cform"], L1["capex"])
    R3, X3 = R1 + L1["R"], X1 + L1["X"]
    I3 = log.add(T, "Isc at Q3 (ski MV bus)", "Z = Z_s + Z_L0 + Z_L1", isc_kA(c_max, U, R3, X3), "kA")
    net["isc"]["Q3"] = I3

    # ---------------- ski substation
    T = "ski"
    log.head(T, "Ski resort MV/LV substation")
    log.add(T, "Subscribed power (excluding lifts, EV)", "15 x 3 + 2 x 12", sub_s, "kVA")
    opts = {}
    o1 = dict(trs=[("T2 (all loads)", choose_tr(T, "Option 1 - T2 all loads", prof.ski_P, prof.ski_Q, p, log, i, n))])
    o2 = dict(trs=[("T2a (lifts)", choose_tr(T, "Option 2 - T2a lifts", prof.ski_lifts_P, prof.ski_lifts_Q, p, log, i, n)),
                   ("T2b (apartments, EV)", choose_tr(T, "Option 2 - T2b others", prof.ski_other_P,
                                                      prof.ski_other_Q, p, log, i, n,
                                                      S_min=sub_s * p["vil.ks"] + (p["ski.ev_dual"] if S["ev_ski"] else 0)))])
    for key, o in (("1", o1), ("2", o2)):
        ntr = len(o["trs"])
        tr_capex = sum(t["capex"] for _, t in o["trs"])
        sub = p["cost.sub_base"] + p["cost.sub_studies"] + p["cost.sub_cb"] * (1 + ntr) + p["cost.sub_unit"] * (1 + ntr)
        loss = sum(t["loss"] for _, t in o["trs"])
        o["capex"] = tr_capex + sub
        o["sub"] = sub
        o["cap"] = o["capex"] + (loss * p["cost.loss_price"] + p["cost.net_om"] / 100 * o["capex"]) * pwf(i, n)
        o["loss"] = loss
        opts[key] = o
        log.add(T, f"Option {key}: {ntr} transformer(s)",
                "C = TR + substation (20k + studies + CBs + units) + losses x PWF", o["cap"], "EUR",
                note=f"CAPEX {o['capex']:,.0f} EUR, losses {loss:,.0f} kWh/yr")
    choice = S["ski_tr"][0]
    if choice == "a":
        choice = min(opts, key=lambda k: opts[k]["cap"])
        log.add(T, "Transformer arrangement (auto)", "lowest capitalised cost", f"option {choice}",
                note="option 2 separates lift harmonics from apartments")
    net["tables"]["Ski transformer options"] = (
        ["option", "transformers", "CAPEX EUR", "losses kWh/yr", "capitalised EUR", "status"],
        [[k, " + ".join(f"{t['row']['Sn_kVA']} kVA" for _, t in o["trs"]), round(o["capex"]),
          round(o["loss"]), round(o["cap"]), "chosen" if k == choice else ""] for k, o in opts.items()])
    ski_opt = opts[choice]
    net["ski_opt"] = choice
    net["ski_trs"] = ski_opt["trs"]
    for nm, t in ski_opt["trs"]:
        elem("ski", nm, "transformer 20/0.4 kV", t["row"].get("model", f"{t['row']['Sn_kVA']} kVA"),
             f"loading {t['loading'] * 100:.0f} %, uk {t['row']['uk_pct']} %", "OK")
        cost("ski", f"{nm} {t['row']['Sn_kVA']} kVA", "20 kEUR/MVA x Sn", t["capex"])
    cost("ski", "Ski MV substation", "20k + 100k studies + CBs + units", ski_opt["sub"])

    lift_tr = ski_opt["trs"][0][1]
    h = None
    if S["lift2_vfd"]:
        busP = prof.ski_P if choice == "1" else prof.ski_lifts_P
        busQ = prof.ski_Q if choice == "1" else prof.ski_lifts_Q
        h = harmonics(p, busP, busQ, R3 * r2, X3 * r2, lift_tr["row"], log, T)
        if h["tr_new"]:
            old = lift_tr["row"]
            lift_tr["row"] = h["tr_new"]
            lift_tr["loading"] = lift_tr["loading"] * old["Sn_kVA"] / h["tr_new"]["Sn_kVA"]
            dc = p["cost.tr_eur_mva"] * (h["tr_new"]["Sn_kVA"] - old["Sn_kVA"]) / 1000
            for e in E["ski"]:
                if e["name"] == ski_opt["trs"][0][0]:
                    e["rating"] = h["tr_new"].get("model", f"{h['tr_new']['Sn_kVA']} kVA")
                    e["detail"] += ", oversized for harmonics"
            cost("ski", f"{ski_opt['trs'][0][0]} oversized for harmonics ({old['Sn_kVA']} -> {h['tr_new']['Sn_kVA']} kVA)",
                 "20 kEUR/MVA x extra Sn", dc)
    RT2, XT2, _ = tr_RX(lift_tr["row"], Ulv)
    R4, X4 = R3 * r2 + RT2, X3 * r2 + XT2
    I4 = log.add(T, "Isc at Q4 (ski LV bus, lifts)", "Z = Z_Q3 (U_lv/U_mv)^2 + Z_T2",
                 isc_kA(c_max, Ulv, R4, X4), "kA")
    I4min = isc_kA(c_min, Ulv, R4, X4) * SQ3 / 2
    log.add(T, "Min 2-phase Isc at Q4 (protection sensitivity)", "Isc2 = sqrt3/2 x c_min U/(sqrt3 Z)",
            I4min, "kA")
    net["isc"]["Q4"] = I4
    if choice == "2":
        tb = ski_opt["trs"][1][1]
        RTb, XTb, _ = tr_RX(tb["row"], Ulv)
        net["isc"]["Q4b"] = log.add(T, "Isc at Q4b (apartments LV bus)", "Z = Z_Q3 (U_lv/U_mv)^2 + Z_T2b",
                                    isc_kA(c_max, Ulv, R3 * r2 + RTb, X3 * r2 + XTb), "kA")
    k = lift_tr["k"]
    dUT2 = (prof.ski_P[k] * 1e3 * RT2 + prof.ski_Q[k] * 1e3 * XT2) / (Ulv * 1e3) ** 2 * 100 \
        if choice == "1" else (prof.ski_lifts_P[k] * 1e3 * RT2 + prof.ski_lifts_Q[k] * 1e3 * XT2) / (Ulv * 1e3) ** 2 * 100
    dU_s = L1["dU_cum"] + dUT2
    log.add(T, "Total drop source -> ski LV bus", "dU_L0 + dU_L1 + dU_T2", dU_s, "%",
            status=ok(dU_s <= p["geo.dU_tot_max"]))
    net["dU_ski"] = dU_s
    elem("ski", "Lift 1 (slip-ring)", "motor", f"{p['ski.motor_kw']:.0f} kW motor",
         f"operating {p['ski.lift1_kw']:.0f} kW, PF {p['ski.pf_slip']}")
    if h:
        net["harm"] = h
        net["tables"]["Harmonic compliance steps"] = h["steps_table"]
        if h["branches"]:
            net["tables"]["Harmonic filter design"] = h["filter_table"]
        net["tables"]["Harmonics at ski LV bus"] = h["table"]
        net["tables"]["Filter sizing iterations"] = h["iter_table"]
        elem("ski", "Lift 2 motor", "motor", f"{h['motor'].get('model', 'LS')} {h['motor']['P_kW']} kW", f"operating {p['ski.lift2_new_kw']:.0f} kW")
        elem("ski", f"ATV66{h['drive']['model']}", "variable speed drive", f"{h['drive']['P_kW']} kW",
             f"line choke {h['L_choke']:.3f} mH, THDi {h['thd_i']:.1f} %" if h["choke"] else
             f"no line choke, THDi {h['thd_i']:.1f} %")
        if h["Q_filter"]:
            elem("ski", "Passive harmonic filter", "filter",
                 f"{h['Q_filter']:.0f} kvar, branches h=" + ",".join(str(b["h"]) for b in h["branches"]),
                 f"THDv {h['thd_v0']:.2f} -> {h['thd_v1']:.2f} %, PF {h['pf0']:.2f} -> {h['pf1']:.2f}",
                 "OK" if h["ok"] else "FAIL")
            cost("ski", f"Harmonic filter {h['Q_filter']:.0f} kvar", f"{p['cost.filter_eur_kvar']} EUR/kvar",
                 h["Q_filter"] * p["cost.filter_eur_kvar"])
        cost("ski", f"ATV66{h['drive']['model']} drive", f"{p['cost.vfd_eur_kw']} EUR/kW x P",
             h["drive"]["P_kW"] * p["cost.vfd_eur_kw"])
    else:
        elem("ski", "Lift 2 (slip-ring)", "motor", f"{p['ski.motor_kw']:.0f} kW motor",
             f"operating {p['ski.lift_meas']:.0f} kW, PF {p['ski.pf_slip']}")
    elem("ski", "Apartments + restaurant/HQ", "load", f"{sub_s:.0f} kVA subscribed",
         f"{p['ski.n3']} x 3 kVA + {p['ski.n12']} x 12 kVA")
    if S["ev_ski"]:
        elem("ski", "EV dual charger", "load (non-linear)", f"{p['ski.ev_dual']:.0f} kW")

    # ---------------- L2 + eco substation
    if S["eco"]:
        T = "eco"
        log.head(T, "Eco-district")
        log.add(T, "Subscribed power", "5 x 6 + 12 x 9 + 12 x 3", sub_e, "kVA",
                note=f"measured forecast peak {prof.eco_P.max():.1f} kW, ks = {prof.eco_P.max() / sub_e:.2f}")
        elem("eco", "Dwellings (~20 buildings)", "load", f"{sub_e:.0f} kVA subscribed",
             f"{p['eco.n6']}x6 + {p['eco.n9']}x9 + {p['eco.n3']}x3 kVA")
    if eco_grid:
        T = "L2"
        L2, tabL2 = choose_line(T, "L2 village -> eco-district", p["geo.L2_len"], prof.eco_P, prof.eco_Q,
                                S["L2_type"], L0["dU"], I1, p, log, i, n)
        net["tables"]["L2 conductor choice"] = tabL2
        net["L2"] = L2
        elem("L2", L2["name"], "overhead line" if L2["type"] == "OHL" else "underground cable",
             f"{p['geo.L2_len']} km, {L2['S']} mm2",
             f"I {L2['I_des']:.1f}/{L2['Imax']} A, dU cum {L2['dU_cum']:.2f} %", ok(L2["feasible"]))
        R5, X5 = R1 + L2["R"], X1 + L2["X"]
        net["isc"]["Q5"] = log.add(T, "Isc at Q5 (eco MV bus)", "Z = Z_s + Z_L0 + Z_L2",
                                   isc_kA(c_max, U, R5, X5), "kA")
        T = "eco"
        tre = choose_tr(T, "T3 eco-district", prof.eco_P, prof.eco_Q, p, log, i, n)
        RT3, XT3, _ = tr_RX(tre["row"], Ulv)
        net["isc"]["Q6"] = log.add(T, "Isc at Q6 (eco LV bus)", "Z = Z_Q5 (U_lv/U_mv)^2 + Z_T3",
                                   isc_kA(c_max, Ulv, R5 * r2 + RT3, X5 * r2 + XT3), "kA")
        sub = p["cost.sub_base"] + p["cost.sub_cb"] * 2 + p["cost.sub_unit"] * 2
        net["eco_conn"] = dict(line=L2, tr=tre, sub=sub,
                               fixed_capex=tre["capex"] + sub,
                               line_capex_km=L2["capex"] / p["geo.L2_len"],
                               line_om_km=L2["om"] / p["geo.L2_len"],
                               loss_cost=(L2["loss"] + tre["loss"]) * p["cost.loss_price"])
        elem("eco", "T3", "transformer 20/0.4 kV", tre["row"].get("model", f"{tre['row']['Sn_kVA']} kVA"),
             f"loading {tre['loading'] * 100:.0f} %", "OK")
        cost("L2", f"L2 {L2['name']}", L2["cform"], L2["capex"])
        cost("eco", f"T3 {tre['row']['Sn_kVA']} kVA", "20 kEUR/MVA x Sn", tre["capex"])
        cost("eco", "Eco MV/LV substation", "20k + 2 CB + 2 units", sub)

    # ---------------- breakers
    log.head("source", "Circuit breakers (In >= margin x I_load, Icu >= Isc)")
    mv, lv = p.table("breakers_mv"), p.table("breakers_lv")
    pts = [("Q0", "source", "Source feeder 20 kV", L0["S_pk"], U, mv),
           ("Q1", "village", "Village MV incomer", L0["S_pk"], U, mv),
           ("Q2", "village", "Village LV main (per TR)", trv["row"]["Sn_kVA"], Ulv, lv),
           ("Q3", "ski", "Ski MV incomer", L1["S_pk"], U, mv),
           ("Q4", "ski", "Ski LV main (lifts TR)", lift_tr["row"]["Sn_kVA"], Ulv, lv)]
    if "Q4b" in net["isc"]:
        pts.append(("Q4b", "ski", "Ski LV main (apartments)", ski_opt["trs"][1][1]["row"]["Sn_kVA"], Ulv, lv))
    if "Q5" in net["isc"]:
        pts += [("Q5", "eco", "Eco MV incomer", net["L2"]["S_pk"], U, mv),
                ("Q6", "eco", "Eco LV main", net["eco_conn"]["tr"]["row"]["Sn_kVA"], Ulv, lv)]
    brows = []
    for q, node, name, S_kva, Uk, rows in pts:
        Iload = S_kva / (SQ3 * Uk)
        isc = net["isc"][q]
        r, need = pick_breaker(Iload, isc, rows, p["geo.line_margin"])
        rating = f"{r.get('model', '')}  {r['In_A']} A / {r['Icu_kA']} kA".strip() if r else "none in catalogue"
        log.add(node, f"Breaker {q} - {name}", f"In >= {p['geo.line_margin']} x {Iload:.1f} A; Icu >= {isc:.2f} kA",
                rating, "", status="OK" if r else "FAIL")
        elem(node, f"CB {q}", "circuit breaker", rating, f"I_load {Iload:.0f} A, Isc {isc:.2f} kA",
             "OK" if r else "FAIL")
        brows.append([q, name, round(Iload, 1), round(need, 1), round(isc, 2),
                      r.get("model", "") if r else "-", f"{r['In_A']} A / {r['Icu_kA']} kA" if r else "none"])
    net["tables"]["Breakers"] = (["point", "location", "I load A", "In min A", "Isc kA", "model", "rating"], brows)
    net["tables"]["Short-circuit currents"] = (["point", "Isc max kA"],
                                               [[k, round(v, 3)] for k, v in net["isc"].items()])

    # ---------------- cost summary
    new_capex = sum(c["value"] for c in net["costs"] if c["new"])
    net["capex_new"] = new_capex
    net["tables"]["Network costs"] = (["node", "item", "formula", "EUR", "new"],
                                      [[c["node"], c["item"], c["formula"], round(c["value"]),
                                        "yes" if c["new"] else "existing"] for c in net["costs"]])
    ski_conn = L1["capex"] + ski_opt["capex"] + sum(c["value"] for c in net["costs"]
                                                     if c["node"] == "ski" and ("filter" in c["item"] or "ATV" in c["item"]))
    loss_ann = (L1["loss"] + ski_opt["loss"]) * p["cost.loss_price"] + p["cost.net_om"] / 100 * ski_conn
    net["ski_conn_capex"] = ski_conn
    net["ski_conn_cap"] = ski_conn + loss_ann * pwf(i, n)
    log.head("ski", "Ski connection - capitalised cost over the project")
    log.add("ski", "Capitalised cost of the ski connection",
            f"C = CAPEX + (losses x {p['cost.loss_price']} + O&M) x PWF({i * 100:.0f} %, {n} yr)",
            net["ski_conn_cap"], "EUR", note=f"CAPEX {ski_conn:,.0f} EUR, annual {loss_ann:,.0f} EUR")
    return net


# ------------------------------------------------------------- LV feeder
def lv_feeder(p, log, Ulv, R_up, X_up, Isc_bus, dU_up):
    """One LV feeder along one road of the village (as asked in class):
    houses, cable, feeder breaker and house connections."""
    from .geo import route_km
    T = "feeder"
    U = Ulv * 1e3
    N = int(p["lvf.n_house"])
    L = p["lvf.len_m"] or route_km(p, "LVF") * 1000 * p["geo.route_factor"]
    a, b = p["lvf.ks_a"], p["lvf.ks_b"]
    ks = min(1.0, a + b / math.sqrt(N))
    S = N * p["lvf.kva"] * ks
    I = S * 1e3 / (SQ3 * U)
    Ides = I * p["geo.line_margin"]
    x0 = p["lvf.start"]
    Leq = L * (x0 + 1) / 2            # houses evenly spread from x0*L to L
    log.head(T, f"LV feeder F1 - one road of the village ({N} houses, {L:.0f} m)")
    log.add(T, "Feeder length", "L = sum haversine(route points)" if not p["lvf.len_m"] else "parameter", L, "m")
    log.add(T, "Diversity factor", f"k_s = a + b / sqrt(N) = {a} + {b} / sqrt({N})", ks, "")
    log.add(T, "Feeder power", "S = N x S_house x k_s", S, "kVA")
    log.add(T, "Feeder current", "I = S / (sqrt3 x U)", I, "A", note=f"with margin {p['geo.line_margin']}: {Ides:.1f} A")
    log.add(T, "Distance to the load centre", "L_eq = L (x_0 + 1) / 2", Leq, "m",
            note=f"first house at {x0:.0%} of the length, last at the end")
    rows = [r for r in p.table("lv_cables") if p["lvf.type"] in ("auto", r["type"])] or p.table("lv_cables")
    rho, xk = p["lvf.rho"], p["lvf.x_km"]
    U0 = U / SQ3
    res = []
    for c in rows:
        dU = c["kV_V_A_km"] * I * Leq / 1000 / U * 100
        Rl = rho * L / c["S_ph_mm2"] + rho * L / c["S_n_mm2"]
        Xl = 2 * xk * L / 1000
        Ik1 = p["grid.c_min"] * U0 / math.hypot(R_up + Rl, X_up + Xl) / 1000
        Ir = max(Ides, 1.0)
        Isd = p["lvf.Isd_min"] * Ir
        Isd_max = Ik1 * 1000 / 1.2
        d = dict(name=c["name"], type=c["type"], S=c["S_ph_mm2"], Imax=c["Imax_A"], dU=dU,
                 dU_tot=dU_up + dU, Ik1=Ik1, Isd=Isd, Isd_max=Isd_max, capex=c["eur_m"] * L,
                 ok_I=c["Imax_A"] >= Ides, ok_dU=dU <= p["lvf.dU_max"] and dU_up + dU <= p["geo.dU_tot_max"],
                 ok_sc=Isd <= Isd_max)
        d["feasible"] = d["ok_I"] and d["ok_dU"] and d["ok_sc"]
        res.append(d)
    feas = [r for r in res if r["feasible"]]
    best = min(feas, key=lambda r: r["capex"]) if feas else max(res, key=lambda r: r["S"])
    log.add(T, "Voltage drop (Silec method)", "dU% = k_V x I x L_eq / U x 100", None, "",
            note="k_V = catalogue drop per A and per km at cos phi 0.8")
    log.add(T, "Min. fault current at the last house", "Ik1_min = c_min U_0 / |Z_up + rho L (1/S_ph + 1/S_n) + j 2 x_c L|",
            None, "", note=f"Z_up = {R_up * 1000:.2f} + j{X_up * 1000:.2f} mohm (village LV bus)")
    log.add(T, "Protection sensitivity", f"I_sd = {p['lvf.Isd_min']} x I_r  <=  Ik1_min / 1.2", None, "")
    for r in res:
        st = "chosen" if r is best else ("OK" if r["feasible"] else
                                         "FAIL " + ",".join(x for x, f in (("I", r["ok_I"]), ("dU", r["ok_dU"]),
                                                                           ("Ik", r["ok_sc"])) if not f))
        log.add(T, f"  {r['name']} ({r['type']})",
                f"I {Ides:.0f}/{r['Imax']} A | dU {r['dU']:.2f} % (total {r['dU_tot']:.2f} %) | "
                f"Ik1 {r['Ik1']:.2f} kA | cost {r['capex']:,.0f} EUR", r["capex"], "EUR", status=st)
    brk, need = pick_breaker(I, Isc_bus, p.table("breakers_lv"), p["geo.line_margin"])
    log.add(T, "Feeder breaker", f"In >= {p['geo.line_margin']} x {I:.1f} A; Icu >= {Isc_bus:.2f} kA (village LV bus)",
            f"{brk['model']} {brk['In_A']} A / {brk['Icu_kA']} kA" if brk else "none", "",
            status="OK" if brk else "FAIL", note=f"settings: Ir = {Ides:.0f} A, Isd <= {best['Isd_max']:.0f} A")
    log.add(T, "Total drop source -> last house", "dU_L0 + dU_T1 + dU_F1", best["dU_tot"], "%",
            status=ok(best["dU_tot"] <= p["geo.dU_tot_max"]))
    kva = p["lvf.kva"]
    three = kva > 9
    Ih = kva * 1e3 / (SQ3 * U if three else U0)
    std = [10, 15, 20, 30, 45, 60, 90]
    hA = next((s for s in std if s >= Ih - 1e-6), std[-1])
    log.add(T, "House branch breaker (500 mA)", "I = S / U_0 (single phase)" if not three else "I = S / (sqrt3 U)",
            Ih, "A", status="chosen", note=f"standard setting {hA} A, {'3-phase' if three else 'single phase'}")
    table = (["cable", "type", "I design A", "Imax A", "dU %", "dU total %", "Ik1 min kA", "Isd max A",
              "cost EUR", "status"],
             [[r["name"], r["type"], round(Ides, 1), r["Imax"], round(r["dU"], 2), round(r["dU_tot"], 2),
               round(r["Ik1"], 3), round(r["Isd_max"]), round(r["capex"]),
               "chosen" if r is best else ("ok" if r["feasible"] else "fail")] for r in res])
    return dict(N=N, L=L, ks=ks, S=S, I=I, Ir=Ides, cable=best, breaker=brk, table=table,
                house_A=hA, house_ph="3-phase" if three else "single phase")
