#!/usr/bin/env python3
"""Triple-check of the coastal flood levels drawn on the Tides chart (Benjamin t3044u + steering, 2026-11-14).

For every data station in tide.js STATIONS and every level (minor, moderate, major) three independent NOAA sources:
  S1  CO-OPS metadata API  mdapi/stations/<id>.json?expand=floodlevels  (nws_* and nos_*, station datum STND)
      converted to MLLW with mdapi/stations/<id>/datums.json
  S2  NOAA Tides & Currents Coastal Inundation Dashboard threshold file  tidesandcurrents.noaa.gov/inundationdb/data/NOSfloodlevels.json
      (minor/moderate/major = the NWS thresholds the dashboard shows; nos_minor = NOS derived), converted with ITS OWN datum_mllw
  S3  NWS National Water Prediction Service gauge  api.water.noaa.gov/nwps/v1/gauges/<SHEF id>  flood categories, converted
      to MLLW with datums.json when they are given above MHHW (or another datum datums.json has)
A level is DRAWN only when it is the NWS (official) value, S1 and S2 agree within 0.05 ft, and S3 agrees too or has no
categories for that gauge (most WA tide gauges are not NWPS gauges). Any disagreement = not drawn + flagged.
NOS derived thresholds (Sweet et al. 2018, NOS CO-OPS 086) are not official flood stages and are listed for information only.
Usage: flood_verify.py [--json out.json] [--md out.md] [--tidejs path/to/tide.js]  (with --tidejs: exit 1 if the table
embedded in tide.js differs from the live triple-check or draws a level that is not verified)
"""
import json, re, sys, urllib.error, urllib.request
TOL = 0.05
LV = ("minor", "moderate", "major")
MD = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/"
S2URL = "https://tidesandcurrents.noaa.gov/inundationdb/data/NOSfloodlevels.json"
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges/"

def get(u):
    rq = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 wx_models_tide_flood_verify"})
    return json.load(urllib.request.urlopen(rq, timeout=40))

def r2(x): return None if x is None else round(x, 2)

def stations_from_tidejs(path):
    src = open(path).read()
    m = re.search(r"const STATIONS = \[(.*?)\];", src, re.S)
    out = []
    for sid, name in re.findall(r'\["([0-9a-z]+)", "([^"]+)"', m.group(1)):
        out.append((sid, name))
    alias = dict(re.findall(r'"([a-z]+)": "(\d{7})"', (re.search(r"const ALIAS = \{(.*?)\};", src, re.S) or [None, ""])[1]))
    table = json.loads(re.search(r"const FLOOD = (\{.*?\});", src, re.S).group(1)) if "const FLOOD = " in src else {}
    return out, alias, table

