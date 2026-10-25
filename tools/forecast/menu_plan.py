#!/usr/bin/env python3
"""Plan the menu-map jobs (speed_build_v1): split each model/tier into forecast-hour chunks and skip models whose newest
cycle is already published (incremental). Standard library only, so the plan job needs no pip install.

  python menu_plan.py --models ifs,aifs,hrrr,rrfs --tiers A,B,C --global-cycle 2026102500 \
      [--state menu_state.json] [--have-caches keys.txt] [--chunk-min 30] [--incremental 1]

Prints GitHub outputs:  menu=<matrix json>  menu_reuse=<json list>  menu_cycles=<json>  menu_any=true|false
Switches (env or flags): MENU_CHUNK_MIN=0 -> one job per model/tier (old layout); MENU_INCREMENTAL=0 -> render every model.
"""
import argparse, datetime as dt, json, math, os, sys, urllib.request

# Wall minutes per model/tier at the old one-core speed (go-live run 40177466747, 10-25-26). ifs A was still running
# past 4 h 40 m; 330 is an estimate. Used only to size the chunks.
OLD_MIN = {("ifs", "A"): 79, ("ifs", "B"): 348, ("ifs", "C"): 184, ("aifs", "A"): 7, ("aifs", "B"): 51, ("aifs", "C"): 72,
           ("hrrr", "A"): 54, ("hrrr", "B"): 146, ("hrrr", "C"): 87, ("rrfs", "A"): 33, ("rrfs", "B"): 195, ("rrfs", "C"): 33}
# 10-25-26 priority tiers: A = precip/snow/ice/p-type, B = gust/feels/dewpoint/temps aloft, C = heavy extras (IVT, upper
# winds, PW, thickness, cloud, IR, vis, fog). Minutes re-split per product from the old tiers of the run above (map count,
# IVT/w850/w250 weighted x4).
HRRR = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfsfcf{s:02d}.grib2"
RRFS = "https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.2dfld.3km.f{s:03d}.conus.grib2"
LONG = {"hrrr": (HRRR, 48), "rrfs": (RRFS, 84)}


def render_steps(m):
    """Same frames the workflow asked menu_maps.py for: IFS/AIFS every 6 h to 240 h, HRRR to 48 h and RRFS to 84 h hourly."""
    if m in LONG: return list(range(1, LONG[m][1] + 1))
    return list(range(6, 241, 6))


def latest_long(m, now=None):
    """Newest 00/06/12/18Z HRRR/RRFS run whose last hour is out (same rule as temp_maps.latest_cycle).
    MENU_PICK=started: newest long run whose first hour is out (pair with MENU_WAIT_MIN on the chunks so each hour is
    drawn as soon as it lands)."""
    url, hours = LONG[m]; hours = 1 if os.environ.get("MENU_PICK", "complete") == "started" else hours; now = (now or dt.datetime.now(dt.timezone.utc)).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 30):
        c = now - dt.timedelta(hours=b)
        if c.hour % 6: continue
        if os.environ.get("WX_CYCLE_HOUR") and c.hour != int(os.environ["WX_CYCLE_HOUR"]): continue   # scheduled run: 12Z only
        req = urllib.request.Request(url.format(d=f"{c:%Y%m%d}", h=c.hour, s=hours) + ".idx", headers={"Range": "bytes=0-10", "User-Agent": "wx-models"})
        try:
            with urllib.request.urlopen(req, timeout=30): return f"{c:%Y%m%d%H}"
        except Exception: pass
    raise SystemExit(f"no {m} long run found")


def chunks(steps, n):
    """n contiguous, near-equal forecast-hour ranges (early hours first, so they can be published first)."""
    n = max(1, min(n, len(steps))); k, r = divmod(len(steps), n); out, i = [], 0
    for j in range(n):
        w = k + (j < r); out.append(steps[i:i + w]); i += w
    return out


def cache_key(m, cyc, tiers, ver):
    return f"menu-out-{ver}-{m}-{cyc}-{''.join(sorted(tiers))}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="ifs,aifs,hrrr,rrfs"); ap.add_argument("--tiers", default="A,B,C")
    ap.add_argument("--global-cycle", required=True); ap.add_argument("--state"); ap.add_argument("--have-caches")
    ap.add_argument("--chunk-min", type=float, default=float(os.environ.get("MENU_CHUNK_MIN", "30")))
    ap.add_argument("--incremental", default=os.environ.get("MENU_INCREMENTAL", "1"))
    ap.add_argument("--ver", default=os.environ.get("MENU_CACHE_VER", "v1"))
    ap.add_argument("--waves", default=os.environ.get("MENU_WAVES", "A,B:C"), help="tier groups for the deploy waves, e.g. A,B:C")
    ap.add_argument("--speedup", type=float, default=1.0, help="expected per-job speedup used when sizing chunks (1 = size at old speed)")
    a = ap.parse_args()
    ms = [m for m in a.models.split(",") if m in ("ifs", "aifs", "hrrr", "rrfs")]; ts = [t for t in a.tiers.split(",") if t in "ABC" and t]
    cyc = {m: (latest_long(m) if m in LONG else a.global_cycle) for m in ms}
    state = {}
    if a.state and os.path.exists(a.state):
        try: state = json.load(open(a.state))
        except Exception: state = {}
    have = set(open(a.have_caches).read().split()) if a.have_caches and os.path.exists(a.have_caches) else set()
    inc = str(a.incremental).lower() not in ("0", "off", "false", "no")
    include, reuse = [], []
    for m in ms:
        key = cache_key(m, cyc[m], ts, a.ver)
        st = state.get(m, {})
        if inc and st.get("cycle") == cyc[m] and st.get("key") == key and key in have:
            reuse.append({"model": m, "cycle": cyc[m], "key": key}); continue
        for t in ts:
            n = 1 if a.chunk_min <= 0 else math.ceil(OLD_MIN.get((m, t), 60) / a.speedup / a.chunk_min)
            parts = chunks(render_steps(m), n)
            for j, p in enumerate(parts, 1):
                include.append({"model": m, "tier": t, "cycle": cyc[m], "chunk": f"{j}of{len(parts)}",
                                "steps": ",".join(map(str, p)), "first": p[0], "last": p[-1], "key": key})
    include = sorted(include, key=lambda x: (x["first"], x["model"], x["tier"]))   # early hours of every model run first
    print("menu=" + json.dumps({"include": include}) if include else "menu=" + json.dumps({"include": [{"model": "none"}]}))
    print("menu_any=" + ("true" if include else "false"))
    for w, grp in zip(("w3", "w4"), (a.waves.split(":") + ["", ""])[:2]):   # one matrix per deploy wave
        sub = [x for x in include if x["tier"] in grp.split(",")]
        print(f"menu_{w}=" + json.dumps({"include": sub if sub else [{"model": "none"}]}))
        print(f"menu_{w}_any=" + ("true" if sub else "false"))
    print("menu_reuse=" + json.dumps(reuse if reuse else [{"model": "none"}]))
    print("menu_reuse_any=" + ("true" if reuse else "false"))
    rendered = sorted({x["model"] for x in include})
    print("menu_store=" + json.dumps(rendered if rendered else ["none"]))
    print("menu_cycles=" + json.dumps(cyc))
    print("menu_keys=" + json.dumps({m: cache_key(m, cyc[m], ts, a.ver) for m in ms}))
    print(f"# {len(include)} menu chunk jobs, reused {[r['model'] for r in reuse]}", file=sys.stderr)


if __name__ == "__main__":
    main()
