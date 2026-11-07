#!/usr/bin/env python3
"""Batch-fill the Washington forecast map viewer from ONE model run.

Calls the map scripts in tools/wa_maps (precip_map.py, snow_map.py, gust_map.py,
wave_map.py, nbm_map.py) as subprocesses, so colors, labels and layout come from
one place. Each output folder gets a small site_frame.json
sidecar (tab, period, view, valid window) that publish_forecast_maps.py reads.

NOT scheduled. Run by hand only:
  python tools/forecast/render_forecast_batch.py \
      --cycle 2026102312 --tabs rain --periods 6h,24h,48h --views full --hours 48 [--jobs 2] [--dry-run]

Periods (rain/snow): 1h (rain, HRRR only), step (3 h, the finest ECMWF step), 6h, 12h,
24h, 48h, total (run start to each 6 h step). Gusts: step, max6h, max12h, max24h.
Waves: step, max24h (hmax). Lows/highs: daily (NBM, one per day).

Models (--models, default ecmwf; lows/highs default nbm): ecmwf, nbm, eps (ENS mean), eps90 (ENS 90th percentile), hrrr.
Each tab only renders the models it supports (MODELS below). Finest steps: ECMWF 3 h, NBM 1 h to 36 h, ENS 3 h to 144 h
then 6 h; "step" windows that fall between a model's steps are skipped. (GFS removed 10-24-26.)
"""
import argparse, datetime as dt, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
MAPS = os.environ.get("WX_MAPS_DIR", os.path.normpath(os.path.join(HERE, "..", "wa_maps")))
PY = os.environ.get("WX_PYTHON", sys.executable)
OUTROOT = os.environ.get("SITE_BATCH", ".site_batch")

TABS = {
    "rain":   {"script": "precip_map.py", "views": ["full", "west", "east"],
               "periods": ["1h", "step", "6h", "12h", "24h", "48h", "total"]},
    "bcrain": {"script": "precip_map.py", "views": ["bc", "lowermainland"],
               "periods": ["step", "6h", "12h", "24h", "48h", "total"]},
    "snow":   {"script": "snow_map.py", "views": ["full", "west", "east", "cascades", "northeast"],
               "periods": ["step", "6h", "12h", "24h", "48h", "total"]},
    "gusts":  {"script": "gust_map.py", "views": ["full", "west", "east"],
               "periods": ["step", "max6h", "max12h", "max24h"]},
    "waves":  {"script": "wave_map.py", "views": ["full", "vi"], "periods": ["step", "max24h"]},
    "lows":   {"script": "nbm_map.py", "views": ["full", "west", "east"], "periods": ["daily"]},
    "highs":  {"script": "nbm_map.py", "views": ["full", "west", "east"], "periods": ["daily"]},
}
# GFS left the Washington tabs on 10-24-26 (Benjamin: GFS only as 500 mb anomaly + sea-level pressure). The old lists are in
# archive/gfs_products_20261024/wa_tab_models.py.txt; the map scripts still accept --source gfs / --model gfs.
MODELS = {"rain": ["ecmwf", "nbm", "eps", "eps90", "hrrr"], "bcrain": ["ecmwf", "eps", "eps90"],
          "snow": ["ecmwf", "nbm", "eps", "eps90"], "gusts": ["ecmwf", "nbm", "eps"],
          "lows": ["nbm", "eps"], "highs": ["nbm", "eps"], "waves": ["ecmwf"]}
DEFAULT_MODEL = {"lows": "nbm", "highs": "nbm"}
MODEL_NAME = {"ecmwf": "ECMWF", "nbm": "NBM", "gfs": "GFS", "eps": "EPS mean", "eps90": "EPS 90th pct", "hrrr": "HRRR"}
HOURLY = {"hrrr"}          # 1 h windows only for the hourly 3 km model (A1); HRRR 00/12Z runs reach 48 h
MAX_H = {"hrrr": 48}


def on_model_step(model, h):
    """True if forecast hour h is a native step of the model (GFS 6-hourly past 120 h, ENS past 144 h)."""
    if model == "gfs": return h <= 120 or h % 6 == 0
    if model in ("eps", "eps90"): return h <= 144 or h % 6 == 0
    return True


PERIOD_HOURS = {"1h": 1, "step": 3, "6h": 6, "12h": 12, "24h": 24, "48h": 48,
                "max6h": 6, "max12h": 12, "max24h": 24}


