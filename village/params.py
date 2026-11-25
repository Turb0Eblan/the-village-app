"""
All project inputs in one place.

Every scalar parameter has: key, label, value, unit, source.
Every catalogue is a table (columns + rows) the user can edit in the
Parameters screen. Default values come from the project subject, the
course price sheets and the team's earlier work (sources are noted).
"""
import copy
import json

SUBJ = "Subject PDF (BE-village 26-27)"
COSTS = "Tarifs/Costs.html (teacher)"
TEAM_TH = "Tuan_Hung Deliverable.xlsx"
TEAM_DUY = "Duy - HOMER Economic Data.docx"
TEAM_ECO = "BE_eco_district_results.md"
ASSUMED = "assumption (editable)"


def P(key, label, value, unit="", source=ASSUMED):
    return {"key": key, "label": label, "value": value, "unit": unit, "source": source}


SECTIONS = [
    ("grid", "Grid source (HV/MV substation)", [
        P("U_hv", "HV voltage", 63.0, "kV", SUBJ),
        P("U_mv", "MV voltage", 20.0, "kV", SUBJ),
        P("U_lv", "LV voltage (phase-phase)", 0.4, "kV", SUBJ),
        P("Ssc", "Short-circuit power at source", 300.0, "MVA", SUBJ),
        P("RX_src", "Source R/X ratio", 0.2, "-", TEAM_TH),
        P("c_max", "Voltage factor c (max Isc, IEC 60909)", 1.1, "-", "IEC 60909"),
        P("c_min", "Voltage factor c (min Isc)", 0.95, "-", "IEC 60909"),
        P("f", "Frequency", 50.0, "Hz"),
    ]),
    ("geo", "Network geometry and limits", [
        P("L0_len", "L0 source -> village length", 8.0, "km", SUBJ),
        P("L0_cond", "L0 conductor (existing)", "ASTER 148", "", SUBJ + " (150 mm2)"),
        P("L1_len", "L1 village -> ski resort length", 4.0, "km", SUBJ),
        P("L2_len", "L2 village -> eco-district length", 8.0, "km", SUBJ + " p.3"),
        P("dU_mv_max", "Max voltage drop on MV network", 5.0, "%", "NF C 15-100 / EN 50160"),
        P("dU_tot_max", "Max total drop to LV delivery point", 10.0, "%", "EN 50160 (+/-10 %)"),
        P("tr_max_load", "Max transformer loading at peak", 100.0, "%", TEAM_TH),
        P("line_margin", "Design margin on line current", 1.25, "-"),
        P("t_fault", "Fault clearing time (cable thermal check)", 0.5, "s"),
        P("k_cable", "k factor Al XLPE cable", 94.0, "A.s^0.5/mm2", "IEC 60949"),
        P("k_ohl", "k factor bare Almelec conductor", 85.0, "A.s^0.5/mm2", ASSUMED),
        P("n_vil_tr", "Number of MV/LV substations in village", 1, "-", TEAM_TH + " (1 x T1)"),
        P("lv_radius", "Max LV feeder length (info)", 250.0, "m", "lecture"),
        P("len_from_map", "Take L1 / L2 lengths from the map routes (1 = yes)", 0, "-"),
        P("route_factor", "Route length / map polyline length", 1.0, "-"),
    ]),
    ("lvf", "LV feeder example (village, cluster 2 road)", [
        P("n_house", "Houses on the feeder", 24, "-", "lecture: show one road, one feeder"),
        P("kva", "Contract per house", 9.0, "kVA", SUBJ + " (cluster 2)"),
        P("ks_a", "Diversity ks = a + b / sqrt(N): a", 0.2, "-", ASSUMED),
        P("ks_b", "Diversity ks = a + b / sqrt(N): b", 0.8, "-", ASSUMED),
        P("start", "First house at (fraction of length), only without the house table", 0.35, "-"),
        P("type", "Cable type (OHL / UG / auto)", "UG", "", "village centre: underground"),
        P("len_m", "Feeder length (0 = from map route)", 0.0, "m"),
        P("dU_max", "Max voltage drop on the LV feeder", 6.0, "%", "with T1 drop stays inside EN 50160 +/-10 %"),
        P("rho", "Aluminium resistivity (hot, fault)", 0.036, "ohm.mm2/m", "NF C 15-100 (1.25 x rho20)"),
        P("x_km", "Cable reactance", 0.08, "ohm/km"),
        P("Isd_min", "Lowest short-time trip setting of the feeder breaker", 1.5, "x Ir", "Micrologic 2.2"),
    ]),
    ("vil", "Village loads", [
        P("n6", "Subscribers 6 kVA", 180, "-", SUBJ),
        P("n9", "Subscribers 9 kVA", 250, "-", SUBJ),
        P("n12", "Subscribers 12 kVA", 100, "-", SUBJ),
        P("S_mun", "Municipal site (lighting + water tower)", 36.0, "kVA", SUBJ),
        P("S_saw", "Sawmill", 36.0, "kVA", SUBJ),
        P("pf", "Power factor (residential/commercial)", 0.95, "-", TEAM_TH),
        P("ks", "Simultaneity coefficient (cross-check)", 0.35, "-", SUBJ + " 0.25-0.45"),
        P("ev_fast", "EV fast charger", 50.0, "kW", SUBJ),
        P("ev_dual", "EV dual charger 2 x 22 kW", 44.0, "kW", SUBJ),
        P("ev_pf", "EV charger power factor", 0.99, "-"),
    ]),
    ("ski", "Ski resort loads", [
        P("n3", "Small apartments 3 kVA", 15, "-", SUBJ),
        P("n12", "Professional 12 kVA (restaurant, HQ)", 2, "-", SUBJ),
        P("pf_sub", "Power factor of subscribers", 0.95, "-"),
        P("motor_kw", "Original lift motor rating", 75.0, "kW", SUBJ),
        P("lift_meas", "Lift operating point in measured curve", 65.0, "kW", SUBJ),
        P("lift1_kw", "Lift 1 operating power (slip-ring)", 65.0, "kW", SUBJ),
        P("lift2_new_kw", "Lift 2 operating power after renovation", 100.0, "kW", SUBJ),
        P("pf_slip", "Power factor slip-ring motor", 0.87, "-", ASSUMED),
        P("pf_vfd", "Displacement PF with VFD", 0.95, "-", ASSUMED),
        P("eta_motor", "Motor efficiency", 0.95, "-", "LS catalogue"),
        P("choke", "Line choke on ATV66 (1 = yes)", 1, "-", "Harmonics_ATV66.pdf"),
        P("ev_dual", "EV dual charger 2 x 22 kW", 44.0, "kW", SUBJ),
        P("pf_target", "Target power factor (capacitor/filter)", 0.95, "-", TEAM_TH),
        P("filt_q", "Filter quality factor", 30.0, "-"),
        P("filt_detune", "Tuning factor (h_t = factor x h)", 0.96, "-"),
        P("lab_U", "ATV66 harmonic table: test voltage", 400.0, "V", "Harmonics_ATV66.pdf, lecture DG7"),
        P("lab_Isc", "ATV66 harmonic table: test short-circuit current", 22.0, "kA", "Harmonics_ATV66.pdf, lecture DG7"),
        P("harm_tr_max", "Step 2: max transformer oversizing for harmonics", 2.0, "x Sn", "lecture DG7 ('a bit')"),
    ]),
    ("eco", "Eco-district loads", [
        P("n6", "Contracts 6 kVA", 5, "-", SUBJ),
        P("n9", "Contracts 9 kVA", 12, "-", SUBJ),
        P("n3", "Contracts 3 kVA", 12, "-", SUBJ),
        P("pf", "Power factor", 0.95, "-"),
    ]),
    ("cost", "Network costs", [
        P("tr_eur_mva", "Transformer", 20000.0, "EUR/MVA", COSTS),
        P("sub_base", "Substation (constant part)", 20000.0, "EUR", COSTS),
        P("sub_cb", "Circuit breaker", 20000.0, "EUR/unit", COSTS),
        P("sub_unit", "Other unit (switch, metering, line cell)", 10000.0, "EUR/unit", COSTS),
        P("sub_studies", "New MV substation studies & tests", 100000.0, "EUR", "MV-substation_cost.html"),
        P("ohl_eur_km", "Overhead line (lines + poles + works)", 30000.0, "EUR/km", COSTS),
        P("cable_lay", "Cable excavation and laying", 17.0, "EUR/m", COSTS),
        P("loss_price", "Price of lost energy", 0.10, "EUR/kWh"),
        P("net_om", "Network O&M", 1.0, "%CAPEX/yr"),
        P("filter_eur_kvar", "Harmonic filter", 60.0, "EUR/kvar"),
        P("vfd_eur_kw", "Variable speed drive", 150.0, "EUR/kW"),
    ]),
    ("econ", "Economics", [
        P("i", "Discount rate", 8.0, "%", SUBJ),
        P("n", "Project lifetime", 20, "years", SUBJ),
        P("co2_grid", "Grid CO2 factor", 20.0, "g/kWh", "RTE 2025 / team HOMER 19.6"),
        P("overrun", "Price of kWh above subscription", 0.50, "EUR/kWh", SUBJ + " (very expensive)"),
        P("sell", "Feed-in price (export)", 0.07, "EUR/kWh", "2007 decree hydro, " + TEAM_ECO),
        P("retail", "Retail price (eco-district via grid)", 0.20, "EUR/kWh", TEAM_ECO),
        P("ext_eur_km", "Grid extension capital (HOMER)", 180000.0, "EUR/km", TEAM_ECO),
        P("ext_om_km", "Grid extension O&M", 1800.0, "EUR/yr/km", TEAM_ECO),
    ]),
    ("pv", "Photovoltaic", [
        P("capex", "Capital cost", 1100.0, "EUR/kWp", TEAM_DUY + " 1000-1200"),
        P("capex_eco", "Capital cost, building-integrated (eco)", 2500.0, "EUR/kWp", TEAM_ECO),
        P("om", "O&M", 20.0, "EUR/kWp/yr"),
        P("life", "Lifetime", 25, "years"),
        P("derate", "Derating factor", 0.85, "-"),
        P("tcoef", "Temperature coefficient", -0.40, "%/degC"),
        P("noct", "NOCT", 45.0, "degC"),
    ]),
    ("hyd", "Hydro", [
        P("v_head", "River (village): gross head", 22.0, "m", SUBJ),
        P("v_D", "River: penstock diameter", 1.10, "m", SUBJ),
        P("v_L", "River: penstock length", 250.0, "m", SUBJ),
        P("v_eta", "River: turbine efficiency", 75.0, "%", SUBJ),
        P("v_Qd", "River: design flow", 0.80, "m3/s"),
        P("eA_head", "Stream intake A: gross head", 219.0, "m", SUBJ),
        P("eA_D", "Intake A: penstock diameter", 0.10, "m", SUBJ),
        P("eA_L", "Intake A: penstock length", 1400.0, "m", SUBJ),
        P("eB_head", "Stream intake B: gross head", 342.0, "m", SUBJ),
        P("eB_D", "Intake B: penstock diameter", 0.15, "m", SUBJ),
        P("eB_L", "Intake B: penstock length", 2400.0, "m", SUBJ),
        P("e_eta", "Stream: turbine efficiency", 82.0, "%", SUBJ),
        P("e_Qd", "Stream: design flow", 12.0, "L/s", TEAM_ECO),
        P("reserved", "Reserved flow left in river", 10.0, "%", "French law (debit reserve)"),
        P("min_ratio", "Min turbine flow ratio", 50.0, "%", TEAM_ECO),
        P("rough", "Pipe roughness", 0.045, "mm", "steel"),
        P("capex_kw", "Turbine + civil works", 4000.0, "EUR/kW"),
        P("pipe_eur_m", "Penstock cost per m per m of diameter", 800.0, "EUR/(m.m)"),
        P("om_pct", "O&M", 2.0, "%CAPEX/yr"),
        P("life", "Lifetime", 40, "years"),
    ]),
    ("bat", "Battery + converter", [
        P("capex", "Battery capital", 700.0, "EUR/kWh", TEAM_ECO),
        P("om", "Battery O&M", 10.0, "EUR/kWh/yr", TEAM_ECO),
        P("life", "Battery lifetime", 15, "years", TEAM_ECO),
        P("eff", "Round-trip efficiency", 90.0, "%"),
        P("soc_min", "Minimum state of charge", 20.0, "%"),
        P("c_rate", "Max C-rate", 0.5, "1/h"),
        P("conv_capex", "Converter capital", 300.0, "EUR/kW", TEAM_ECO),
        P("conv_eff", "Converter efficiency", 95.0, "%"),
        P("conv_life", "Converter lifetime", 15, "years"),
    ]),
    ("wind", "Wind turbine (generic 10 kW)", [
        P("rated", "Rated power", 10.0, "kW", TEAM_ECO),
        P("capex", "Capital per turbine", 50000.0, "EUR", TEAM_ECO),
        P("om", "O&M per turbine", 500.0, "EUR/yr", TEAM_ECO),
        P("hub", "Hub height", 24.0, "m"),
        P("alpha", "Wind shear exponent", 0.14, "-"),
        P("v_in", "Cut-in speed", 3.0, "m/s"),
        P("v_r", "Rated speed", 11.0, "m/s"),
        P("v_out", "Cut-out speed", 25.0, "m/s"),
        P("life", "Lifetime", 20, "years"),
    ]),
    ("bio", "Biogas CHP (farm manure + food waste)", [
        P("yield", "Biogas yield", 30.0, "m3/t", "spec_note.pptx"),
        P("lhv", "Biogas energy content", 6.0, "kWh/m3"),
        P("eta_el", "Electrical efficiency", 35.0, "%"),
        P("collect", "Collectable fraction of biomass file", 100.0, "%"),
        P("capex", "Capital cost", 5000.0, "EUR/kW"),
        P("om", "O&M", 0.02, "EUR/kWh"),
        P("life", "Lifetime", 15, "years"),
    ]),
    ("opt", "Optimisation search space", [
        P("vil_pv", "Village PV sizes", "0, 250, 500, 1000, 2000, 3000, 4000, 5000", "kWp"),
        P("vil_bat", "Village battery sizes", "0, 500, 1000, 2000", "kWh"),
        P("vil_bio", "Village biogas sizes", "0, 50", "kW"),
        P("eco_pv", "Eco PV sizes", "0, 50, 100, 150, 200, 300, 400, 500", "kWp"),
        P("eco_bat", "Eco battery sizes", "0, 250, 500, 1000, 1500, 2000", "kWh"),
        P("eco_wind", "Eco wind turbines", "0, 3", "#"),
        P("eco_bio", "Eco biogas sizes", "0, 15, 30", "kW"),
        P("max_unmet", "Max unmet load (isolated)", 0.1, "%", "HOMER capacity shortage"),
    ]),
]

