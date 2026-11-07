#!/usr/bin/env python3
"""Build alert_relay/data/spc_state_grid.json.

The box watcher uses a Census-derived grid that is not in this repo. This
generator fills the same role the SPC filter expects: postal-code keys, a
0.25 degree CONUS grid, 0.1 degree for Washington, plus at least one interior
point per state. Borders can disagree with the box grid by about one cell;
the woken routine still checks the SPC map.
"""
import json, os, sys

SRC = os.environ.get("STATES_GEOJSON", "/tmp/geo/us-states.json")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "spc_state_grid.json")

POSTAL = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Puerto Rico": "PR",
}


def _rings(geom):
    t = geom.get("type")
    c = geom.get("coordinates") or []
    if t == "Polygon":
        yield c
    elif t == "MultiPolygon":
        for poly in c:
            yield poly


def _in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def contains(geom, lat, lon):
    for poly in _rings(geom):
        if not poly or not poly[0]:
            continue
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def bbox(geom):
    xs, ys = [], []
    for poly in _rings(geom):
        for ring in poly:
            for x, y, *_ in ring:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def step_for(code):
    if code == "WA":
        return 0.1
    if code in ("AK",):
        return 0.5
    if code in ("DC", "RI", "DE", "CT"):
        return 0.05
    return 0.25


def interior_points(geom, step):
    x0, y0, x1, y1 = bbox(geom)
    pts = []
    lat = y0
    # Snap to the step so repeated builds are stable.
    lat = round(round(lat / step) * step, 4)
    if lat < y0:
        lat += step
    while lat <= y1 + 1e-9:
        lon = round(round(x0 / step) * step, 4)
        if lon < x0:
            lon += step
        while lon <= x1 + 1e-9:
            if contains(geom, lat, lon):
                pts.append([round(lat, 4), round(lon, 4)])
            lon = round(lon + step, 4)
        lat = round(lat + step, 4)
    if not pts:
        # Walk a finer lattice until one interior point appears.
        fine = min(step, 0.02)
        lat = y0
        while lat <= y1 and not pts:
            lon = x0
            while lon <= x1:
                if contains(geom, lat, lon):
                    pts.append([round(lat, 4), round(lon, 4)])
                    break
                lon += fine
            lat += fine
    return pts


def main():
    data = json.load(open(SRC))
    points = {}
    for feat in data["features"]:
        name = feat["properties"]["name"]
        code = POSTAL.get(name)
        if not code:
            print("skip unknown", name, file=sys.stderr)
            continue
        pts = interior_points(feat["geometry"], step_for(code))
        if not pts:
            print("NO POINTS", code, file=sys.stderr)
            return 1
        points[code] = pts
        print("%s %d" % (code, len(pts)))
    doc = {
        "points": points,
        "about": "0.25 deg CONUS, 0.1 deg WA, 0.5 deg AK, 0.05 deg for DC/RI/DE/CT. "
                 "Built because the box file spc_state_grid.json is not in source control. "
                 "Point-in-polygon uses the same ray cast as spc_quiet.py.",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print("wrote", OUT, "bytes", os.path.getsize(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
