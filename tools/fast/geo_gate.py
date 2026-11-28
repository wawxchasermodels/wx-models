#!/usr/bin/env python3
"""Ingestion alignment gate (11-28-26, Benjamin t3439u/t3440u: "WHY are the labels messed up again ... Make sure that NEVER happens").
Run by fast_cycle.publish_manifest before a run is listed in manifest.json, and usable by hand:
    geo_gate.py <manifest.json> <model> <run.json> ...
A run is only listed when
  1. its grid (run.json grid nx / ny) is exactly the model's manifest crop, so the data, the LUTs, the basemap and the town labels
     (all built for that crop) are on one frame (an older / other crop re-encode is what shifted maps off their coast and labels);
  2. on 0.25 deg / 0.1 deg lat/lon grids (90N origin, 0..360E), known towns' label slots in every view sit on their real lat/lon
     (within 0.3 deg), so a crop, origin or longitude-wrap change in the manifest cannot list misaligned maps.
Read-only. Returns a list of problems (empty = OK)."""
import json, re, sys

KNOWN = {"Seattle": (47.6062, -122.3321), "Portland": (45.5152, -122.6784), "Spokane": (47.6588, -117.4260), "Boise": (43.6150, -116.2023),
         "Victoria": (48.4284, -123.3656), "Medford": (42.3265, -122.8756), "Yakima": (46.6021, -120.5059), "Eugene": (44.0521, -123.0868)}
DEG_TOL = 0.3

def _res(M):
    if M.get("grid") != "ll": return None
    m = re.search(r"([\d.]+)\s*°", M.get("res") or "")
    r = float(m.group(1)) if m else None
    if r in (0.25, 0.1): return r
    if r == 0.5 and M.get("crop") and M["crop"][3] - M["crop"][2] == 864: return 0.25   # 0.5 deg members regridded onto the 0.25 frame
    return None

def check(man, model, run):
    probs = []
    M = (man.get("models") or {}).get(model)
    if not M: return probs   # model not in the manifest yet (static not published): nothing to compare
    crop, G = M.get("crop"), (run or {}).get("grid") or {}
    if crop and G and (G.get("nx"), G.get("ny")) != (crop[3] - crop[2], crop[1] - crop[0]):
        probs.append(f"{model} {run.get('cycle')}: run grid {G.get('nx')}x{G.get('ny')} is not the manifest crop {crop[3]-crop[2]}x{crop[1]-crop[0]}")
    res = _res(M)
    if res and crop:
        for vid, V in (M.get("views") or {}).items():
            for t in V.get("towns") or []:
                kn = KNOWN.get(t.get("name"))
                if not kn or t.get("fi") is None: continue
                ei, ej = (90 - kn[0]) / res - crop[0], ((kn[1] % 360) + 360) % 360 / res - crop[2]
                d = ((ei - t["fi"]) ** 2 + (ej - t["fj"]) ** 2) ** 0.5 * res
                if d > DEG_TOL: probs.append(f"{model} view {vid}: {t['name']} label slot is {d:.2f} deg from its real place")
    return probs

if __name__ == "__main__":
    man = json.load(open(sys.argv[1])); m = sys.argv[2]; bad = []
    for p in sys.argv[3:]: bad += check(man, m, json.load(open(p)))
    for b in bad: print("GEO GATE:", b)
    print("geo_gate:", "FAIL" if bad else "OK"); sys.exit(1 if bad else 0)