# ------------------------------------------------------------------ catalogues
TABLES = {
    "transformers": {
        "title": "MV/LV transformers 20/0.41 kV (Schneider Minera, oil immersed ONAN)",
        "source": "Substation/Minera_letEN00.pdf",
        "columns": ["model", "Sn_kVA", "P0_W", "Pk_W", "uk_pct"],
        "rows": [
            ["Minera 100 kVA", 100, 210, 2150, 4], ["Minera 160 kVA", 160, 460, 2350, 4],
            ["Minera 250 kVA", 250, 650, 3250, 4], ["Minera 315 kVA", 315, 800, 3900, 4],
            ["Minera 400 kVA", 400, 930, 4600, 4], ["Minera 500 kVA", 500, 1100, 5500, 4],
            ["Minera 630 kVA", 630, 1300, 6500, 4], ["Minera 800 kVA", 800, 1220, 10700, 6],
            ["Minera 1000 kVA", 1000, 1470, 13000, 6], ["Minera 1250 kVA", 1250, 1800, 16000, 6],
            ["Minera 1600 kVA", 1600, 2300, 20000, 6], ["Minera 2000 kVA", 2000, 2750, 25500, 6],
            ["Minera 2500 kVA", 2500, 3350, 32000, 6], ["Minera 3150 kVA", 3150, 4380, 33000, 7],
        ],
    },
    "conductors": {
        "title": "MV conductors (overhead Almelec ASTER / underground Al C33-226)",
        "source": "Silec catalogues; UG eur_m = cable price (SilecPriceList3_2010.xls); OHL eur_m = extra Almelec metal vs 34.4 mm2 (3 x 2.7 kg/km/mm2 x 4 EUR/kg)",
        "columns": ["name", "type", "S_mm2", "R_ohm_km", "X_ohm_km", "Imax_A", "eur_m"],
        "rows": [
            ["ASTER 22", "OHL", 22, 1.50, 0.30, 105, 0],
            ["ASTER 34.4", "OHL", 34.4, 0.958, 0.35, 160, 0],
            ["ASTER 54.6", "OHL", 54.6, 0.603, 0.35, 220, 0.65],
            ["ASTER 75.5", "OHL", 75.5, 0.438, 0.35, 270, 1.33],
            ["ASTER 117", "OHL", 117, 0.283, 0.33, 360, 2.68],
            ["ASTER 148", "OHL", 148, 0.224, 0.30, 420, 3.68],
            ["ASTER 228", "OHL", 228, 0.146, 0.31, 550, 6.27],
            ["AL 3x50", "UG", 50, 0.641, 0.13, 165, 21.7],
            ["AL 3x95", "UG", 95, 0.320, 0.12, 235, 26.9],
            ["AL 3x150", "UG", 150, 0.206, 0.11, 300, 33.5],
            ["AL 3x240", "UG", 240, 0.125, 0.10, 390, 46.1],
        ],
    },
    "breakers_mv": {
        "title": "MV circuit breakers 24 kV (SM6 cubicle with SF1/SF2 SF6 breaker)",
        "source": "mv_design_guide.pdf (ratings); model names Schneider SM6 range, " + ASSUMED,
        "columns": ["model", "In_A", "Icu_kA"],
        "rows": [["SM6 DM1-A / SF1 400 A", 400, 12.5], ["SM6 DM1-A / SF1 630 A", 630, 16],
                 ["SM6 DM1-A / SF1 630 A 25 kA", 630, 25], ["SM6 DM1-A / SF2 1250 A", 1250, 20],
                 ["SM6 DM1-D / SF2 1250 A 25 kA", 1250, 25], ["MCset / Evolis 2500 A", 2500, 25]],
    },
    "breakers_lv": {
        "title": "LV circuit breakers 400 V (Compact NSX / Masterpact)",
        "source": "Schneider ranges: NSX F 36 kA, N 50 kA, H 70 kA; Masterpact NT H2 50 kA, NW H1 65 kA, H2 100 kA; " + ASSUMED,
        "columns": ["model", "In_A", "Icu_kA"],
        "rows": [["Compact NSX100F", 100, 36], ["Compact NSX100H", 100, 70],
                 ["Compact NSX160F", 160, 36], ["Compact NSX160H", 160, 70],
                 ["Compact NSX250F", 250, 36], ["Compact NSX250H", 250, 70],
                 ["Compact NSX400N", 400, 50], ["Compact NSX400H", 400, 70],
                 ["Compact NSX630N", 630, 50], ["Compact NSX630H", 630, 70],
                 ["Masterpact NT08H2", 800, 50], ["Masterpact NW08H2", 800, 100],
                 ["Masterpact NW10H1", 1000, 65], ["Masterpact NW10H2", 1000, 100],
                 ["Masterpact NW12H1", 1250, 65], ["Masterpact NW12H2", 1250, 100],
                 ["Masterpact NW16H1", 1600, 65], ["Masterpact NW16H2", 1600, 100],
                 ["Masterpact NW20H1", 2000, 65], ["Masterpact NW20H2", 2000, 100],
                 ["Masterpact NW25H1", 2500, 65], ["Masterpact NW25H2", 2500, 100],
                 ["Masterpact NW32H1", 3200, 65], ["Masterpact NW32H2", 3200, 100],
                 ["Masterpact NW40H1", 4000, 65], ["Masterpact NW40H2", 4000, 100],
                 ["Masterpact NW50H1", 5000, 100], ["Masterpact NW63H1", 6300, 100]],
    },
    "atv66": {
        "title": "ATV66 drives 400 V, constant torque (I1 and harmonics in % of H1)",
        "source": "Motor/Harmonics_ATV66.pdf p.86 (no choke) and p.88 (with choke)",
        "columns": ["model", "P_kW", "L_mH", "Iline_choke", "H5c", "H7c", "H11c", "H13c",
                    "Iline_nochoke", "H5n", "H7n", "H11n", "H13n", "H1_A"],
        "rows": [
            ["C10N4", 75, 0.15, 136, 38, 14, 7.5, 3.5, 171, 75, 55, 19, 9, 124],
            ["C13N4", 90, 0.15, 160, 43, 19, 8, 4, 198, 73, 52, 15, 8, 148],
            ["C15N4", 110, 0.15, 194, 39, 15, 7.5, 3.5, 237, 70, 48, 12, 7, 181],
            ["C19N4", 132, 0.15, 226, 40, 16, 7.5, 3.5, 275, 68, 45, 10, 7.5, 213],
            ["C23N4", 160, 0.075, 294, 40.3, 15.9, 7.6, 3.8, 326, 63.1, 38.1, 8, 7.9, 268.3],
            ["C28N4", 200, 0.075, 359, 36.6, 12.6, 7.2, 3.4, 399, 55.9, 31.1, 7.7, 6.6, 333.8],
            ["C31N4", 220, 0.075, 390, 35.3, 11.6, 7.1, 3.4, 421, 53.1, 28.3, 7.8, 6, 363.7],
        ],
    },
    "motors": {
        "title": "Leroy-Somer LS 4-pole motors 400 V 50 Hz (IP55, full load values)",
        "source": "Motor/4-LS-triphases-en.pdf (4 poles, 1500 min-1 table)",
        "columns": ["model", "P_kW", "eta_pct", "pf", "In_A"],
        "rows": [["LS 280 SC", 75, 93.5, 0.84, 138], ["LS 280 MD", 90, 93.5, 0.84, 165],
                 ["LS 315 SN", 110, 94.1, 0.84, 201], ["LS 315 MP", 132, 94.2, 0.85, 238],
                 ["LS 315 MR", 160, 94.7, 0.85, 287], ["LS 315 MR (200)", 200, 94.9, 0.84, 362]],
    },
    "lv_cables": {
        "title": "LV distribution cables 0.6/1 kV, aluminium (Silec)",
        "source": "Cables/2222_LVunderground.pdf (H1 XDV-AS, NF C 33-210) and 2221_LVoverhead.pdf (mains ABC, NF C 33-209); k_V = catalogue voltage drop per km and per A at cos phi 0.8",
        "columns": ["name", "type", "S_ph_mm2", "S_n_mm2", "Imax_A", "kV_V_A_km", "eur_m"],
        "rows": [["ABC 3x35+54.6", "OHL", 35, 54.6, 138, 1.60, 6],
                 ["ABC 3x70+54.6", "OHL", 70, 54.6, 213, 0.91, 9],
                 ["ABC 3x150+70", "OHL", 150, 70, 344, 0.50, 15],
                 ["H1 XDV-AS 3x50+50", "UG", 50, 50, 140, 1.20, 9],
                 ["H1 XDV-AS 3x95+50", "UG", 95, 50, 210, 0.62, 13],
                 ["H1 XDV-AS 3x150+70", "UG", 150, 70, 280, 0.43, 18],
                 ["H1 XDV-AS 3x240+95", "UG", 240, 95, 370, 0.29, 26]],
    },
    "sites": {
        "title": "Positions on the map (WGS84)",
        "source": "team Google My Map 'The Village' (TheVillage objectives), other points " + ASSUMED,
        "columns": ["key", "node", "name", "lat", "lon", "source"],
        "rows": [
            ["src", "source", "HV/MV substation 63/20 kV", 45.1300, 5.5860, "assumed, towards Lans-en-Vercors"],
            ["vil_sub", "village", "Village MV/LV substation (T1)", 45.1762622, 5.5428289, "team map"],
            ["vil_c1", "village", "Cluster 1 - 180 x 6 kVA", 45.1792078, 5.5416022, "team map"],
            ["vil_c2", "village", "Cluster 2 - 250 x 9 kVA", 45.1742358, 5.5470240, "team map"],
            ["vil_c3", "village", "Cluster 3 - 100 x 12 kVA", 45.1720927, 5.5405797, "team map"],
            ["vil_mun", "village", "Town hall + water tower 36 kVA", 45.1748534, 5.5428277, "team map"],
            ["vil_saw", "village", "Sawmill 36 kVA", 45.1774251, 5.5501607, "team map"],
            ["vil_evf", "village", "Fast EV charger 50 kW", 45.1760360, 5.5396834, "team map"],
            ["vil_evd", "village", "Dual EV charger 2 x 22 kW", 45.1767633, 5.5459610, "team map"],
            ["vil_pv", "village", "PV plant", 45.1700, 5.5500, "assumed, open field south-east"],
            ["vil_hyd", "village", "River hydro plant", 45.1715, 5.5560, "assumed, on Le Meaudret"],
            ["vil_bio", "village", "Biogas CHP (farms + sawmill waste)", 45.1790, 5.5520, "assumed, near the sawmill"],
            ["vil_bat", "village", "Battery + converter", 45.1770, 5.5440, "assumed, next to the substation"],
            ["ski_sub", "ski", "Ski MV/LV substation (T2)", 45.2195879, 5.5810475, "team map"],
            ["ski_l1", "ski", "Chairlift 1 (slip-ring)", 45.2232841, 5.5789143, "team map"],
            ["ski_l2", "ski", "Chairlift 2 (VFD ATV66)", 45.2214761, 5.5829545, "team map"],
            ["ski_rest", "ski", "Restaurant / resort office 2 x 12 kVA", 45.2193126, 5.5775736, "team map"],
            ["ski_apt", "ski", "Apartments 15 x 3 kVA", 45.2170, 5.5795, "assumed near the station"],
            ["ski_ev", "ski", "Dual EV charger 2 x 22 kW", 45.2179662, 5.5780293, "team map"],
            ["eco_sub", "eco", "Eco MV/LV substation (T3) / microgrid controller", 45.1717663, 5.5564406, "team map"],
            ["eco_c6", "eco", "6 kVA dwellings (x5)", 45.1747860, 5.5605970, "team map"],
            ["eco_c9", "eco", "9 kVA dwellings (x12)", 45.1727032, 5.5593111, "team map"],
            ["eco_c3", "eco", "3 kVA dwellings (x12)", 45.1734324, 5.5617759, "team map"],
            ["eco_pv", "eco", "PV (building roofs)", 45.1745510, 5.5633241, "team map"],
            ["eco_hyd", "eco", "Stream hydro (intake A/B)", 45.1714, 5.5622, "team map (moved 150 m south for legibility)"],
            ["eco_bio", "eco", "Biogas CHP", 45.1740494, 5.5574004, "team map"],
            ["eco_bat", "eco", "Battery + converter", 45.1710, 5.5580, "assumed, next to the controller"],
            ["eco_wind", "eco", "Wind turbines", 45.1765, 5.5655, "assumed, ridge east of the district"],
        ],
    },
    "routes": {
        "title": "Line routes on the map (points in order)",
        "ver": 2,
        "source": "L1 follows the D218 polyline of the team map; the LV feeder follows the streets of OpenStreetMap; L0 and L2 " + ASSUMED,
        "columns": ["line", "lat", "lon"],
        "rows": [
            ["L0", 45.1300, 5.5860], ["L0", 45.1450, 5.5700], ["L0", 45.1600, 5.5560],
            ["L0", 45.1700, 5.5480], ["L0", 45.1762622, 5.5428289],
            ["L1", 45.1762622, 5.5428289], ["L1", 45.1748534, 5.5428277], ["L1", 45.1780341, 5.5481221],
            ["L1", 45.1814513, 5.5568644], ["L1", 45.1922642, 5.5647038], ["L1", 45.2058803, 5.5728554],
            ["L1", 45.2195879, 5.5810475],
            ["L2", 45.1762622, 5.5428289], ["L2", 45.1748534, 5.5428277], ["L2", 45.1735, 5.5480],
            ["L2", 45.1722, 5.5530], ["L2", 45.1717663, 5.5564406],
            ["LVF", 45.1762622, 5.5428289], ["LVF", 45.1761243, 5.5427779], ["LVF", 45.1760583, 5.5428673], ["LVF", 45.1758584, 5.5431609],
            ["LVF", 45.1756289, 5.5435319], ["LVF", 45.1759739, 5.5442402], ["LVF", 45.1761317, 5.5444942],
            ["LVF", 45.1761538, 5.5445362], ["LVF", 45.1761892, 5.5446038], ["LVF", 45.1762131, 5.5446661],
            ["LVF", 45.1761831, 5.5447099], ["LVF", 45.1760573, 5.5449714], ["LVF", 45.1760348, 5.5450247],
            ["LVF", 45.1759857, 5.5451405], ["LVF", 45.1759463, 5.5452336], ["LVF", 45.1757989, 5.5455816],
            ["LVF", 45.1757145, 5.5457808], ["LVF", 45.1755434, 5.5461191], ["LVF", 45.1754378, 5.5463280],
            ["LVF", 45.1753600, 5.5464817], ["LVF", 45.1753258, 5.5465802], ["LVF", 45.1753036, 5.5466509],
            ["LVF", 45.1752463, 5.5468084], ["LVF", 45.1752164, 5.5469350], ["LVF", 45.1751856, 5.5471198],
            ["LVF", 45.1751756, 5.5473381], ["LVF", 45.1750978, 5.5473714], ["LVF", 45.1749678, 5.5474445],
            ["LVF", 45.1748205, 5.5475326], ["LVF", 45.1747477, 5.5475820], ["LVF", 45.1746871, 5.5476489],
            ["LVF", 45.1746505, 5.5477000], ["LVF", 45.1746245, 5.5477363], ["LVF", 45.1745885, 5.5478093],
            ["LVF", 45.1745633, 5.5478868], ["LVF", 45.1745151, 5.5480740], ["LVF", 45.1745036, 5.5482148],
            ["LVF", 45.1745557, 5.5482629], ["LVF", 45.1746369, 5.5483349], ["LVF", 45.1746927, 5.5484177],
        ],
    },
    "lvf_houses": {
        "title": "Houses on LV feeder F1 (cluster 2 road)",
        "source": "building footprints and streets from OpenStreetMap (c) OpenStreetMap contributors, ODbL; the 24 buildings closest to the road",
        "columns": ["n", "lat", "lon", "tap_lat", "tap_lon", "s_m"],
        "rows": [
            [1, 45.1757990, 5.5429750, 45.1758952, 5.5431068, 36],
            [2, 45.1757494, 5.5430709, 45.1758424, 5.5431868, 45],
            [3, 45.1756502, 5.5431413, 45.1757747, 5.5432963, 56],
            [4, 45.1759385, 5.5438363, 45.1758293, 5.5439433, 120],
            [5, 45.1761834, 5.5440415, 45.1759960, 5.5442758, 152],
            [6, 45.1761064, 5.5441964, 45.1760165, 5.5443088, 155],
            [7, 45.1761318, 5.5442501, 45.1760464, 5.5443569, 161],
            [8, 45.1762274, 5.5443219, 45.1761133, 5.5444646, 172],
            [9, 45.1764512, 5.5447311, 45.1762131, 5.5446661, 191],
            [10, 45.1764392, 5.5448944, 45.1762131, 5.5446661, 191],
            [11, 45.1759706, 5.5446777, 45.1761261, 5.5448283, 207],
            [12, 45.1757788, 5.5451732, 45.1759207, 5.5452941, 250],
            [13, 45.1756949, 5.5454354, 45.1758168, 5.5455393, 273],
            [14, 45.1756806, 5.5454982, 45.1757935, 5.5455944, 278],
            [15, 45.1754378, 5.5458830, 45.1755863, 5.5460342, 319],
            [16, 45.1750892, 5.5464092, 45.1753274, 5.5465756, 371],
            [17, 45.1754811, 5.5468472, 45.1752845, 5.5467033, 382],
            [18, 45.1749266, 5.5478284, 45.1748359, 5.5475234, 474],
            [19, 45.1747728, 5.5474619, 45.1748011, 5.5475458, 478],
            [20, 45.1747019, 5.5480561, 45.1745411, 5.5479728, 524],
            [21, 45.1743006, 5.5483903, 45.1745036, 5.5482148, 543],
            [22, 45.1745642, 5.5485883, 45.1746914, 5.5484158, 570],
            [23, 45.1747717, 5.5485037, 45.1746927, 5.5484177, 570],
            [24, 45.1745650, 5.5487448, 45.1746927, 5.5484177, 570],
        ],
    },
    "harm_limits": {
        "title": "IEC 61000-3-12 current emission limits (balanced 3-phase)",
        "source": "IEC 61000-3-12 table 4",
        "columns": ["Rsce_min", "I5", "I7", "I11", "I13", "THD", "PWHD"],
        "rows": [[33, 10.7, 7.2, 3.1, 2, 13, 22], [66, 14, 9, 5, 3, 16, 25],
                 [120, 19, 12, 7, 4, 22, 28], [250, 31, 20, 12, 7, 37, 38],
                 [350, 40, 25, 15, 10, 48, 46]],
    },
    "tariff": {
        "title": "EDF MV supply options (fixed EUR/kW/yr, energy c EUR/kWh by period)",
        "source": TEAM_DUY,
        "columns": ["option", "fixed", "WinterPeak", "WinterFull", "WinterOff", "SummerFull", "SummerOff"],
        "rows": [["TLU", 51.24, 5.97, 4.69, 3.34, 3.36, 1.71],
                 ["LU", 31.20, 9.19, 5.48, 3.43, 3.37, 1.71],
                 ["MU", 19.32, 12.35, 6.28, 3.55, 3.38, 1.72],
                 ["CU", 7.80, 17.27, 7.52, 3.73, 3.45, 1.75]],
    },
    "flows": {
        "title": "Monthly average flows",
        "source": SUBJ + " p.4",
        "columns": ["month", "river_m3s", "stream_Ls"],
        "rows": [["Jan", 0.82, 12.2], ["Feb", 0.75, 11.4], ["Mar", 0.71, 13.3],
                 ["Apr", 0.72, 13.6], ["May", 1.03, 12.3], ["Jun", 1.06, 15.7],
                 ["Jul", 1.10, 12.2], ["Aug", 1.09, 11.4], ["Sep", 0.90, 10.1],
                 ["Oct", 0.96, 9.5], ["Nov", 0.87, 9.9], ["Dec", 0.78, 11.5]],
    },
}

