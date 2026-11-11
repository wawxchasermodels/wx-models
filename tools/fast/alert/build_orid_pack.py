#!/usr/bin/env python3
"""Fetch NWS geometries for the OR/ID alert extension and merge them into the site alert pack."""
from __future__ import annotations
import json, sys, time, urllib.request
from pathlib import Path

from shapely.geometry import mapping, shape

HERE = Path(__file__).resolve().parent
SITE = HERE.parent / "site" / "alert"
sys.path.insert(0, str(HERE))
from orid_zones import all_new_zone_ids, county_ids, NEW_TOWNS

UA = "WAWeatherChasersStudio/1.0 (alerts; benjamin@wawxchasers)"
TOL = 0.004  # degrees; matches the existing pack's roughly-hundreds-of-points density


def fetch_zone(zid: str) -> dict:
    kind = "county" if zid[2] == "C" else "forecast"
    url = f"https://api.weather.gov/zones/{kind}/{zid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


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


def simplify_geom(g, tol=TOL):
    if not g:
        return None
    s = shape(g)
    if s.is_empty:
        return None
    if not s.is_valid:
        s = s.buffer(0)
    s2 = s.simplify(tol, preserve_topology=True)
    if s2.is_empty or s2.area == 0:
        s2 = s
    # Drop Z if present
    gj = mapping(s2)
    return json.loads(json.dumps(gj))


def feature_from_nws(doc: dict, zid: str) -> dict:
    props = doc.get("properties") or {}
    geom = simplify_geom(doc.get("geometry"))
    if not geom:
        raise RuntimeError(f"no geometry for {zid}")
    name = props.get("name") or zid
    state = props.get("state") or (zid[:2] if not zid.startswith("PZZ") else "PZ")
    return {
        "type": "Feature",
        "id": zid,
        "properties": {"id": zid, "name": name, "state": state},
        "geometry": geom,
    }


def main():
    ids = all_new_zone_ids()
    zones_path = SITE / "zones_wa.json"
    pack = json.loads(zones_path.read_text())
    have = {f.get("id") or (f.get("properties") or {}).get("id") for f in pack["features"]}
    added = []
    county_geoms = []
    wanted_county = {c[0] for c in county_ids()}
    for i, zid in enumerate(ids):
        if zid in have:
            print(f"  skip existing {zid}")
            # still collect county outline if we already have it
            if zid in wanted_county:
                feat = next(f for f in pack["features"] if (f.get("id") or f["properties"]["id"]) == zid)
                county_geoms.append(feat["geometry"])
            continue
        last_err = None
        for attempt in range(3):
            try:
                doc = fetch_zone(zid)
                feat = feature_from_nws(doc, zid)
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        if last_err:
            raise SystemExit(f"failed {zid}: {last_err}")
        pack["features"].append(feat)
        have.add(zid)
        added.append((zid, ncoords(feat["geometry"]), feat["properties"]["name"]))
        if zid in wanted_county:
            county_geoms.append(feat["geometry"])
        print(f"  + {zid:8} {added[-1][1]:4d} pts  {added[-1][2]}")
        time.sleep(0.12)
    zones_path.write_text(json.dumps(pack, separators=(",", ":")))
    print(f"zones_wa.json now {len(pack['features'])} features, added {len(added)}")

    bm_path = SITE / "basemap_wa.json"
    bm = json.loads(bm_path.read_text())
    # Avoid duplicating county outlines if we re-run: tag by packing only new ones
    # Existing 39 are WA. Append the new OR/ID county geoms.
    before = len(bm["counties"])
    # If a previous run already appended, don't double: detect by count or bbox south of 45.4
    def south(g):
        ys = []
        def w(c):
            if c and isinstance(c[0], (int, float)):
                ys.append(c[1])
            else:
                for x in c: w(x)
        w(g.get("coordinates"))
        return min(ys) if ys else 90
    existing_south = [south(g) for g in bm["counties"]]
    # WA counties all have min lat >= ~45.54 except maybe not. Don't use that.
    # Just replace extras beyond 39 with the new set.
    bm["counties"] = bm["counties"][:39] + county_geoms
    bm_path.write_text(json.dumps(bm, separators=(",", ":")))
    print(f"basemap counties {before} -> {len(bm['counties'])} (kept 39 WA + {len(county_geoms)} OR/ID)")

    tw_path = SITE / "towns_wa.json"
    tw = json.loads(tw_path.read_text())
    have_n = {p["n"] for p in tw["places"]}
    n_add = 0
    for rec in NEW_TOWNS:
        if rec["n"] in have_n:
            print(f"  town exists {rec['n']}")
            continue
        tw["places"].append(rec)
        have_n.add(rec["n"]); n_add += 1
    tw_path.write_text(json.dumps(tw, separators=(",", ":")))
    print(f"towns added {n_add}, total {len(tw['places'])}")
    print("ok")


if __name__ == "__main__":
    main()
