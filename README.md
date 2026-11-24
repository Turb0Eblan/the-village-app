# The Village – network & distributed generation app

Start: double-click `Start The Village.command` (first start installs numpy + matplotlib
into `~/.venvs/village-dg`), or run `python main.py` in an environment with numpy and matplotlib.

## Screens
- **Map**: real map of Autrans (Google map / terrain / satellite, OpenStreetMap, OpenTopoMap) or a
  schematic view. Overview shows source, village, ski resort, eco-district and the MV lines.
  Click a block: the map zooms in and shows where the substation, transformers, loads, plants,
  lifts and the LV feeder (houses along one road) are. The side panel shows the selected
  equipment; "Open details" opens the single-line diagram, typeset formulas and tables.
  Positions come from the team Google My Map and can be edited in Parameters -> sites / routes.
  Tiles are kept in `data/map_tiles.sqlite`, so places already seen also work offline.
- **Year** (top): 2010 base → 2015 lift VFD → 2020 EV → 2025 partial RES → 2026 eco-district
  (project task, default) → 2030 net-zero.
- **Parameters**: every input and catalogue (transformers, conductors, ATV66, tariffs, flows…),
  with its source. Double-click to edit, then press **Calculate**.
- **Setup**: what exists in the chosen year (lift VFD, chargers, RES, eco-district mode…).
- **Compare**: all runs side by side, a chart, and the team's HOMER results next to the app's.
- **Report**: full calculation log for a run, all tables, CSV export.

## What is calculated
- Load curves rebuilt from the team files (lift and EV powers are parameters).
- Equipment models: Minera transformers, SM6/SF1 and Compact NSX / Masterpact breakers,
  Leroy-Somer LS motors, ATV66 drives, Silec MV and LV cables.
- LV feeder example (one road of the village, as asked in class): diversity, Silec voltage drop,
  minimum fault current at the last house vs breaker setting, house branch breaker.
- Transformer sizing, conductor choice for L1/L2 (ampacity, ΔU, short-circuit thermal limit,
  capitalised cost over 20 yr at 8 %), Isc at Q0…Q6 (IEC 60909), breakers.
- Lift 2: motor + ATV66 choice, IEC 61000-3-12 limits, passive filter sized step by step,
  THDv, impedance scan.
- Hourly energy model (PV, river/stream hydro with penstock losses, wind, biogas, battery, grid),
  EDF option + subscription choice, NPC / LCOE / renewable fraction, search over sizes,
  eco-district isolated vs grid and break-even distance.

Code: `village/params.py` (inputs), `network.py`, `energy.py`, `engine.py`, `ui_*.py` (interface).
Data: `data/` (8760 h load curves in kW and weather).

## Dashboard, best values, harmonics (lecture DG7)
- **Dashboard** (top bar): key figures of a run as tiles and six charts: monthly supply mix, average January/July day, NPC breakdown, network margins (% of each limit), and NPC and renewable share across runs.
- **Best values:**
  - Compare page: the best run per quantity is green with a ★, the worst is red.
  - Option tables: the best NPC, LCOE, cost, renewable share, CO2 or THD value is marked with ★. Failed options are ignored.
- **Lift 2 harmonics** follow the 3 steps of lecture DG7:
  1. **Line choke.** Sized by matching impedances with the ATV66 test case: X_ch = X_lab + X_ch,mfr − X_net, with the test at 400 V / 22 kA and 0.15 mH. Results are checked against IEC 61000-3-12 for the R_sce and against EN 50160 for V_h.
  2. **Oversized transformer.** Up to `ski.harm_tr_max` × Sn.
  3. **Tuned filters.** One per non-compliant harmonic:
     - C comes from the reactive power to compensate. Q is first split equally (as in the lecture); if that cannot pass, it is split by the excess harmonic current.
     - L = 1/(C ω_h²), and R comes from the quality factor q.
  - THD = sqrt(Σ I_h²) / I_1.
  - Tables: "Harmonic compliance steps", "Harmonic filter design", "Filter sizing iterations".
