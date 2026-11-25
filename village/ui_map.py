"""Map of Autrans: real tiles (Google / OpenStreetMap) with the network on
top, plus a simple schematic view that also works without internet.

Overview: source, village, ski resort, eco-district and the MV lines.
Click a block: the map zooms in and shows where the substation,
transformers, loads, plants and the LV feeder are."""
import io
import os
import sqlite3
import threading
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageFont, ImageTk

from .geo import sites, route, point_at, route_km
from .ui_common import GREEN, RED

try:
    import requests
    import tkintermapview
    HAVE_MAP = True
except Exception:          # map package missing -> schematic only
    HAVE_MAP = False

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "map_tiles.sqlite")

TILES = {
    "Google map": ("https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga", 20),
    "Google terrain": ("https://mt0.google.com/vt/lyrs=p&hl=en&x={x}&y={y}&z={z}&s=Ga", 20),
    "Google satellite": ("https://mt0.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}&s=Ga", 20),
    "OpenStreetMap": ("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", 19),
    "OpenTopoMap": ("https://a.tile.opentopomap.org/{z}/{x}/{y}.png", 17),
}

INK = "#1a1a1a"
BLUE = "#1f4e79"
ORANGE = "#c55a11"
GREY_L = "#9a9a9a"
TITLE = {"source": "Source 63/20 kV", "village": "Village", "ski": "Ski resort", "eco": "Eco-district"}


