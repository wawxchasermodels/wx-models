#!/usr/bin/env python3
"""Add complete OR, ID, and MT county outlines (and a Montana land fill) to the
Studio Active Alerts basemap. Does not change the alert zone pack or filter.

Source: US Census Bureau 2024 cartographic boundaries, 1:500,000.
WA's original 39 county geoms are left untouched. Existing OR/ID context
land fills stay; Montana is appended so the state is filled and outlined
when someone pans or zooms out.
"""
from __future__ import annotations
import json, zipfile
from pathlib import Path

import shapefile
from shapely.geometry import mapping, shape

HERE = Path(__file__).resolve().parent
SITE = HERE.parent / "site" / "alert"
CACHE = Path("/tmp/census_cb")
TOL = 0.004  # degrees; matches the alert-pack builder
ND = 5
WANTED = {"OR": "41", "ID": "16", "MT": "30"}
WA_COUNTY_COUNT = 39
EXPECTED = {"OR": 36, "ID": 44, "MT": 56}


def round_geom(g, nd=ND):
    def r(c):
        if not c:
            return c
        if isinstance(c[0], (int, float)):
            return [round(float(c[0]), nd), round(float(c[1]), nd)]
        return [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def simplify_geom(g, tol=TOL):
    s = shape(g)
    if s.is_empty:
        return None
    if not s.is_valid:
        s = s.buffer(0)
    s2 = s.simplify(tol, preserve_topology=True)
    if s2.is_empty or s2.area == 0:
        s2 = s
    return round_geom(json.loads(json.dumps(mapping(s2))))


def ensure_unzip(zip_name: str, dest_name: str) -> Path:
    dest = CACHE / dest_name
    shp = next(dest.glob("*.shp"), None) if dest.exists() else None
    if shp:
        return shp
    zpath = CACHE / zip_name
    if not zpath.exists():
        raise SystemExit(f"missing {zpath}; download Census cartographic zip first")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest)
    shp = next(dest.glob("*.shp"))
    return shp


def load_counties():
    shp = ensure_unzip("cb_2024_us_county_500k.zip", "county500k")
    sf = shapefile.Reader(str(shp.with_suffix("")))
    out = {st: [] for st in WANTED}
    for sr in sf.iterShapeRecords():
        rec = sr.record.as_dict()
        st = rec.get("STUSPS")
        if st not in out:
            continue
        geom = simplify_geom(sr.shape.__geo_interface__)
        if not geom:
            raise RuntimeError(f"empty geometry for {st} {rec.get('NAME')}")
        out[st].append((rec.get("NAME") or "", rec.get("GEOID") or "", geom))
    for st, n in EXPECTED.items():
        if len(out[st]) != n:
            raise SystemExit(f"{st} county count {len(out[st])} != {n}")
        out[st].sort(key=lambda t: t[1])
    return out


def load_state(stusps: str):
    shp = ensure_unzip("cb_2024_us_state_500k.zip", "state500k")
    sf = shapefile.Reader(str(shp.with_suffix("")))
    for sr in sf.iterShapeRecords():
        rec = sr.record.as_dict()
        if rec.get("STUSPS") == stusps:
            geom = simplify_geom(sr.shape.__geo_interface__)
            if not geom:
                raise RuntimeError(f"empty state geometry for {stusps}")
            return geom
    raise SystemExit(f"state {stusps} not found")


def ncoords(g) -> int:
    n = 0
    def w(c):
        nonlocal n
        if c and isinstance(c[0], (int, float)):
            n += 1
        else:
            for x in c:
                w(x)
    if g:
        w(g.get("coordinates"))
    return n


def main():
    counties = load_counties()
    mt_state = load_state("MT")
    path = SITE / "basemap_wa.json"
    bm = json.loads(path.read_text())
    old = bm.get("counties") or []
    if len(old) < WA_COUNTY_COUNT:
        raise SystemExit(f"expected at least {WA_COUNTY_COUNT} WA counties, got {len(old)}")
    wa = old[:WA_COUNTY_COUNT]
    extra = []
    for st in ("OR", "ID", "MT"):
        extra.extend(g for _, _, g in counties[st])
    bm["counties"] = wa + extra
    ctx = list(bm.get("context") or [])
    # Keep OR, ID, BC as they are. Replace a previous MT append or add one.
    # Detect MT by bbox (eastern edge past -110).
    def is_mt(g):
        xs = []
        def w(c):
            if c and isinstance(c[0], (int, float)):
                xs.append(c[0])
            else:
                for x in c:
                    w(x)
        w((g or {}).get("coordinates"))
        return xs and min(xs) < -116.2 and max(xs) > -104.5
    ctx = [g for g in ctx if not is_mt(g)]
    ctx.append(mt_state)
    bm["context"] = ctx
    src = bm.get("source") or ""
    note = ("Washington, Oregon, Idaho and Montana: US Census Bureau 2024 "
            "cartographic boundaries, 1:500,000 (public domain), simplified. "
            "British Columbia: Natural Earth 10m (public domain), simplified. "
            "Oregon, Idaho and Montana show every county outline; only WA plus "
            "bordering OR/ID and the Oregon coast are in the alert zone pack. "
            "Shoreline is cartographic 1:500k, not a navigational coastline.")
    bm["source"] = note
    text = json.dumps(bm, separators=(",", ":"))
    path.write_text(text)
    pts = sum(ncoords(g) for g in bm["counties"])
    print(f"wrote {path} ({path.stat().st_size} bytes, "
          f"{len(wa)} WA + {len(extra)} OR/ID/MT counties, "
          f"{pts} county points, context {len(ctx)})")


if __name__ == "__main__":
    main()