# ------------------------------------------------------------- scenario years
# What exists in the system each year (the team's story line).
SETUP_FIELDS = [
    ("lift2_vfd", "Lift 2 renovated with VFD (ATV66)", "bool"),
    ("ev_village", "EV chargers in village centre", "bool"),
    ("ev_ski", "EV charger at ski resort", "bool"),
    ("vil_res", "Renewables in village (PV / river hydro / battery)", "bool"),
    ("vil_hydro", "River hydro plant allowed", "bool"),
    ("vil_bio", "Biogas CHP allowed in village", "bool"),
    ("eco", "Eco-district built", "bool"),
    ("eco_mode", "Eco-district supply", ["isolated", "grid", "compare"]),
    ("ski_tr", "Ski resort MV/LV transformers", ["1 (all loads)", "2 (lifts separate)", "auto"]),
    ("L1_type", "L1 village -> ski line", ["auto", "OHL", "UG"]),
    ("L2_type", "L2 village -> eco line", ["auto", "OHL", "UG"]),
    ("net_zero", "Net-zero energy target (export >= import)", "bool"),
    ("min_ren", "Minimum renewable fraction of village system (%)", "num"),
]

YEARS = {
    "2010": dict(title="2010 - Establishment", lift2_vfd=False, ev_village=False, ev_ski=False,
                 vil_res=False, vil_hydro=False, vil_bio=False, eco=False, eco_mode="compare",
                 ski_tr="1 (all loads)", L1_type="auto", L2_type="auto", net_zero=False, min_ren=0,
                 note="Grid only. Both chairlifts with slip-ring motors (65 kW)."),
    "2015": dict(title="2015 - Chairlift upgrade", lift2_vfd=True, ev_village=False, ev_ski=False,
                 vil_res=False, vil_hydro=False, vil_bio=False, eco=False, eco_mode="compare",
                 ski_tr="auto", L1_type="auto", L2_type="auto", net_zero=False, min_ren=0,
                 note="Lift 2 gets a VFD (ATV66) and 100 kW operating point. "
                      "Ski connection rebuilt after the incident. Harmonic filter needed."),
    "2020": dict(title="2020 - EV charging", lift2_vfd=True, ev_village=True, ev_ski=True,
                 vil_res=False, vil_hydro=False, vil_bio=False, eco=False, eco_mode="compare",
                 ski_tr="auto", L1_type="auto", L2_type="auto", net_zero=False, min_ren=0,
                 note="50 kW fast + 2x22 kW in village, 2x22 kW at ski resort."),
    "2025": dict(title="2025 - Partial renewables", lift2_vfd=True, ev_village=True, ev_ski=True,
                 vil_res=True, vil_hydro=True, vil_bio=False, eco=False, eco_mode="compare",
                 ski_tr="auto", L1_type="auto", L2_type="auto", net_zero=False, min_ren=20,
                 note="PV + river hydro in the village (at least 20 % renewable) to cut the EDF subscription."),
    "2026": dict(title="2026 - Eco-district (project task)", lift2_vfd=True, ev_village=True,
                 ev_ski=True, vil_res=True, vil_hydro=True, vil_bio=False, eco=True,
                 eco_mode="compare", ski_tr="auto", L1_type="auto", L2_type="auto", net_zero=False, min_ren=20,
                 note="Final state of the subject: new lift, chargers, eco-district "
                      "(isolated vs grid-connected, break-even distance)."),
    "2030": dict(title="2030 - Net-zero", lift2_vfd=True, ev_village=True, ev_ski=True,
                 vil_res=True, vil_hydro=True, vil_bio=True, eco=True, eco_mode="isolated",
                 ski_tr="auto", L1_type="auto", L2_type="auto", net_zero=True, min_ren=0,
                 note="Village exports at least as much as it imports over the year."),
}
DEFAULT_YEAR = "2026"

