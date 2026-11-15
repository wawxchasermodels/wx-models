#!/usr/bin/env python3
"""Tides viewer: sea surface temperature (warm water) term for the Conditional Prediction (Benjamin t3069u, 2026-11-14). MOCK.

Source: NOAA OISST v2.1 daily SST anomaly, near real time (ERDDAP ncdcOisst21NrtAgg_LonPM180 on coastwatch.pfeg.noaa.gov;
public, no key, 0.25 deg, ~1-2 day latency; anomaly vs the 1971-2000 OISST climatology). ERDDAP sends no CORS header, so the
browser cannot read it directly: this script runs with tide_archive.py and writes <out>/v1/sst.json next to the archive.

Per station (pixels and coefficient in sst_coef.json):
  ssta30  = mean anomaly over the newest 30 days (deg C) -> "sea surface temperature vs normal"
  steric  = k * ssta30 (ft): the warm water rise this SST implies. NOT added: STOFS-2D-Global's own 5 day station bias
            correction (the "anomaly" in points.cwl vs points.cwl.noanomaly) already carries it (r ~ 0.6-0.7 vs SSTA, 2024-26).
  d       = mean of the newest 2 days - mean of the 5 days before (deg C): warming or cooling since the window STOFS last averaged
  adj     = k * d (ft): ADDED to the Conditional line, fading in with 1 - exp(-lead/12 h) so the line still starts on the
            newest observation (the fading bias is computed on the remainder; nothing is counted twice).
k = per station ft/deg C, monthly residual vs SSTA regression on Jun 2023 - Oct 2025 only (out-of-sample test Nov 2025 on).

  python sst_steric.py --out DIR
"""
import argparse, csv, io, json, os, time, urllib.request, datetime as D

ERD = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21NrtAgg_LonPM180.csv"
HERE = os.path.dirname(os.path.abspath(__file__))


def get(u, tries=4):
    err = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "wx-models-tides"}), timeout=120).read().decode()
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(3 + 4 * i)
    raise err


def fetch(days=45):
    t0 = (D.datetime.now(D.timezone.utc) - D.timedelta(days=days)).strftime("%Y-%m-%d")
    q = f"anom%5B({t0}):1:(last)%5D%5B0%5D%5B(45.5):(49.0)%5D%5B(-126.5):(-122.0)%5D"
    r = csv.reader(io.StringIO(get(f"{ERD}?{q}"))); next(r); next(r)
    by = {}
    for t, _z, la, lo, an in r:
        if an != "NaN": by.setdefault(t[:10], {})[(round(float(la), 3), round(float(lo), 3))] = float(an)
    return by


def station_terms(by, pix, k):
    days = sorted(by)
    ser = []
    for d in days:
        v = [by[d][(round(p[0], 3), round(p[1], 3))] for p in pix if (round(p[0], 3), round(p[1], 3)) in by[d]]
        if v: ser.append((d, sum(v) / len(v)))
    if len(ser) < 20: return None
    m = lambda a: sum(x[1] for x in a) / len(a)
    s30, rec, prior = m(ser[-30:]), m(ser[-2:]), m(ser[-7:-2])
    return {"last_day": ser[-1][0], "ssta30_c": round(s30, 3), "d_c": round(rec - prior, 3), "k_ft_per_c": k,
            "steric_ft": round(k * s30, 3), "adj_ft": round(k * (rec - prior), 3), "series": [[d, round(v, 2)] for d, v in ser[-30:]]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    coef = json.load(open(os.path.join(HERE, "sst_coef.json")))
    by = fetch()
    out = {"source": "NOAA OISST v2.1 NRT daily SST anomaly (ERDDAP ncdcOisst21NrtAgg_LonPM180), vs 1971-2000 climatology",
           "made": int(time.time() * 1000), "tau_h": 12, "stations": {}}
    for st, c in coef["stations"].items():
        r = station_terms(by, c["pix"], c["k_ft_per_c"])
        if r: out["stations"][st] = r
    fn = os.path.join(a.out, "v1", "sst.json"); os.makedirs(os.path.dirname(fn), exist_ok=True)
    json.dump(out, open(fn + ".tmp", "w"), separators=(",", ":")); os.replace(fn + ".tmp", fn)
    print(json.dumps({st: {k: v for k, v in r.items() if k != "series"} for st, r in out["stations"].items()}))


if __name__ == "__main__":
    main()
