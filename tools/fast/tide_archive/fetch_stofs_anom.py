#!/usr/bin/env python3
"""Extract STOFS-2D-Global 5-day station bias correction (cwl minus cwl.noanomaly) at WA/OR tide stations.

Writes one small JSON per cycle under --out (default /tmp/sst_work/stofs_anom/). Used by the
Conditional v2 wind toggle so wind-off keeps the anomaly (applied once, same as c1) and only
removes the non-IB, non-anomaly part of STOFS.
"""
from __future__ import annotations
import argparse, datetime as D, json, os, sys, tempfile, urllib.request

S3 = "https://noaa-gestofs-pds.s3.amazonaws.com/"
STATIONS = ["9439040","9440910","9441102","9442396","9443090","9444090","9444900","9449880","9449424","9447130","9446484"]
UA = {"User-Agent": "wx-models-tides"}
OUT_DEFAULT = "/tmp/sst_work/stofs_anom"

def cycles(start, end):
    t = start
    out = []
    while t <= end:
        out.append(t)
        t += D.timedelta(hours=6)
    return out

def fetch(url, dest):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)

def extract(cycle, tmp):
    import netCDF4 as N, numpy as np
    tag = cycle.strftime("%Y%m%d/stofs_2d_glo.t%Hz.points.")
    paths = {}
    for suf in ("cwl.nc", "cwl.noanomaly.nc"):
        dest = os.path.join(tmp, suf)
        fetch(S3 + f"stofs_2d_glo.{tag}{suf}", dest)
        paths[suf] = dest
    fa = N.Dataset(paths["cwl.nc"])
    fb = N.Dataset(paths["cwl.noanomaly.nc"])
    try:
        nm = [str(s).strip() for s in N.chartostring(fa.variables["station_name"][:])]
        units = fa.variables["time"].units  # "seconds since YYYY-MM-DD HH:MM:SS"
        base_s = units.split("since", 1)[1].strip()
        base = D.datetime.strptime(base_s[:19], "%Y-%m-%d %H:%M:%S")
        tsec = fa.variables["time"][:]
        times = [base + D.timedelta(seconds=float(s)) for s in tsec]
        za = fa.variables["zeta"][:]
        zb = fb.variables["zeta"][:]
        # hourly from cycle init (include nowcast negatives)
        init = cycle.replace(tzinfo=None)
        stations = {}
        for sid in STATIONS:
            ix = [i for i, s in enumerate(nm) if sid in s]
            if not ix:
                continue
            i = ix[0]
            df = (za[:, i] - zb[:, i]) / 0.3048  # m -> ft
            hourly = {}
            # sample on the hour relative to init
            t0 = times[0].replace(minute=0, second=0, microsecond=0)
            if times[0].minute or times[0].second:
                t0 += D.timedelta(hours=1)
            t1 = times[-1].replace(minute=0, second=0, microsecond=0)
            t = t0
            while t <= t1:
                # nearest 6-min
                k = min(range(len(times)), key=lambda j: abs((times[j] - t).total_seconds()))
                if abs((times[k] - t).total_seconds()) <= 6 * 60:
                    h = int(round((t - init).total_seconds() / 3600.0))
                    hourly[str(h)] = round(float(df[k]), 4)
                t += D.timedelta(hours=1)
            stations[sid] = {"hourly": hourly, "t0_ft": hourly.get("0")}
        return {
            "cycle": cycle.strftime("%Y%m%d%H"),
            "init": cycle.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "units": "ft",
            "source": "points.cwl.nc minus points.cwl.noanomaly.nc",
            "stations": stations,
        }
    finally:
        fa.close(); fb.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="UTC ISO, inclusive, e.g. 2026-10-31T18:00:00Z")
    ap.add_argument("--end", required=True, help="UTC ISO, inclusive")
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args()
    def parse(s):
        s = s.replace("Z", "")
        return D.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    os.makedirs(args.out, exist_ok=True)
    ok = skip = fail = 0
    for c in cycles(parse(args.start), parse(args.end)):
        dest = os.path.join(args.out, c.strftime("%Y%m%d%H") + ".json")
        if os.path.exists(dest):
            try:
                j = json.load(open(dest))
                if j.get("stations") and "9441102" in j["stations"]:
                    skip += 1
                    continue
            except Exception:
                pass
        try:
            with tempfile.TemporaryDirectory(prefix="stofsanom_") as tmp:
                rec = extract(c, tmp)
            json.dump(rec, open(dest, "w"))
            ok += 1
            print(f"{c:%Y%m%d%H} ok stations={len(rec['stations'])} -> {dest}", flush=True)
        except Exception as e:
            fail += 1
            print(f"{c:%Y%m%d%H} FAIL {type(e).__name__}: {e}", flush=True)
    print(f"done ok={ok} skip={skip} fail={fail}")
    return 0 if fail == 0 or ok + skip > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
