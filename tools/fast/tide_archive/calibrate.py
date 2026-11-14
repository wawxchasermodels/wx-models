#!/usr/bin/env python3
"""Daily self-calibration of the archived Conditional Prediction (Benjamin t3014u, 2026-11-14). Background only (t3018u): stored, not shown.

Once a day, at the 08 UTC issue slot (12 AM PST), for each station and lead range it looks back LOOKBACK_D days at the RAW
archived snapshots, compares them with observed water levels that existed at that moment (verified time <= calibration
time, so it is strictly causal), and sets
    corr(range) = clip( -mean_error * ns / (ns + SHRINK_K), +-CAP )      if ns >= MIN_SNAPS and n >= MIN_HOURS, else 0
(error = raw conditional - observed; ns = snapshots contributing, n = hourly pairs). The correction is applied to that day's
four snapshots (08, 14, 20, 02 UTC) as a smooth function of lead: 0 at lead 0 (the line still starts on the current
observation), the range values at the range centres 6/18/36/60 h, linear in between, flat after 60 h.
Each snapshot keeps the raw residual "r" and gains "rc" (calibrated) and "cal" (the calibration time). Coefficients:
  v1/calib/<YYYY-MM>.json  {"entries": [{t, lookback_d, ranges, st: {station: {corr, mean, n, ns}}}]}  and the newest in index.json.

  python calibrate.py --out DIR --from 2026100108 --to 2026111414    # rolling hindcast: fills missing days, applies
  python calibrate.py --out DIR --from now --to now                  # live, after tide_archive.py --issue now
"""
import argparse, datetime as D, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tide_archive as A

LOOKBACK_D, SHRINK_K, CAP, MIN_SNAPS, MIN_HOURS = 10, 8, 0.5, 8, 48
RANGES = [(0, 12), (12, 24), (24, 48), (48, 72)]
CENTRES = [6, 18, 36, 60]
CAL_HOUR = 8
HR, DAY = A.HR, A.DAY


def corr_at(lead_h, c):   # piecewise linear in lead through (0,0) and the range centres
    pts = [(0, 0.0)] + list(zip(CENTRES, c))
    if lead_h >= pts[-1][0]: return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= lead_h <= x1: return y0 + (y1 - y0) * (lead_h - x0) / (x1 - x0)
    return 0.0


def coeffs(issues, obs, pred, C, lookback_d=LOOKBACK_D, k=SHRINK_K, cap=CAP, min_snaps=MIN_SNAPS, min_hours=MIN_HOURS):
    """Correction per lead range from raw snapshots issued in [C - lookback, C) and verified at times <= C."""
    out = []
    for a, b in RANGES:
        errs, snaps = [], set()
        for I in issues:
            if not (C - lookback_d * DAY <= I["t"] < C): continue
            for kk in range(max(1, a), min(b, len(I["r"]) - 1) + (1 if b == 72 else 0)):
                t = I["t"] + kk * HR
                if t > C: break
                o, p = obs.get(t), pred.get(t)
                if o is None or p is None: continue
                errs.append(p + I["r"][kk] - o); snaps.add(I["t"])
        n, ns = len(errs), len(snaps)
        m = sum(errs) / n if n else 0.0
        c = 0.0
        if ns >= min_snaps and n >= min_hours: c = max(-cap, min(cap, -m * ns / (ns + k)))
        out.append({"corr": round(c, 3), "mean": round(m, 3), "n": n, "ns": ns})
    return out


