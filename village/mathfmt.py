"""Turns the plain-text formulas of the calculation log
('I = S_peak / (sqrt3 x U) x margin') into typeset formulas (matplotlib
mathtext), rendered as images for the Tk text widgets - fractions, square
roots, indices and Greek letters as in a Word equation."""
import base64
import io
import re

from matplotlib import mathtext
from matplotlib.font_manager import FontProperties

TOK = re.compile(r"""
 (?P<om>O&M)
|(?P<num>\d+(?:[.,]\d+)?(?![A-Za-z_]))
|(?P<id>[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+(?:,[A-Za-z0-9]+)?)?)
|(?P<op>>=|<=|!=|->|[=<>+\-*/,;&%:])
|(?P<lp>\()|(?P<rp>\))|(?P<bar>\|)
|(?P<pow>\^-?[A-Za-z0-9.]+)
|(?P<ws>\s+)
|(?P<other>.)""", re.X)

GREEK = {"phi": r"\varphi", "eta": r"\eta", "rho": r"\rho", "omega": r"\omega", "alpha": r"\alpha",
         "beta": r"\beta", "lambda": r"\lambda", "mu": r"\mu", "tau": r"\tau", "theta": r"\theta",
         "Delta": r"\Delta", "pi": r"\pi", "sigma": r"\sigma"}
FUNCS = {"cos": r"\cos", "sin": r"\sin", "tan": r"\tan", "max": r"\max", "min": r"\min",
         "ln": r"\ln", "exp": r"\exp", "sum": r"\sum", "log": r"\log"}
UNITS = {"A", "kA", "V", "kV", "kVA", "kW", "kWh", "MWh", "m", "km", "h", "s", "EUR", "kvar", "ohm",
         "mohm", "mm2", "MVA", "Hz", "yr", "kWp", "L"}
OPS = {">=": r"\geq", "<=": r"\leq", "!=": r"\neq", "->": r"\rightarrow", "*": r"\cdot", "%": r"\%",
       "&": "&", "=": "=", "+": "+", "-": "-", "<": "<", ">": ">", ",": ",", ";": ";", ":": ":"}
# words that may appear inside a formula without making it a sentence
MATHWORDS = {"sqrt", "sum", "max", "min", "cos", "sin", "tan", "phi", "eta", "rho", "margin", "price",
             "loading", "factor", "over", "with", "for", "per", "and", "hav", "haversine", "target",
             "contracts", "ratio", "yield", "day", "mean", "power", "curve"}
SUB_SHORT = re.compile(r"^([A-Z])(sc|cu|sd|r|n|k|k1|h|1|0|th|pk|max|min|app|el|c)$")


def _sub(s):
    return s if len(s) == 1 or s.isdigit() else r"\mathrm{" + s + "}"


def _ident(name, prev_num=False):
    if prev_num and name in UNITS:
        return r"\,\mathrm{" + name + "}"
    base, _, sub = name.partition("_")
    if base == "x" and not sub:
        return "x"
    if base == "sqrt3":
        t = r"\sqrt{3}"
    elif base == "dU":
        t = r"\Delta U"
    elif base in GREEK:
        t = GREEK[base]
    elif re.match(r"^(phi|eta|rho)\d$", base):
        t = GREEK[base[:-1]] + "_" + base[-1]
    elif base in FUNCS:
        t = FUNCS[base]
    elif len(base) == 1:
        t = base
    elif SUB_SHORT.match(base):
        m = SUB_SHORT.match(base)
        t = m.group(1) + "_{" + _sub(m.group(2)) + "}"
        if sub:
            t = m.group(1) + "_{" + _sub(m.group(2) + "," + sub) + "}"
            sub = ""
    elif re.match(r"^[A-Z][a-z]?\d+$", base):        # P0, I1, H5
        m = re.match(r"^([A-Z][a-z]?)(\d+)$", base)
        t = m.group(1) + "_{" + m.group(2) + "}"
    else:
        t = r"\mathrm{" + base + "}"
    if sub:
        t = "{" + t + "}_{" + _sub(sub) + "}"
    return t


def _tokens(s):
    out = []
    for m in TOK.finditer(s):
        k = m.lastgroup
        if k == "ws":
            continue
        out.append((k, m.group()))
    return out