def windows(t0, period, horizon):
    """(start, end) PT datetimes for one period over the horizon from run start t0."""
    if period == "total":
        return [(t0, t0 + dt.timedelta(hours=h)) for h in range(6, horizon + 1, 6)]
    if period == "daily":
        d0 = t0.date()
        return [(dt.datetime.combine(d0 + dt.timedelta(days=i), dt.time(0), PT),) * 2
                for i in range(max(1, horizon // 24))]
    n = PERIOD_HOURS[period]
    if period == "step":  # single valid time for gusts/waves, 3 h accumulation for rain/snow
        return [(t0 + dt.timedelta(hours=h - n), t0 + dt.timedelta(hours=h)) for h in range(n, horizon + 1, n)]
    return [(t0 + dt.timedelta(hours=h), t0 + dt.timedelta(hours=h + n)) for h in range(0, horizon - n + 1, n)]


def fmt(t):
    return t.strftime("%Y-%m-%d %H")


def build(tab, period, view, s, e, cycle, out, model="ecmwf"):
    cfg = TABS[tab]
    cmd = [PY, os.path.join(MAPS, cfg["script"])]
    if tab in ("rain", "bcrain", "snow"):
        cmd += ["--start", fmt(s), "--end", fmt(e), "--cycle", cycle]
        if model != "ecmwf":
            cmd += ["--source", model]
        if view != "full":
            cmd += ["--region", view]
    elif tab == "gusts":
        # gust_map takes PT hours on --date; single steps are 0 h windows (start = end)
        a = e if period == "step" else s
        cmd += ["--model", model, "--date", a.strftime("%Y-%m-%d"), "--start", str(a.hour),
                "--end", str(e.hour if e.date() == a.date() else 23), "--cycle", cycle]
        if view != "full":
            cmd += ["--region", view]
    elif tab == "waves":
        a = e if period == "step" else s
        cmd += ["--start", fmt(a), "--end", fmt(e), "--cycle", cycle]
        if period.startswith("max"):
            cmd += ["--hmax"]
        if view == "vi":
            cmd += ["--region", "vi"]
    elif tab in ("lows", "highs"):
        cmd += ["--kind", tab[:-1], "--date", s.strftime("%Y-%m-%d")]
        if model != "nbm":
            cmd += ["--source", model, "--cycle", cycle]
        if view != "full":
            cmd += ["--region", view]
    return cmd + ["--out", out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", required=True, help="ECMWF run YYYYMMDDHH (UTC)")
    ap.add_argument("--tabs", default=",".join(TABS))
    ap.add_argument("--periods", default="all")
    ap.add_argument("--views", default="all")
    ap.add_argument("--hours", type=int, default=144, help="forecast horizon (h)")
    ap.add_argument("--models", default="default", help="comma list of ecmwf,nbm,eps,eps90,hrrr or 'all' (default: each tab's usual model)")
    ap.add_argument("--jobs", type=int, default=1, help="parallel renders (each uses ~1-2 GB RAM)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--shard", default="1/1", help="K/N: render only every N-th job starting at K (workflow matrix split)")
    a = ap.parse_args()
    t0 = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc).astimezone(PT)
    jobs = []
    for tab in a.tabs.split(","):
        cfg = TABS[tab]
        for period in cfg["periods"]:
            if a.periods != "all" and period not in a.periods.split(","):
                continue
            for view in cfg["views"]:
                if a.views != "all" and view not in a.views.split(","):
                    continue
                base = DEFAULT_MODEL.get(tab, "ecmwf")
                want = [base] if a.models == "default" else MODELS[tab] if a.models == "all" else a.models.split(",")
                for model in [m for m in want if m in MODELS[tab]]:
                    if model in ("nbm",) and view in ("bc", "lowermainland"):
                        continue  # NBM is CONUS-only
                    if (period == "1h" and model not in HOURLY) or (period == "step" and model in HOURLY):
                        continue  # 1 h windows only for HRRR; HRRR skips the 3 h "step" (its 1 h maps are finer)
                    for s, e in windows(t0, period, min(a.hours, MAX_H.get(model, a.hours))):
                        h = round((e - t0).total_seconds() / 3600)
                        if period == "step" and not on_model_step(model, h):
                            continue
                        tdir = tab if model == base else f"{tab}.{model}"
                        out = f"{OUTROOT}/{a.cycle}/{tdir}/{period}/{view}/{e:%Y%m%d%H}"
                        jobs.append((tab, period, view, s, e, out, build(tab, period, view, s, e, a.cycle, out, model), model))
    k, n = (int(x) for x in a.shard.split("/"))
    if not 1 <= k <= n:
        raise SystemExit(f"bad --shard {a.shard}")
    jobs = jobs[k - 1::n]  # round-robin, so every shard gets a similar mix of tabs, views and hours
    print(f"shard {k}/{n}: {len(jobs)} renders (about {len(jobs) * 25 / 60 / max(1, a.jobs):.0f} min at ~25 s each, {a.jobs} at a time)")
    if a.dry_run:
        for j in jobs:
            print(" ".join(j[-2][1:]))
        return

    def run(j):
        tab, period, view, s, e, out, cmd, model = j
        if os.path.exists(f"{out}/site_frame.json"):
            return f"skip {out}"
        os.makedirs(out, exist_ok=True)
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        open(f"{out}/render.log", "w").write(r.stdout[-4000:] + r.stderr[-4000:])
        if tab == "gusts" and os.path.exists(f"{out}/{model}_final.jpg"):  # gust_map.py names its output <model>_final.jpg
            os.replace(f"{out}/{model}_final.jpg", f"{out}/final.jpg")
        if r.returncode != 0 or not os.path.exists(f"{out}/final.jpg"):
            return f"FAIL {out} rc={r.returncode}"
        json.dump({"tab": tab, "period": period, "view": view, "model": MODEL_NAME[model],
                   "cycle": a.cycle, "start_pt": s.isoformat(), "end_pt": e.isoformat()},
                  open(f"{out}/site_frame.json", "w"), indent=1)
        return f"ok {out} {time.time() - t:.0f}s"

    with ThreadPoolExecutor(a.jobs) as ex:
        for msg in ex.map(run, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