def check(ids):
    s2 = {s["id"]: s for s in get(S2URL)["stations"]}
    rows = {}
    for sid in ids:
        r = {"id": sid, "levels": {}, "notes": []}
        m = get(f"{MD}{sid}.json?expand=floodlevels")["stations"][0]
        dj = {d["name"]: d["value"] for d in get(f"{MD}{sid}/datums.json").get("datums", [])}
        mllw = dj.get("MLLW"); fl = m.get("floodlevels") or {}
        r.update(name=m.get("name"), shef=m.get("shefcode") or "", mllw_stnd=mllw, mhhw_stnd=dj.get("MHHW"))
        e2 = s2.get(sid)
        f2 = {x["name"]: x["value"] for x in (e2 or {}).get("floodlevels", [])}
        if e2 and mllw is not None and e2.get("datum_mllw") is not None and abs(e2["datum_mllw"] - mllw) > 0.005:
            r["notes"].append(f"S2 datum_mllw {e2['datum_mllw']} != datums.json MLLW {mllw}")
        if not e2: r["notes"].append("station not in the Tides & Currents inundation dashboard file")
        cats, s3note = {}, ""
        if r["shef"]:
            try:
                g = get(NWPS + r["shef"])
                if "flood" in g:
                    vd = [(v.get("abbrev") or "").rstrip("*").upper() for v in (g.get("datums") or {}).get("vertical", {}).get("value", [])]
                    base = vd[0] if vd else ""
                    off = {"MHHW": dj.get("MHHW"), "MLLW": mllw, "MSL": dj.get("MSL"), "MHW": dj.get("MHW"), "NAVD88": dj.get("NAVD88")}.get(base)
                    for k in LV:
                        stg = (g["flood"]["categories"].get(k) or {}).get("stage")
                        if stg is not None and stg > -9000:
                            cats[k] = r2(stg + off - mllw) if off is not None and mllw is not None else "datum?"
                    s3note = f"NWPS {r['shef']} ({g.get('name')}), stages above {base or '?'}" + ("" if cats else ", no flood categories")
                else: s3note = f"NWPS: {r['shef']} is not an NWPS gauge"
            except urllib.error.HTTPError as ex: s3note = f"NWPS: {r['shef']} is not an NWPS gauge (HTTP {ex.code})" if ex.code in (400, 404) else f"NWPS {r['shef']}: unreachable (HTTP {ex.code})"
            except Exception as ex: s3note = f"NWPS {r['shef']}: unreachable ({type(ex).__name__})"; r["s3_down"] = True
        r["s3note"] = s3note
        for k in LV:
            nws = fl.get(f"nws_{k}"); nos = fl.get(f"nos_{k}")
            s1 = r2(nws - mllw) if nws is not None and mllw is not None else None
            s1nos = r2(nos - mllw) if nos is not None and mllw is not None else None
            s2v = r2(f2[k] - e2["datum_mllw"]) if e2 and f2.get(k) is not None and e2.get("datum_mllw") is not None else None
            s2nos = r2(f2[f"nos_{k}"] - e2["datum_mllw"]) if e2 and f2.get(f"nos_{k}") is not None else None
            s3 = cats.get(k)
            ok12 = s1 is not None and s2v is not None and abs(s1 - s2v) <= TOL
            ok3 = s3 is None or (isinstance(s3, float) and s1 is not None and abs(s1 - s3) <= TOL)
            if s1 is None and s2v is None and s3 is None: status = "none"
            elif ok12 and ok3: status = "verified 3/3" if s3 is not None else "verified 2/2 (no NWPS categories)"
            else: status = "MISMATCH"
            r["levels"][k] = {"s1_nws": s1, "s2": s2v, "s3": s3, "s1_nos": s1nos, "s2_nos": s2nos, "status": status,
                              "draw": s1 if status.startswith("verified") else None}
        rows[sid] = r
    return rows

def md_table(rows, names):
    L = ["| Station | Level | S1 mdapi NWS | S2 T&C dashboard | S3 NWS NWPS | Chart draws | Check | NOS derived (info, S1/S2) |", "|---|---|---|---|---|---|---|---|"]
    f = lambda v: "n/a" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))
    for key, name, sid in names:
        r = rows[sid]
        for k in LV:
            x = r["levels"][k]
            L.append(f"| {name} ({sid}) | {k} | {f(x['s1_nws'])} | {f(x['s2'])} | {f(x['s3'])} | {f(x['draw']) if x['draw'] is not None else 'not drawn'} | {x['status']} | {f(x['s1_nos'])} / {f(x['s2_nos'])} |")
    return "\n".join(L)

def main():
    a = sys.argv[1:]; opt = lambda k: a[a.index(k) + 1] if k in a else None
    tj = opt("--tidejs") or "/workspace/wx-models-site/tide_floodlines_mock_20261114/tools/fast/site/tide/tide.js"
    st, alias, table = stations_from_tidejs(tj)
    names = [(k, n, alias.get(k, k)) for k, n in st]
    rows = check(sorted({x[2] for x in names}))
    bad = []
    for sid, r in rows.items():
        for k in LV:
            want = r["levels"][k]["draw"]; have = (table.get(sid) or {}).get(k)
            if r["levels"][k]["status"] == "MISMATCH": bad.append(f"{sid} {k}: sources disagree {r['levels'][k]}")
            if (want is None) != (have is None) or (want is not None and abs(want - have) > TOL):
                bad.append(f"{sid} {k}: tide.js FLOOD table {have} but live triple-check says {want}")
    if opt("--json"): json.dump({"rows": rows, "bad": bad, "names": names}, open(opt("--json"), "w"), indent=1)
    if opt("--md"): open(opt("--md"), "w").write(md_table(rows, names) + "\n")
    for sid, r in rows.items(): print(sid, r["name"], r["shef"], "|", r["s3note"], "|", "; ".join(r["notes"]))
    print(md_table(rows, names))
    for b in bad: print("FAIL", b)
    print("flood_verify:", "FAILS " + str(len(bad)) if bad else "PASS")
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())