def load_station(out, st):
    issues = []
    d = os.path.join(out, "v1", st)
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if re.match(r"^\d{4}-\d{2}\.json$", f): issues += json.load(open(os.path.join(d, f)))["issues"]
    return sorted(issues, key=lambda i: i["t"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--from", dest="f", required=True); ap.add_argument("--to", required=True)
    ap.add_argument("--lookback", type=int, default=LOOKBACK_D)
    a = ap.parse_args()
    if a.f == "now":   # live: the current issue slot (same rule as tide_archive.py --issue now)
        nw = D.datetime.now(D.timezone.utc)
        a.f = A.slot_floor(int(nw.timestamp() * 1000)).strftime("%Y%m%d%H"); a.to = nw.strftime("%Y%m%d%H")   # incl. an off-slot live snapshot
    f, t = (int(D.datetime.strptime(x, "%Y%m%d%H").replace(tzinfo=D.timezone.utc).timestamp() * 1000) for x in (a.f, a.to))
    # calibration times covering [f, t]: the 08 UTC at or before f, then daily
    c0 = D.datetime.fromtimestamp(f / 1000, D.timezone.utc).replace(hour=CAL_HOUR, minute=0, second=0, microsecond=0)
    if c0.timestamp() * 1000 > f: c0 -= D.timedelta(days=1)
    cals = []; c = c0
    while c.timestamp() * 1000 <= t: cals.append(int(c.timestamp() * 1000)); c += D.timedelta(days=1)
    cal_dir = os.path.join(a.out, "v1", "calib"); os.makedirs(cal_dir, exist_ok=True)
    hist = {}
    for fn in os.listdir(cal_dir):
        for e in json.load(open(os.path.join(cal_dir, fn)))["entries"]: hist[e["t"]] = e
    now = int(D.datetime.now(D.timezone.utc).timestamp() * 1000)
    newest = {}
    for st in A.STATIONS:
        issues = load_station(a.out, st)
        if not issues: continue
        lo = cals[0] - (a.lookback + 1) * DAY
        pred = dict(A.coops("predictions", st, lo, max(cals[-1], t) + 76 * HR, "&interval=6"))
        obs = dict(A.coops("water_level", st, lo, min(now, cals[-1]) + A.H6))
        for C in cals:
            e = hist.setdefault(C, {"t": C, "lookback_d": a.lookback, "shrink_k": SHRINK_K, "cap": CAP, "min_snaps": MIN_SNAPS,
                                    "ranges": RANGES, "centres": CENTRES, "st": {}})
            if st not in e["st"]:
                o_c = {tt: v for tt, v in obs.items() if tt <= C}   # only verification that existed at C
                e["st"][st] = coeffs(issues, o_c, pred, C, a.lookback)
        # apply to snapshots in [f, t]: the newest calibration at or before each issue time
        by_month = {}
        for I in issues:
            if not (f <= I["t"] <= t): continue
            C = max((x for x in cals if x <= I["t"]), default=None)
            if C is None: continue
            cc = [b["corr"] for b in hist[C]["st"][st]]
            I["rc"] = [round(I["r"][k] + corr_at(k, cc), 3) for k in range(len(I["r"]))]; I["cal"] = C
        for I in issues:
            by_month.setdefault(D.datetime.fromtimestamp(I["t"] / 1000, D.timezone.utc).strftime("%Y-%m"), []).append(I)
        for mon, lst in by_month.items():
            fn = os.path.join(a.out, "v1", st, f"{mon}.json")
            json.dump({"station": st, "issues": lst}, open(fn + ".tmp", "w"), separators=(",", ":")); os.replace(fn + ".tmp", fn)
        newest[st] = {"t": cals[-1], "lookback_d": a.lookback, "ranges": RANGES, "centres": CENTRES, "c": hist[cals[-1]]["st"][st]}
    by_m = {}
    for C, e in hist.items(): by_m.setdefault(D.datetime.fromtimestamp(C / 1000, D.timezone.utc).strftime("%Y-%m"), []).append(e)
    for mon, lst in by_m.items():
        fn = os.path.join(cal_dir, f"{mon}.json")
        json.dump({"entries": sorted(lst, key=lambda e: e["t"])}, open(fn + ".tmp", "w"), separators=(",", ":")); os.replace(fn + ".tmp", fn)
    idx_fn = os.path.join(a.out, "v1", "index.json"); idx = json.load(open(idx_fn))
    idx.setdefault("calib", {}).update(newest); idx["calib_months"] = sorted(by_m)
    json.dump(idx, open(idx_fn + ".tmp", "w"), separators=(",", ":")); os.replace(idx_fn + ".tmp", idx_fn)
    print(json.dumps({"calibrations": len(cals), "stations": len(newest), "newest": {s: [b["corr"] for b in v["c"]] for s, v in newest.items()}}))


if __name__ == "__main__":
    main()
