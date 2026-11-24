"""Map geometry: positions of the equipment (team Google My Map) and line
routes. Distances use the haversine formula on the WGS84 sphere."""
import math

R_EARTH = 6371.0  # km


def dist_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def sites(p):
    """key -> dict(node, name, lat, lon, source)"""
    return {r["key"]: dict(r, pos=(float(r["lat"]), float(r["lon"]))) for r in p.table("sites")}


def route(p, line):
    return [(float(r["lat"]), float(r["lon"])) for r in p.table("routes") if r["line"] == line]


def route_km(p, line):
    pts = route(p, line)
    return sum(dist_km(a, b) for a, b in zip(pts, pts[1:]))


def point_at(pts, frac):
    """Point at a fraction of the polyline length (for houses along a feeder)."""
    seg = [dist_km(a, b) for a, b in zip(pts, pts[1:])]
    tot = sum(seg)
    if tot == 0:
        return pts[0]
    d = frac * tot
    for (a, b), s in zip(zip(pts, pts[1:]), seg):
        if d <= s or s == seg[-1]:
            t = 0 if s == 0 else min(1.0, d / s)
            return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
        d -= s
    return pts[-1]


def apply_map_lengths(p, log):
    """Log map route lengths; optionally use them as L1 / L2 lengths."""
    log.head("geo", "Line lengths: subject vs map routes")
    f = p["geo.route_factor"]
    for ln in ("L0", "L1", "L2"):
        km = route_km(p, ln) * f
        use = bool(p["geo.len_from_map"]) and ln != "L0"
        log.add("geo", f"{ln} route length on the map", "L = factor x sum haversine(P_i, P_i+1)", km, "km",
                status="used" if use else "info",
                note=f"subject / parameter value {p['geo.' + ln + '_len']} km")
        if use:
            p.set(f"geo.{ln}_len", round(km, 2))