# ------------------------------------------- team HOMER results (for compare)
HOMER_REF = [
    {"case": "Eco-district isolated (HOMER, team)", "year": "2026",
     "arch": "PV 150 kW, 3 x G10 wind, 1500 kWh Li-ion, hydro 21.1 kW, conv. 50 kW",
     "NPC": 3.02e6, "LCOE": 1.23, "REN": 100.0,
     "src": "Study/2026-EcoDistrict-Atur/BE_eco_district_results.md "
            "(ECO_results.csv gives NPC 2.46 MEUR, LCOE 1.00)"},
    {"case": "Eco-district + grid (HOMER, team)", "year": "2026",
     "arch": "Hydro 21.1 kW + grid", "NPC": 227850, "LCOE": 0.0767, "REN": 68.0,
     "src": "Study/2026-EcoDistrict-Atur/ECO+grid_results.csv row 1"},
    {"case": "Break-even grid extension (team)", "year": "2026",
     "arch": "D = (NPC_iso x CRF - P_grid x E) / (C_cap x CRF + C_om)", "NPC": None,
     "LCOE": None, "REN": None, "dist_km": 13.4,
     "src": "BE_eco_district_results.md section 6"},
    {"case": "Village + ski net-zero (HOMER, team)", "year": "2030",
     "arch": "PV 5235 kW, hydro 80.9 kW, conv. 3898 kW, grid", "NPC": 6165654,
     "LCOE": 0.0476, "REN": 67.8,
     "src": "Study/2030-RESfull-Thinh/RUN_4_Grid_adjust summary row 1"},
]


