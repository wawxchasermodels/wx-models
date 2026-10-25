#!/usr/bin/env python3
"""Build the Observations tab basemap (web/forecast/obs/basemap.json) from Natural Earth 1:10m (public domain).

  python tools/forecast/obs_basemap.py [out.json]

Layers: land, lakes, state/province lines, country borders, populated places (city labels) and state/province label points, clipped to western North America and the NE Pacific,
in two detail levels (lo for zoomed-out views, hi for zoomed-in). Coordinates are lon/lat x 1000 as integers.
Small-town labels come from GeoNames (cities500 + the Canada dump, CC BY 4.0, credit "GeoNames, geonames.org"), downloaded
once into ~/.cache/geonames and baked into the JSON; the site never calls GeoNames at runtime.
Run once; the output is a static file (about 1.2 MB) served with the site. Uses cartopy's Natural Earth downloader."""
import json, math, os, sys
from shapely.geometry import Point
from shapely.prepared import prep
import cartopy.io.shapereader as shp
from shapely.geometry import box, mapping
from shapely.ops import unary_union

BBOX = box(-180, 24, -88, 76)
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web", "forecast", "obs", "basemap.json")
TOL = {"lo": 0.03, "hi": 0.006}


def geoms(cat, name):
    return [g for g in shp.Reader(shp.natural_earth("10m", cat, name)).geometries() if g.intersects(BBOX)]


def densify(c, step=0.1):
    """Add points so no segment is longer than `step` degrees: straight lon/lat runs such as the 49th parallel must
    curve once projected (Lambert), instead of being drawn as one long straight chord."""
    out = [c[0]]
    for (x0, y0), (x1, y1) in zip(c, c[1:]):
        n = max(1, int(math.ceil(max(abs(x1 - x0), abs(y1 - y0)) / step)))
        out += [(x0 + (x1 - x0) * j / n, y0 + (y1 - y0) * j / n) for j in range(1, n + 1)]
    return out


def split_water(lines, land):
    """Split border lines into land and water runs (water runs are drawn dashed: Haro Strait, Boundary Pass, Juan de Fuca)."""
    pl = prep(land)
    out = {True: [], False: []}
    for c in lines:
        run, wet = [c[0]], None
        for a, b in zip(c, c[1:]):
            w = not pl.contains(Point((a[0] + b[0]) / 2e3, (a[1] + b[1]) / 2e3))
            if wet is not None and w != wet:
                out[wet].append(run); run = [a]
            run.append(b); wet = w
        if len(run) > 1: out[bool(wet)].append(run)
    return out


def rings(g, tol, polys):
    g = g.intersection(BBOX).simplify(tol, preserve_topology=polys)
    out = []
    parts = getattr(g, "geoms", [g])
    for p in parts:
        if p.is_empty: continue
        if p.geom_type == "Polygon":
            for r in [p.exterior] + list(p.interiors):
                c = [[round(x * 1000), round(y * 1000)] for x, y in r.coords]
                if len(c) >= 4: out.append(c)
        elif p.geom_type == "LineString":
            c = [[round(x * 1000), round(y * 1000)] for x, y in densify(list(p.coords))]
            if len(c) >= 2: out.append(c)
        elif hasattr(p, "geoms"):
            out += rings(p, 0, polys)
    return out


# label anchor points for the faint state/province names (hand-placed near each region's visual centre)
REGIONS = [
    ("Washington", "WA", -120.5, 47.4), ("Oregon", "OR", -120.6, 43.9), ("Idaho", "ID", -114.6, 44.2), ("Montana", "MT", -109.6, 47.0),
    ("California", "CA", -119.8, 37.6), ("Nevada", "NV", -116.9, 39.3), ("Utah", "UT", -111.6, 39.3), ("Wyoming", "WY", -107.5, 43.0),
    ("Arizona", "AZ", -111.7, 34.3), ("Colorado", "CO", -105.5, 39.0), ("New Mexico", "NM", -106.1, 34.4), ("Alaska", "AK", -151.0, 64.5),
    ("North Dakota", "ND", -100.4, 47.4), ("South Dakota", "SD", -100.2, 44.4), ("Nebraska", "NE", -99.8, 41.5),
    ("British Columbia", "BC", -124.5, 54.0), ("Alberta", "AB", -114.5, 55.0), ("Saskatchewan", "SK", -105.9, 54.5),
    ("Yukon", "YT", -135.5, 63.5), ("Northwest Territories", "NT", -119.0, 64.0), ("Manitoba", "MB", -97.5, 55.0),
]


def places():
    out = []
    for r in shp.Reader(shp.natural_earth("10m", "cultural", "populated_places_simple")).records():
        g, a = r.geometry, r.attributes
        if BBOX.contains(g) and a["adm0_a3"] in ("USA", "CAN", "MEX"):
            out.append([a["name"], round(g.x, 3), round(g.y, 3), int(a["scalerank"]), int(a["pop_max"])])
    return sorted(out, key=lambda p: (p[3], -p[4]))