def _parse(toks, i, end=None):
    """Returns (list of items, next index). Item = dict(kind, tex, inner)."""
    items = []
    while i < len(toks):
        k, v = toks[i]
        if end and k == end:
            return items, i + 1
        if k == "rp" or (k == "bar" and end == "bar"):
            return items, i + 1
        if k == "lp":
            inner, i = _parse(toks, i + 1, "rp")
            tex = _join(inner)
            items.append(dict(kind="atom", tex=r"\left(" + tex + r"\right)", inner=tex))
            continue
        if k == "bar":
            inner, i = _parse(toks, i + 1, "bar")
            tex = _join(inner)
            items.append(dict(kind="atom", tex=r"\left|" + tex + r"\right|", inner=tex))
            continue
        if k == "om":
            items.append(dict(kind="atom", tex=r"\mathrm{O&M}", inner=r"\mathrm{O&M}"))
            i += 1
            continue
        if k == "pow":
            e = v[1:]
            e = "-" + _ident(e[1:]) if e.startswith("-") and e[1:].isalpha() else (_ident(e) if e.isalpha() else e)
            if items and items[-1]["kind"] == "atom":
                items[-1]["tex"] = "{" + items[-1]["tex"] + "}^{" + e + "}"
                items[-1]["inner"] = items[-1]["tex"]
            else:
                items.append(dict(kind="atom", tex="^{" + e + "}", inner=e))
            i += 1
            continue
        if k == "id" and v == "sqrt":
            # sqrt(...) or sqrt N
            if i + 1 < len(toks) and toks[i + 1][0] == "lp":
                inner, i = _parse(toks, i + 2, "rp")
                tex = r"\sqrt{" + _join(inner) + "}"
            elif i + 1 < len(toks) and toks[i + 1][0] in ("num", "id"):
                tex = r"\sqrt{" + _ident(toks[i + 1][1]) + "}"
                i += 2
            else:
                tex = r"\sqrt{\ }"
                i += 1
            items.append(dict(kind="atom", tex=tex, inner=tex))
            continue
        if k == "id" and v == "x" and items and items[-1]["kind"] == "atom" \
                and i + 1 < len(toks) and toks[i + 1][0] in ("num", "id", "lp", "bar"):
            items.append(dict(kind="op", tex=r"\times", op="x"))
            i += 1
            continue
        if k in ("num", "id"):
            prev_num = bool(items) and items[-1].get("num")
            if k == "num":
                tex = v.replace(",", "{,}")
            else:
                tex = _ident(v, prev_num)
            items.append(dict(kind="atom", tex=tex, inner=tex, num=(k == "num")))
            i += 1
            continue
        if k == "op":
            items.append(dict(kind="op", tex=OPS.get(v, v), op=v))
            i += 1
            continue
        items.append(dict(kind="atom", tex=re.sub(r"([#$&%_{}])", r"\\\1", v), inner=v))
        i += 1
    return items, i


def _fractions(items):
    out = list(items)
    j = 0
    while j < len(out):
        it = out[j]
        if it.get("op") == "/" and 0 < j < len(out) - 1 \
                and out[j - 1]["kind"] == "atom" and out[j + 1]["kind"] == "atom" \
                and not (j + 2 < len(out) and out[j + 2].get("op") == "/") \
                and not (j - 2 >= 0 and out[j - 2].get("op") == "/"):
            a, b = out[j - 1], out[j + 1]
            tex = r"\frac{" + a["inner"] + "}{" + b["inner"] + "}"
            out[j - 1:j + 2] = [dict(kind="atom", tex=tex, inner=tex)]
            j = max(j - 1, 0)
            continue
        j += 1
    return out


def _join(items):
    items = _fractions(items)
    parts = []
    prev = None
    for it in items:
        if prev is not None and prev["kind"] == "atom" and it["kind"] == "atom" and not it["tex"].startswith(r"\,"):
            parts.append(r"\,")
        parts.append(it["tex"] if it["kind"] == "atom" else " " + it["tex"] + " ")
        prev = it
    return "".join(parts)


def _split_top(s):
    """Split at ', ' / '; ' / ' | ' outside brackets."""
    out, depth, cur, k = [], 0, "", 0
    while k < len(s):
        ch = s[k]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and s[k:k + 2] in (", ", "; ") or depth == 0 and s[k:k + 3] == " | ":
            out.append((cur, s[k:k + 2].strip() if s[k:k + 3] != " | " else "|"))
            cur = ""
            k += 3 if s[k:k + 3] == " | " else 2
            continue
        cur += ch
        k += 1
    out.append((cur, ""))
    return out


def _words(seg):
    w = re.findall(r"(?<![_A-Za-z0-9])[a-z]{3,}(?![_A-Za-z0-9(])", seg)
    return [x for x in w if x not in MATHWORDS]


def is_math(seg):
    words = _words(seg)
    has_op = bool(re.search(r"(=|>=|<=|\^|sqrt|/|\+|\bx\b)", seg))
    return has_op and (len(words) <= 1 or ("=" in seg and len(words) <= 4))


def to_tex(seg):
    return "$" + _join(_parse(_tokens(seg), 0)[0]) + "$"


def pieces(formula):
    """[(kind, text)] with kind 'tex' or 'text'."""
    out = []
    if " | " in formula:            # table-like rows of candidates stay plain text
        return [("text", formula)]
    for seg, sep in _split_top(formula):
        seg = seg.strip()
        tail = ""
        m = re.match(r"^(.*?\S)\s*(\([^()]*\))$", seg)
        if m and len(_words(m.group(2))) >= 1 and is_math(m.group(1)):
            seg, tail = m.group(1), m.group(2)
        if seg:
            out.append(("tex", to_tex(seg)) if is_math(seg) else ("text", seg))
        if tail:
            out.append(("text", "  " + tail))
        if sep:
            out.append(("text", sep + " " if sep != "|" else "  |  "))
    return out


_cache = {}


def png_b64(tex, size=13, color="#1f3864", dpi=110):
    key = (tex, size, color, dpi)
    if key not in _cache:
        buf = io.BytesIO()
        mathtext.math_to_image(tex, buf, prop=FontProperties(size=size), dpi=dpi, format="png", color=color)
        _cache[key] = base64.b64encode(buf.getvalue())
    return _cache[key]