# ------------------------------------------------------------ PIL drawing
def _font(size, bold=False):
    for path, idx in (("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0),
                      ("/System/Library/Fonts/HelveticaNeue.ttc", 1 if bold else 0),
                      ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", 0),
                      ("arialbd.ttf" if bold else "arial.ttf", 0)):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


F_T, F_L, F_S = _font(13, True), _font(11), _font(10)


def _status_col(st):
    return {"OK": GREEN, "FAIL": RED}.get(st, GREY_L)


def card(title, lines, status="", faded=False):
    """White label box (title + lines + status square)."""
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = max([d0.textlength(title, font=F_T) + 30] + [d0.textlength(t, font=F_L) for t in lines]) + 16
    h = 24 + 15 * len(lines) + 6
    im = Image.new("RGBA", (int(w) + 2, int(h) + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fg = "#9a9a9a" if faded else INK
    d.rounded_rectangle([0, 0, w, h], radius=4, fill=(255, 255, 255, 235), outline=fg, width=2)
    d.text((8, 5), title, font=F_T, fill=fg)
    if status:
        d.rectangle([w - 18, 8, w - 8, 18], fill=_status_col(status))
    for k, t in enumerate(lines):
        d.text((8, 24 + 15 * k), t, font=F_L, fill="#8a8a8a" if faded else "#333333")
    return im


def symbol(kind, status=""):
    """Small equipment symbol 18 px."""
    im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = RED if status == "FAIL" else INK
    if kind == "sub":
        d.rectangle([2, 2, 17, 17], fill="white", outline=col, width=2)
        d.ellipse([4, 5, 12, 13], outline=col, width=1)
        d.ellipse([8, 5, 16, 13], outline=col, width=1)
    elif kind == "gen":
        d.ellipse([2, 2, 17, 17], fill="#fff2cc", outline=col, width=2)
        d.text((6, 3), "G", font=F_S, fill=col)
    elif kind == "motor":
        d.ellipse([2, 2, 17, 17], fill="white", outline=col, width=2)
        d.text((5, 3), "M", font=F_S, fill=col)
    elif kind == "ev":
        d.rectangle([3, 2, 16, 17], fill="#e2efda", outline=col, width=2)
        d.text((5, 3), "EV", font=_font(8, True), fill=col)
    elif kind == "bat":
        d.rectangle([2, 5, 17, 15], fill="#ddebf7", outline=col, width=2)
        d.rectangle([17, 8, 19, 12], fill=col)
    elif kind == "house":
        d.polygon([(2, 9), (8, 3), (14, 9)], fill="white", outline=col)
        d.rectangle([4, 9, 12, 15], fill="white", outline=col)
        return im.crop((0, 0, 17, 17))
    elif kind == "house_s":       # small filled house for real buildings
        d.polygon([(1, 6), (6, 1), (11, 6)], fill=ORANGE, outline=INK)
        d.rectangle([2, 6, 10, 11], fill=ORANGE, outline=INK)
        return im.crop((0, 0, 12, 12))
    elif kind == "dot":
        d.ellipse([5, 5, 14, 14], fill=INK, outline="white", width=2)
    else:  # load
        d.ellipse([3, 3, 16, 16], fill="white", outline=col, width=2)
        d.polygon([(6, 8), (13, 8), (9.5, 13)], fill=col)
    return im


def label_above(kind, lines, status=""):
    """Label box above the symbol (used for the substation); anchor 's'."""
    box = label_icon("dot", lines, status)
    box = box.crop((symbol("dot").width + 3, 0, box.width, box.height))
    sym = symbol(kind, status)
    W = max(box.width, sym.width)
    im = Image.new("RGBA", (W, box.height + 4 + sym.height), (0, 0, 0, 0))
    im.paste(box, ((W - box.width) // 2, 0), box)
    im.paste(sym, ((W - sym.width) // 2, box.height + 4), sym)
    return im


def label_icon(kind, lines, status="", left=False):
    """Symbol + small label to its right (anchor 'w'), or to its left (left=True, anchor 'e')."""
    sym = symbol(kind, status)
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = max(d0.textlength(t, font=F_L if k else _font(11, True)) for k, t in enumerate(lines)) + 10
    th = 15 * len(lines) + 4
    W = int(sym.width + 4 + tw)
    H = int(max(sym.height, th))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if left:
        im.paste(sym, (W - sym.width, (H - sym.height) // 2), sym)
        x0 = 0
        d.rounded_rectangle([0, 0, W - sym.width - 4, H - 1], radius=3, fill=(255, 255, 255, 225),
                            outline=RED if status == "FAIL" else "#555555")
    else:
        im.paste(sym, (0, (H - sym.height) // 2), sym)
        x0 = sym.width + 3
        d.rounded_rectangle([x0, 0, W - 1, H - 1], radius=3, fill=(255, 255, 255, 225),
                            outline=RED if status == "FAIL" else "#555555")
    for k, t in enumerate(lines):
        head, sep, rest = t.partition("  ")
        fb = _font(11, True)
        d.text((x0 + 5, 2 + 15 * k), head, font=fb, fill=RED if status == "FAIL" else INK)
        if rest:
            d.text((x0 + 5 + d.textlength(head + "  ", font=fb), 2 + 15 * k), rest, font=F_L, fill="#333333")
    return im


# ------------------------------------------------------------ cached tiles
if HAVE_MAP:
    class CachedMapView(tkintermapview.TkinterMapView):
        """Map widget that keeps every downloaded tile in a local sqlite file,
        so places already seen also open without internet."""

        _lock = threading.Lock()

        def __init__(self, *a, **k):
            try:
                os.makedirs(os.path.dirname(CACHE), exist_ok=True)
                with sqlite3.connect(CACHE) as con:
                    con.execute("CREATE TABLE IF NOT EXISTS tiles (server TEXT, z INT, x INT, y INT, img BLOB,"
                                " PRIMARY KEY (server, z, x, y))")
            except Exception:
                pass
            super().__init__(*a, **k)

        def request_image(self, zoom, x, y, db_cursor=None):
            key = (self.tile_server, zoom, x, y)
            data = None
            try:
                with sqlite3.connect(CACHE, timeout=5) as con:
                    row = con.execute("SELECT img FROM tiles WHERE server=? AND z=? AND x=? AND y=?", key).fetchone()
                data = row[0] if row else None
            except Exception:
                pass
            if data is None:
                try:
                    url = self.tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
                    r = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=10)
                    if r.status_code == 200 and r.content:
                        data = r.content
                        with self._lock, sqlite3.connect(CACHE, timeout=5) as con:
                            con.execute("INSERT OR REPLACE INTO tiles VALUES (?,?,?,?,?)", key + (data,))
                except Exception:
                    return self.empty_tile_image
            try:
                image = Image.open(io.BytesIO(data))
                if not self.running:
                    return self.empty_tile_image
                tkimg = ImageTk.PhotoImage(image)
                self.tile_image_cache[f"{zoom}{x}{y}"] = tkimg
                return tkimg
            except Exception:
                return self.empty_tile_image


# ------------------------------------------------------------ content
def node_status(run, node):
    if not run:
        return ""
    tags = {"village": ("village", "feeder"), "ski": ("ski",), "eco": ("eco", "energy-eco"),
            "source": ("source",), "L0": ("L0",), "L1": ("L1",), "L2": ("L2",)}[node]
    return "FAIL" if any(s["tag"] in tags for s in run["fails"]) else "OK"


def node_card_lines(run, node):
    p = run["params"]
    k = run["kpi"]
    net = run["net"]
    S = run["setup"]
    if node == "source":
        return [f"S_sc {p['grid.Ssc']:.0f} MVA", f"Isc Q0 {net['isc']['Q0']:.2f} kA"]
    if node == "village":
        out = [f"T1 {k['T1 village']}", f"peak {k['Village peak (kW)']} kW"]
        if S["ev_village"]:
            out.append(f"EV {p['vil.ev_fast']:.0f} + {p['vil.ev_dual']:.0f} kW")
        if S["vil_res"]:
            out.append(k["Village DG system"])
            out.append(f"renewable {k['Village renewable (%)']} %")
        out.append(f"EDF {k['EDF option / subscription']}")
        return out
    if node == "ski":
        h = net.get("harm")
        out = [f"T2 {k['T2 ski']}", f"peak {k['Ski peak (kW)']} kW"]
        if h:
            out.append(f"Lift 2: ATV66{h['drive']['model']} + {h['motor']['P_kW']} kW")
            out.append(f"filter {h['Q_filter']:.0f} kvar, THDv {h['thd_v1']:.2f} %")
        else:
            out.append("lifts: 2 x slip-ring 65 kW")
        if S["ev_ski"]:
            out.append(f"EV {p['ski.ev_dual']:.0f} kW")
        return out
    if node == "eco":
        e = run.get("eco")
        if not (S["eco"] and e):
            return ["not built in this year"]
        out = []
        if "iso" in e:
            out += ["isolated: " + e["iso"]["best"]["label"], f"   NPC {e['iso']['best']['NPC'] / 1e6:.2f} MEUR"]
        if "grid" in e:
            out += ["grid: " + e["grid"]["best"]["label"], f"   NPC {e['grid']['best']['NPC'] / 1e6:.2f} MEUR"]
        if e.get("decision"):
            out.append("cheaper: " + ("grid connection" if e["decision"] == "grid" else "isolated"))
        return out
    return []


def compact_lines(run, node):
    """Short text for the cards on the overview map (details go to the side panel)."""
    p, k, net, S = run["params"], run["kpi"], run["net"], run["setup"]
    if node == "source":
        return [f"Isc Q0 {net['isc']['Q0']:.2f} kA"]
    if node == "village":
        out = [f"T1 {k['T1 village']}, peak {k['Village peak (kW)']:.0f} kW"]
        if S["vil_res"]:
            out.append(f"{k['Village DG system']} ({k['Village renewable (%)']:.0f} % RES)")
        return out
    if node == "ski":
        h = net.get("harm")
        out = [f"T2 {k['T2 ski']}, peak {k['Ski peak (kW)']:.0f} kW"]
        if h:
            out.append(f"Lift 2 ATV66{h['drive']['model']}, filter {h['Q_filter']:.0f} kvar")
        return out
    if node == "eco":
        e = run.get("eco")
        if not (S["eco"] and e):
            return ["not built in this year"]
        v = eco_variant(run)
        b = e[v]["best"]
        out = [("grid-connected: " if v == "grid" else "isolated: ") + b["label"],
               f"NPC {b['NPC'] / 1e6:.2f} MEUR"]
        other = "iso" if v == "grid" else "grid"
        if other in e:
            out[-1] += f"  (other variant {e[other]['best']['NPC'] / 1e6:.2f})"
        return out
    return []


def line_short(run, ln):
    p, net = run["params"], run["net"]
    if ln == "L0":
        return [f"{p['geo.L0_cond']}, {p['geo.L0_len']} km, dU {net['L0']['dU']:.2f} %"]
    if ln not in net:
        return ["not built"]
    L = net[ln]
    out = [f"{L['name']}, {p['geo.' + ln + '_len']} km, dU {L['dU_cum']:.2f} %"]
    if ln == "L2" and run.get("eco") and run["eco"].get("decision"):
        out.append(f"break-even {run['eco']['breakeven_km']:.1f} km")
    return out


def line_lines(run, ln):
    p = run["params"]
    net = run["net"]
    if ln == "L0":
        L = net["L0"]
        return [f"{p['geo.L0_cond']}, {p['geo.L0_len']} km", f"dU {L['dU']:.2f} %, I {L['I_des']:.0f} A"]
    if ln not in net:
        return ["not built" if ln == "L2" and run["setup"]["eco"] else "-"]
    L = net[ln]
    out = [f"{L['name']} ({L['type']}), {p['geo.' + ln + '_len']} km", f"dU cum. {L['dU_cum']:.2f} %"]
    if ln == "L2" and run.get("eco") and run["eco"].get("decision"):
        e = run["eco"]
        out.append(f"break-even {e['breakeven_km']:.1f} km -> " + ("connect" if e["decision"] == "grid" else "isolated"))
    return out


def eco_variant(run):
    e = run.get("eco") or {}
    return e.get("decision") or ("iso" if "iso" in e else "grid")


def node_items(run, node):
    """Equipment shown on the map when a block is opened:
    list of dict(key, kind, lines, status, els)."""
    p = run["params"]
    E = run["net"]["elements"]
    S = run["setup"]
    els = E.get(node, [])
    by = {e["name"]: e for e in els}

    def find(pred):
        return [e for e in els if pred(e)]

    out = []

    def add(key, kind, lines, found, status=""):
        st = status or ("FAIL" if any(e.get("status") == "FAIL" for e in found) else "")
        out.append(dict(key=key, kind=kind, lines=lines, els=found, status=st))

    if node == "source":
        add("src", "sub", ["HV/MV substation", "T0 63/20 kV, " + by.get("CB Q0", {}).get("rating", "")],
            find(lambda e: True))
    elif node == "village":
        sub = find(lambda e: e["name"].startswith("T1") or e["name"] in ("CB Q1", "CB Q2", "CB F1 feeder breaker"))
        t1 = by.get(next((n for n in by if n.startswith("T1")), ""), {})
        add("vil_sub", "sub", ["Village substation", f"T1 {t1.get('rating', '')}"], sub)
        add("vil_c1", "load", ["Cluster 1", f"{p['vil.n6']} x 6 kVA"], [])
        add("vil_c2", "load", ["Cluster 2", f"{p['vil.n9']} x 9 kVA"], [])
        add("vil_c3", "load", ["Cluster 3", f"{p['vil.n12']} x 12 kVA"], [])
        add("vil_mun", "load", ["Town hall + water tower", f"{p['vil.S_mun']:.0f} kVA"], [])
        add("vil_saw", "motor", ["Sawmill", f"{p['vil.S_saw']:.0f} kVA"], [])
        if S["ev_village"]:
            ev = find(lambda e: e["name"] == "EV chargers")
            add("vil_evf", "ev", ["Fast charger", f"{p['vil.ev_fast']:.0f} kW"], ev)
            add("vil_evd", "ev", ["Dual charger", f"2 x {p['vil.ev_dual'] / 2:.0f} kW"], ev)
        pv = find(lambda e: e["name"] in ("PV array", "PV plant step-up"))
        if pv:
            add("vil_pv", "gen", ["PV plant"] + [e["rating"] for e in pv], pv)
        hy = find(lambda e: e["kind"] == "hydro turbine" or e["name"] == "River hydro step-up")
        if hy:
            add("vil_hyd", "gen", ["River hydro"] + [e["rating"] for e in hy], hy)
        bio = find(lambda e: e["name"].startswith("Biogas"))
        if bio:
            add("vil_bio", "gen", ["Biogas CHP"] + [e["rating"] for e in bio], bio)
        bat = find(lambda e: e["kind"] == "storage")
        if bat:
            add("vil_bat", "bat", ["Battery"] + [e["rating"] for e in bat], bat)
    elif node == "ski":
        sub = find(lambda e: e["kind"].startswith("transformer") or e["name"] in ("CB Q3", "CB Q4", "CB Q4b"))
        add("ski_sub", "sub", ["Ski substation"] + [f"{e['name'].split(' ')[0]} {e['rating']}" for e in sub
                                                    if e["kind"].startswith("transformer")], sub)
        add("ski_l1", "motor", ["Chairlift 1", "slip-ring " + by.get("Lift 1 (slip-ring)", {}).get("rating", "")],
            find(lambda e: e["name"].startswith("Lift 1")))
        l2 = find(lambda e: e["name"].startswith("Lift 2") or e["kind"] in ("variable speed drive", "filter"))
        if S["lift2_vfd"]:
            mot = by.get("Lift 2 motor", {})
            drv = next((e for e in l2 if e["kind"] == "variable speed drive"), {})
            flt = next((e for e in l2 if e["kind"] == "filter"), None)
            lines = ["Chairlift 2", f"{mot.get('rating', '')} + {drv.get('name', '')}"]
            if flt:
                lines.append("filter " + flt["rating"].split(",")[0])
            add("ski_l2", "motor", lines, l2)
        else:
            add("ski_l2", "motor", ["Chairlift 2", f"slip-ring {p['ski.motor_kw']:.0f} kW"], l2)
        ap = find(lambda e: e["name"].startswith("Apartments"))
        add("ski_rest", "load", ["Restaurant / office", f"{p['ski.n12']} x 12 kVA"], ap)
        add("ski_apt", "load", ["Apartments", f"{p['ski.n3']} x 3 kVA"], ap)
        if S["ev_ski"]:
            add("ski_ev", "ev", ["Dual charger", f"{p['ski.ev_dual']:.0f} kW"], find(lambda e: e["name"] == "EV dual charger"))
    elif node == "eco":
        v = eco_variant(run)
        pre = "isolated: " if v == "iso" else "grid: "
        gen = [e for e in els if e["name"].startswith(pre)]
        if v == "grid":
            sub = find(lambda e: e["name"] in ("T3", "CB Q5", "CB Q6"))
            add("eco_sub", "sub", ["Eco substation", "T3 " + by.get("T3", {}).get("rating", "")], sub)
        else:
            add("eco_sub", "sub", ["Microgrid controller", "isolated 400 V bus"], [])
        dw = find(lambda e: e["name"].startswith("Dwellings"))
        add("eco_c6", "load", ["Dwellings", f"{p['eco.n6']} x 6 kVA"], dw)
        add("eco_c9", "load", ["Dwellings", f"{p['eco.n9']} x 9 kVA"], dw)
        add("eco_c3", "load", ["Dwellings", f"{p['eco.n3']} x 3 kVA"], dw)
        for key, kind, pred, title in (
                ("eco_pv", "gen", lambda e: "PV" in e["name"], "PV"),
                ("eco_hyd", "gen", lambda e: e["kind"] == "hydro turbine", "Stream hydro"),
                ("eco_bio", "gen", lambda e: "Biogas" in e["name"], "Biogas CHP"),
                ("eco_bat", "bat", lambda e: e["kind"] == "storage", "Battery"),
                ("eco_wind", "gen", lambda e: "Wind" in e["name"], "Wind")):
            f = [e for e in gen if pred(e)]
            if f:
                add(key, kind, [title] + [e["rating"] for e in f], [dict(e, name=e["name"][len(pre):]) for e in f])
    return out


# ------------------------------------------------------------ geo map view
class GeoMap:
    """Real map with the network drawn on it."""

    def __init__(self, parent, page):
        self.page = page
        self.frame = tk.Frame(parent)
        self.mode = "overview"
        self.imgs = []
        self.map = CachedMapView(self.frame, corner_radius=0)
        self.map.pack(fill="both", expand=True)
        self.set_tiles("Google map")
        self.map.set_position(45.18, 5.56)
        self.map.set_zoom(13)

    def set_tiles(self, name):
        url, mz = TILES[name]
        self.map.set_tile_server(url, max_zoom=mz)

    def _img(self, pil):
        t = ImageTk.PhotoImage(pil)
        self.imgs.append(t)
        return t

    def clear(self):
        self.map.delete_all_marker()
        self.map.delete_all_path()
        self.imgs = []

    def fit(self, pts, pad=0.25):
        la = [a for a, _ in pts]
        lo = [b for _, b in pts]
        dla = max(max(la) - min(la), 0.004) * pad
        dlo = max(max(lo) - min(lo), 0.006) * pad + (0.004 if pad > 0.2 else 0)
        self.map.fit_bounding_box((max(la) + dla, min(lo) - dlo), (min(la) - dla, max(lo) + dlo))

    def _path(self, pts, color, width, cmd=None):
        if len(pts) >= 2:
            self.map.set_path(pts, color=color, width=width, command=cmd)

    def draw_lines(self, run, faded=False):
        p = run["params"] if run else self.page.app.params
        for ln in ("L0", "L1", "L2"):
            pts = route(p, ln)
            if ln == "L2" and not (run and run["setup"]["eco"]):
                continue
            active = (not run) or ln == "L0" or ln in run["net"]
            if ln == "L2" and run and run.get("eco") and run["eco"].get("decision") == "iso":
                active = False
            st = node_status(run, ln) if run and active else ""
            col = RED if st == "FAIL" else (BLUE if active else GREY_L)
            self._path(pts, col if not faded else GREY_L, 5 if active else 3,
                       cmd=lambda *_a, n=ln: self.page.select("line", n))
            if not faded and run:
                lab = {"L0": 0.5, "L1": 0.55, "L2": 0.5}[ln]
                pos = point_at(pts, lab)
                im = card(ln, line_short(run, ln), st, faded=not active)
                anchor = {"L0": "w", "L1": "w", "L2": "ne"}[ln]
                self.map.set_marker(pos[0], pos[1], icon=self._img(im), icon_anchor=anchor,
                                    command=lambda *_a, n=ln: self.page.select("line", n))

    def overview(self):
        run = self.page.app.current
        p = run["params"] if run else self.page.app.params
        self.mode = "overview"
        self.clear()
        st = sites(p)
        self.draw_lines(run)
        anchors = {"source": ("src", "e"), "village": ("vil_sub", "se"), "ski": ("ski_sub", "e"),
                   "eco": ("eco_sub", "nw")}
        for node, (key, anc) in anchors.items():
            la, lo = st[key]["pos"]
            if run:
                lines = compact_lines(run, node)
                faded = node == "eco" and not run["setup"]["eco"]
                im = card(TITLE[node], lines, "" if faded else node_status(run, node), faded)
            else:
                im = card(TITLE[node], ["press Calculate"])
            cmd = (lambda *_a, n=node: self.open_node(n))
            self.map.set_marker(la, lo, icon=self._img(symbol("dot")), command=cmd)
            self.map.set_marker(la, lo, icon=self._img(im), icon_anchor=anc, command=cmd)
        pts = [st[k]["pos"] for k in ("src", "vil_sub", "ski_sub", "eco_sub")]
        self.fit(pts, 0.15)

    def open_node(self, node):
        run = self.page.app.current
        self.mode = node
        self.page.select("node", node)
        if not run:
            return
        p = run["params"]
        st = sites(p)
        self.clear()
        self.draw_lines(run, faded=True)
        items = node_items(run, node)
        hub = items[0]["key"]
        hpos = st[hub]["pos"]
        pts = [hpos]
        # links from the substation (LV) - plants connect at MV via their step-up
        for it in items[1:]:
            if it["key"] not in st:
                continue
            pos = st[it["key"]]["pos"]
            mv = it["kind"] == "gen" and node == "village"
            self._path([hpos, pos], BLUE if mv else "#555555", 3 if mv else 2,
                       cmd=lambda *_a, i=it: self.page.select("item", node, i))
        if node == "village":
            self.draw_feeder(run)
        for it in items[1:] + items[:1]:
            if it["key"] not in st:
                continue
            la, lo = st[it["key"]]["pos"]
            pts.append((la, lo))
            left = it is not items[0] and lo < hpos[1] - 0.0008
            one = [it["lines"][0] + "  " + it["lines"][1]] if len(it["lines"]) > 1 else it["lines"]
            if it is items[0]:
                icon, anc = label_above(it["kind"], one, it["status"]), "s"
            else:
                icon, anc = label_icon(it["kind"], one, it["status"], left), ("e" if left else "w")
            self.map.set_marker(la, lo, icon=self._img(icon),
                                icon_anchor=anc, command=lambda *_a, i=it: self.page.select("item", node, i))
        self.fit(pts, 0.22)

    def draw_feeder(self, run):
        p = run["params"]
        fd = run["net"].get("feeder")
        pts = route(p, "LVF")
        if not fd or len(pts) < 2:
            return
        st = "FAIL" if not fd["cable"]["feasible"] else ""
        info = dict(key="LVF", kind="load", status=st,
                    lines=["LV feeder F1", f"{fd['cable']['name']}, {fd['L']:.0f} m",
                           f"{fd['N']} houses, dU {fd['cable']['dU']:.2f} %"],
                    els=[e for e in run["net"]["elements"]["village"]
                         if e["name"].startswith(("LV feeder", "CB F1", "House"))])
        cmd = (lambda *_a: self.page.select("item", "village", info))
        self._path(pts, RED if st else ORANGE, 4, cmd=cmd)
        houses = p.table("lvf_houses")
        hi = self._img(symbol("house_s"))
        if houses:   # real buildings, each with its service cable to the street
            for h in houses:
                self._path([(h["tap_lat"], h["tap_lon"]), (h["lat"], h["lon"])], RED if st else ORANGE, 1, cmd=cmd)
            for h in houses:
                self.map.set_marker(h["lat"], h["lon"], icon=hi, command=cmd)
        else:
            x0 = p["lvf.start"]
            N = fd["N"]
            for i in range(N):
                f = x0 + (1 - x0) * i / max(1, N - 1)
                la, lo = point_at(pts, f)
                self.map.set_marker(la, lo, icon=hi, command=cmd)
        end = pts[-1]
        self.map.set_marker(end[0], end[1], icon=self._img(label_icon("house", [info["lines"][0] + "  " + info["lines"][1]], st)),
                            icon_anchor="w", command=cmd)


# ------------------------------------------------------------ schematic
class Scheme:
    """Schematic map (no internet needed). Layout follows the real geography:
    ski resort north-east up the D218, eco-district east, source south-east."""

    POS = dict(source=(0.66, 0.88), village=(0.22, 0.62), ski=(0.72, 0.14), eco=(0.80, 0.52))

    def __init__(self, parent, page):
        self.page = page
        self.frame = tk.Frame(parent, background="white")
        self.cv = tk.Canvas(self.frame, background="white", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.f_t = tkfont.Font(family="Helvetica", size=12, weight="bold")
        self.f_l = tkfont.Font(family="Helvetica", size=10)

    def overview(self):
        self.draw()

    def open_node(self, node):
        self.page.select("node", node)

    def draw(self):
        c = self.cv
        c.delete("all")
        W, H = max(c.winfo_width(), 600), max(c.winfo_height(), 400)
        run = self.page.app.current
        pos = {k: (x * W, y * H) for k, (x, y) in self.POS.items()}
        # landscape hints
        c.create_line(0.24 * W, 0.66 * H, 0.40 * W, 0.50 * H, 0.60 * W, 0.30 * H, 0.74 * W, 0.14 * H,
                      fill="#d0d0d0", width=6, smooth=True)
        c.create_text(0.47 * W, 0.37 * H, text="D218", fill="#a0a0a0", font=("Helvetica", 9))
        c.create_line(0.02 * W, 0.80 * H, 0.40 * W, 0.74 * H, 0.98 * W, 0.70 * H, fill="#9ec5e8", width=3,
                      smooth=True)
        c.create_text(0.06 * W, 0.78 * H, text="Le Meaudret", anchor="sw", fill="#7aa6cf", font=("Helvetica", 9))
        c.create_text(0.74 * W, 0.04 * H, text="alt. ~1450 m", fill="#999999", font=("Helvetica", 9))
        c.create_text(0.24 * W, 0.94 * H, text="alt. ~1050 m", fill="#999999", font=("Helvetica", 9))
        boxes = {}
        nodes = ("source", "village", "ski", "eco")
        for n in nodes:   # measure boxes first so lines stop at their border
            lines = compact_lines(run, n) if run else ["press Calculate"]
            w = max([self.f_t.measure(TITLE[n]) + 34] + [self.f_l.measure(t) for t in lines]) + 20
            h = 30 + 16 * len(lines) + 4
            boxes[n] = (lines, w, h)
        self.rects = []
        self.on_top = []
        for n in nodes:
            lines, w, h = boxes[n]
            x0 = min(max(pos[n][0] - w / 2, 6), W - w - 6)
            self.rects.append((x0 - 6, pos[n][1] - h / 2 - 6, x0 + w + 6, pos[n][1] + h / 2 + 6))
        for ln, a, b in (("L0", "source", "village"), ("L1", "village", "ski"), ("L2", "village", "eco")):
            if ln == "L2" and not (run and run["setup"]["eco"]):
                continue
            self._line(ln, pos[a], pos[b], run)
        for n in nodes:
            self._node(n, pos[n], boxes[n], run)
        for tag in self.on_top:
            c.tag_raise(tag)
        S = self.page.app.setup
        from .params import YEARS
        c.create_text(12, 10, text=YEARS[S["year"]]["title"], anchor="nw", font=("Helvetica", 14, "bold"),
                      fill=INK)

    def _bind(self, tag, cmd):
        c = self.cv
        c.tag_bind(tag, "<Button-1>", lambda e: cmd())
        c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))

    def _line(self, ln, a, b, run):
        c = self.cv
        active = (not run) or ln == "L0" or ln in run["net"]
        if ln == "L2" and run and run.get("eco") and run["eco"].get("decision") == "iso":
            active = False
        st = node_status(run, ln) if run and active else ""
        col = RED if st == "FAIL" else (INK if active else "#bbbbbb")
        typ = run["net"][ln]["type"] if run and ln in run["net"] and ln != "L0" else "OHL"
        tag = "line:" + ln
        c.create_line(*a, *b, width=3 if active else 2, fill=col,
                      dash=(8, 4) if typ == "UG" else (() if active else (3, 4)), tags=tag)
        c.create_line(*a, *b, width=18, fill="", tags=tag)
        lines = [ln] + (line_short(run, ln) if run else [])
        # label beside the line (perpendicular offset), moved along the line
        # until it does not cover a block
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = max((dx * dx + dy * dy) ** 0.5, 1)
        nx, ny = -dy / L, dx / L
        if nx < 0:
            nx, ny = -nx, -ny
        t = None
        for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
            for side in (1, -1):
                mx, my = a[0] + f * dx, a[1] + f * dy
                tx, ty = mx + side * nx * 14, my + side * ny * 14
                anc = ("w" if side > 0 else "e") if abs(nx) > 0.3 else ("n" if side > 0 else "s")
                if t:
                    c.delete(t)
                t = c.create_text(tx, ty, text="\n".join(lines), anchor=anc,
                                  font=("Helvetica", 9), fill=col, tags=tag, justify="left")
                x1, y1, x2, y2 = c.bbox(t)
                if not any(x1 < r[2] and x2 > r[0] and y1 < r[3] and y2 > r[1] for r in self.rects):
                    break
            else:
                continue
            break
        else:      # no free place (small window): keep the label above the blocks
            self.on_top.append(tag)
        self.rects.append(c.bbox(t))
        x1, y1, x2, y2 = c.bbox(t)
        r = c.create_rectangle(x1 - 4, y1 - 2, x2 + 4, y2 + 2, fill="white", outline="#dddddd", tags=tag)
        c.tag_lower(r, t)
        self._bind(tag, lambda: self.page.select("line", ln))

    def _node(self, n, xy, box, run):
        c = self.cv
        lines, w, h = box
        x, y = xy
        faded = bool(run) and n == "eco" and not run["setup"]["eco"]
        st = node_status(run, n) if run and not faded else ""
        tag = "node:" + n
        fg = "#aaaaaa" if faded else INK
        x0 = min(max(x - w / 2, 6), c.winfo_width() - w - 6)
        y0 = y - h / 2
        c.create_rectangle(x0, y0, x0 + w, y0 + h, fill="white", outline=fg, width=2, tags=tag)
        c.create_text(x0 + 10, y0 + 8, text=TITLE[n], anchor="nw", font=self.f_t, fill=fg, tags=tag)
        if st:
            c.create_rectangle(x0 + w - 18, y0 + 9, x0 + w - 8, y0 + 19, fill=GREEN if st == "OK" else RED,
                               outline="", tags=tag)
        for k, t in enumerate(lines):
            c.create_text(x0 + 10, y0 + 30 + 16 * k, text=t, anchor="nw", font=self.f_l,
                          fill="#aaaaaa" if faded else "#333333", tags=tag)
        self._bind(tag, lambda: self.page.select("node", n))


def route_lengths(p):
    return {ln: route_km(p, ln) for ln in ("L0", "L1", "L2", "LVF")}