GN = "https://download.geonames.org/export/dump/"
GN_CACHE = os.path.expanduser("~/.cache/geonames")
US_STATES = {"WA", "OR", "ID", "MT", "CA", "NV", "UT", "WY", "AK"}
CA_PROV = {"01", "02", "11", "12", "13"}          # Alberta, British Columbia, Saskatchewan, Yukon, Northwest Territories
SKIP_IDS = {"5771312"}   # GeoNames ids left out on purpose (names that clash with the site's own wording rules)
PPL_OK = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLS", "PPLL", "PPLF"}


def gn_rows(name, member):
    import io, urllib.request, zipfile
    os.makedirs(GN_CACHE, exist_ok=True)
    z = os.path.join(GN_CACHE, name)
    if not os.path.exists(z):
        urllib.request.urlretrieve(GN + name, z)
    with zipfile.ZipFile(z) as zf, zf.open(member) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            yield line.rstrip("\n").split("\t")


def towns(nat):
    """GeoNames populated places in the obs domain: [name, lon, lat, pop]. Places with no population are kept only in
    sparse areas (no populated place within 8 km), so remote coasts such as northern Vancouver Island still get names."""
    keep = {}
    def ok(r):
        return r[0] not in SKIP_IDS and r[6] == "P" and r[7] in PPL_OK and ((r[8] == "US" and r[10] in US_STATES) or (r[8] == "CA" and r[10] in CA_PROV))
    for r in gn_rows("cities500.zip", "cities500.txt"):
        if ok(r): keep[r[0]] = [r[1], float(r[5]), float(r[4]), int(r[14] or 0)]
    zero = []
    for r in gn_rows("CA.zip", "CA.txt"):
        if ok(r) and r[0] not in keep:
            if int(r[14] or 0): keep[r[0]] = [r[1], float(r[5]), float(r[4]), int(r[14])]
            else: zero.append([r[1], float(r[5]), float(r[4]), 0])
    pts = list(keep.values())
    cell = {}
    for p in pts: cell.setdefault((int(p[1] * 5), int(p[2] * 10)), []).append(p)
    def near(p, km):
        i, j = int(p[1] * 5), int(p[2] * 10)
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                for q in cell.get((i + a, j + b), []):
                    if math.hypot((q[1] - p[1]) * 111 * math.cos(math.radians(p[2])), (q[2] - p[2]) * 111) < km: return True
        return False
    sparse = [z for z in zero if not near(z, 8)]
    # drop duplicates of the Natural Earth cities (same place, already labelled in the bigger style)
    def dup(p):
        return any((abs(c[1] - p[1]) < 0.06 and abs(c[2] - p[2]) < 0.04) or (c[0] == p[0] and abs(c[1] - p[1]) < 0.3 and abs(c[2] - p[2]) < 0.2) for c in nat)
    def junk(n):   # administrative areas, census-designated compounds and camp names that read badly as town labels
        return any(w in n for w in ("Trust Area", "Headquarters", "Reserve", " Camp", "(historical)")) or ("-" in n and " " in n)
    out = [[p[0], round(p[1], 3), round(p[2], 3), p[3]] for p in pts + sparse
           if BBOX.contains(Point(p[1], p[2])) and not dup(p) and not junk(p[0])]
    return sorted(out, key=lambda p: -p[3])


def main():
    land = unary_union(geoms("physical", "land"))
    lakes = [g for g in geoms("physical", "lakes") if g.area > 0.02]
    states = geoms("cultural", "admin_1_states_provinces_lines")
    borders = geoms("cultural", "admin_0_boundary_lines_land")
    nat = places()
    res = {"credit": "Basemap: Natural Earth (public domain). Town names: GeoNames (CC BY 4.0)", "scale": 1000, "places": nat, "towns": towns(nat),
           "regions": [list(r) for r in REGIONS]}
    for lod, tol in TOL.items():
        res[lod] = {
            "land": rings(land, tol, True),
            "lakes": sum((rings(g, tol, True) for g in lakes if g.area > (0.02 if lod == "hi" else 0.15)), []),
            "states": sum((rings(g, tol, False) for g in states), []),
        }
        bw = split_water(sum((rings(g, tol, False) for g in borders), []), land)
        res[lod]["borders"], res[lod]["borders_sea"] = bw[False], bw[True]
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    json.dump(res, open(OUT, "w"), separators=(",", ":"))
    print(OUT, os.path.getsize(OUT), "bytes", {k: {l: len(v) for l, v in res[k].items()} for k in TOL}, len(res["places"]), "places", len(res["towns"]), "towns")


if __name__ == "__main__":
    main()
