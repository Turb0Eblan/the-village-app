"""Calculation log (every step keeps its formula) and finance helpers."""
import math


class Log:
    """Ordered list of calculation steps. Each step is shown in the report
    and in the node windows, so the user can follow how a value was chosen."""

    def __init__(self):
        self.steps = []

    def add(self, tag, title, formula="", value=None, unit="", status="", note=""):
        self.steps.append(dict(tag=tag, title=title, formula=formula, value=value,
                               unit=unit, status=status, note=note))
        return value

    def head(self, tag, title):
        self.steps.append(dict(tag=tag, title=title, formula="", value=None, unit="",
                               status="", note="", header=True))

    def for_tags(self, *tags):
        return [s for s in self.steps if s["tag"] in tags]


def fmt(v, d=3):
    """Short number formatting used everywhere in the UI."""
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "yes" if v else "no"
    try:
        a = abs(v)
    except TypeError:
        return str(v)
    if a == 0:
        return "0"
    if a >= 1e6:
        return f"{v:,.0f}".replace(",", " ")
    if a >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    if a >= 100:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.{min(d, 3)}f}".rstrip("0").rstrip(".")
    return f"{v:.{d + 1}g}"


def ok(cond):
    return "OK" if cond else "FAIL"


# ---------------------------------------------------------------- finance
def crf(i, n):
    """Capital recovery factor."""
    return i * (1 + i) ** n / ((1 + i) ** n - 1)


def pwf(i, n):
    """Present worth factor of a constant annual amount (= 1/CRF)."""
    return (1 - (1 + i) ** -n) / i


def npc_component(capex, om_yr, life, i, n, repl=None):
    """HOMER-like NPC of one component: capital + O&M + replacements - salvage."""
    if capex <= 0 and om_yr <= 0:
        return 0.0, dict(capex=0, om=0, repl=0, salvage=0)
    repl = capex if repl is None else repl
    life = max(1, int(round(life)))
    om = om_yr * pwf(i, n)
    rep = 0.0
    y = life
    while y < n:
        rep += repl / (1 + i) ** y
        y += life
    # salvage: linear remaining life of the last unit at the end of the project
    last_install = ((n - 1) // life) * life
    remain = life - (n - last_install)
    salvage = repl * remain / life / (1 + i) ** n
    total = capex + om + rep - salvage
    return total, dict(capex=capex, om=om, repl=rep, salvage=salvage)


def std_up(value, series):
    """Smallest standard value >= value (or the largest if none)."""
    for s in sorted(series):
        if s >= value - 1e-9:
            return s
    return max(series)