# ------------------------------------------------------------------- helpers
class Params:
    """Flat access p['grid.Ssc'] plus the editable structures for the GUI."""

    def __init__(self):
        self.sections = copy.deepcopy(SECTIONS)
        self.tables = copy.deepcopy(TABLES)

    def __getitem__(self, dotted):
        sec, key = dotted.split(".")
        for name, _t, items in self.sections:
            if name == sec:
                for it in items:
                    if it["key"] == key:
                        return it["value"]
        raise KeyError(dotted)

    def set(self, dotted, value):
        sec, key = dotted.split(".")
        for name, _t, items in self.sections:
            if name == sec:
                for it in items:
                    if it["key"] == key:
                        it["value"] = value
                        return
        raise KeyError(dotted)

    def label(self, dotted):
        sec, key = dotted.split(".")
        for name, _t, items in self.sections:
            if name == sec:
                for it in items:
                    if it["key"] == key:
                        return it["label"], it["unit"]
        return dotted, ""

    def table(self, name):
        t = self.tables[name]
        return [dict(zip(t["columns"], r)) for r in t["rows"]]

    def list(self, dotted):
        v = self[dotted]
        if isinstance(v, (int, float)):
            return [float(v)]
        return [float(x) for x in str(v).replace(";", ",").split(",") if x.strip()]

    def to_json(self):
        return json.dumps({
            "values": {f"{s}.{it['key']}": it["value"] for s, _t, items in self.sections
                       for it in items},
            "tables": {k: v["rows"] for k, v in self.tables.items()},
            "columns": {k: v["columns"] for k, v in self.tables.items()},
            "versions": {k: v.get("ver", 1) for k, v in self.tables.items()},
        }, indent=1)

    def load_json(self, text):
        d = json.loads(text)
        for k, v in d.get("values", {}).items():
            try:
                self.set(k, v)
            except KeyError:
                pass
        cols = d.get("columns", {})
        vers = d.get("versions", {})
        for k, rows in d.get("tables", {}).items():
            # tables saved by an older version (other columns or data version) are ignored
            if k in self.tables and cols.get(k) == self.tables[k]["columns"] \
                    and vers.get(k, 1) == self.tables[k].get("ver", 1):
                self.tables[k]["rows"] = rows

    def snapshot(self):
        p = Params()
        p.sections = copy.deepcopy(self.sections)
        p.tables = copy.deepcopy(self.tables)
        return p

    def diff_from_default(self):
        """List of (key, default, current) for changed scalar values."""
        base = Params()
        out = []
        for (s, _t, items), (_s2, _t2, items2) in zip(base.sections, self.sections):
            for a, b in zip(items, items2):
                if a["value"] != b["value"]:
                    out.append((f"{s}.{a['key']}", a["value"], b["value"]))
        return out


def year_setup(year):
    d = dict(YEARS[year])
    d["year"] = year
    return d
