#!/usr/bin/env python3
"""One pass of the fast-style publisher (GitHub Actions, every 15 min; also runnable on the box).
For each model: newest cycle whose first step is out -> encode the steps that are out and not yet in R2 -> upload them,
then run.json (only the unbroken steps from the start, so the slider has no holes) -> manifest lists the newest `keep` runs
whose run.json is in R2 -> prune older runs. Never touches the Pages projects or the live site.
  fast_cycle.py [--models hrrr,gfs,ifs,aifs] [--minutes 40] [--workers 4] [--dry-run]
Env: CF_PAGES_KEY (Cloudflare token with R2 edit), CLOUDFLARE_ACCOUNT_ID."""
import os, sys, json, time, argparse, datetime as dt, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE
from upload_r2 import client, BUCKET, CT

def avail(m, c, s):
    import temp_maps as TM, menu_maps as M
    try:
        if m in FE.NOAA: u = M.MODELS[m]["url"].format(d=f"{c:%Y%m%d}", h=c.hour, s=s) + ".idx"
        elif m in ("eps", "aens"): u = FE.ENS_SRC[m][0].format(d=f"{c:%Y%m%d}", h=c.hour, s=s) + ".index"
        elif m == "nbm": u = FE.NBM_URL.format(d=f"{c:%Y%m%d}", h=c.hour, s=s) + ".idx"
        else: u = TM.MODELS[m]["url"]["sfc"].format(d=f"{c:%Y%m%d}", h=c.hour, s=s) + ".index"
        TM.get(u, (0, 10)); return True
    except Exception: return False

def target_cycle(m):
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 36):
        c = now - dt.timedelta(hours=b)
        if c.hour in FE.MODELS[m]["cycles"] and avail(m, c, FE.MODELS[m]["steps"][0]): return c

MORE = set(); WORK = {}
LASTMAN = {}
MAN_EVERY = 300   # s between manifest rewrites while a run is coming in (run.json is updated every chunk)
# --watch: minutes after the cycle time when the first step is usually out (measured 10-31 from R2 upload times and the
# NOAA / ECMWF open-data files); watching starts WATCH_EARLY min before that, and stops WATCH_SPAN h after it or when complete
DUE_MIN = {"hrrr": 45, "rrfs": 60, "nbm": 55, "gfs": 200, "ifs": 330, "ifs9": 420, "aifs": 320, "eps": 380, "aens": 350}
WATCH_EARLY, WATCH_SPAN = 60, 6

def run_due(s3, m):
    """True when model m has a cycle whose data is due now (or flowing) and whose run is not complete in R2."""
    now = dt.datetime.now(dt.timezone.utc)
    for b in range(0, 18):
        c = (now - dt.timedelta(hours=b)).replace(minute=0, second=0, microsecond=0)
        if c.hour not in FE.MODELS[m]["cycles"]: continue
        t0 = c + dt.timedelta(minutes=DUE_MIN.get(m, 60))
        if not (t0 - dt.timedelta(minutes=WATCH_EARLY) <= now <= t0 + dt.timedelta(hours=WATCH_SPAN)): continue
        try: r = json.loads(s3.get_object(Bucket=BUCKET, Key=f"runs/{m}/{c:%Y%m%d%H}/run.json")["Body"].read())
        except Exception: return True
        if not r.get("complete"): return True
    return False

def update_manifest(s3, fn, tries=8):
    """Read-modify-write manifest.json with an ETag check (If-Match), so parallel model jobs never overwrite each other."""
    import random
    for i in range(tries):
        o = s3.get_object(Bucket=BUCKET, Key="manifest.json"); man = json.loads(o["Body"].read()); fn(man)
        try:
            s3.put_object(Bucket=BUCKET, Key="manifest.json", Body=json.dumps(man).encode(), ContentType="application/json", IfMatch=o["ETag"])
            return man
        except Exception as e:
            if "PreconditionFailed" not in str(e) and "412" not in str(e): raise
            time.sleep(0.5 + random.random() * 2)
    raise SystemExit("manifest.json kept changing; gave up")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--models", default="hrrr,gfs,ifs,aifs"); ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--out", default=os.path.join(HERE, "data")); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--watch", action="store_true"); ap.add_argument("--every", type=float, default=60)
    a = ap.parse_args(); t_end = time.time() + a.minutes * 60; D = a.out; os.makedirs(D, exist_ok=True)
    s3 = client(); s3.download_file(BUCKET, "manifest.json", f"{D}/manifest.json")
    models = a.models.split(",")
    # ECMWF 9 km (ifs9) rides the ECMWF job (no workflow change): after "ifs", once its static layers are in the manifest
    if "ifs" in models and "ifs9" not in models: models.insert(models.index("ifs") + 1, "ifs9")
    def one(m):
        if time.time() > t_end - 120: print("time budget used up", flush=True); MORE.add(m); return
        if m not in json.load(open(f"{D}/manifest.json")).get("models", {}): print(m, "no static layers in R2 yet, skipped", flush=True); return
        c = target_cycle(m)
        if not c: print(m, "no cycle out", flush=True); return
        cyc = f"{c:%Y%m%d%H}"; key = f"runs/{m}/{cyc}/run.json"; rd = f"{D}/runs/{m}/{cyc}"; os.makedirs(rd + "/single", exist_ok=True)
        try:
            s3.download_file(BUCKET, key, f"{rd}/run.json"); r0 = json.load(open(f"{rd}/run.json"))
            if r0.get("complete"): print(m, cyc, "complete in R2", flush=True); return
        except Exception: r0 = None
        print(m, cyc, "has", len((r0 or {}).get("steps", [])), "steps in R2", flush=True)
        want = FE.steps_for(m, c.hour)
        # 10-31 frame at a time (Benjamin 11:48 AM "roll hour data one frame at a time the moment the data is available"): a chunk is
        # only as many hours as there are workers, all encoded in parallel, so each chunk takes about one hour's encode time; when
        # the job is caught up with the source only the hours that are out are in the chunk (usually one), and each goes live
        # (step files + run.json) as soon as it is encoded. The manifest (run list) is rewritten for a new run, at completion and at
        # most every MAN_EVERY s in between (the viewer follows an open run through its run.json), to keep R2 writes low.
        W = min(a.workers, 2) if m == "ifs9" else a.workers
        chunk = W
        while True:
            if time.time() >= t_end - 60: MORE.add(m); break   # budget ran out with hours left -> ask for a re-dispatch
            have = {x["f"] for x in (json.load(open(f"{rd}/run.json"))["steps"] if os.path.exists(f"{rd}/run.json") else [])}
            nxt = [s for s in want if s not in have][:chunk]
            if not nxt or not avail(m, c, nxt[0]): break
            nxt = [s for s in nxt if avail(m, c, s)] if not avail(m, c, nxt[-1]) else nxt
            first = not (r0 or {}).get("steps")
            run, new = FE.steps(m, cyc, nxt, D, W)   # 9 km: ~3 GB per worker (global 0.1 deg fields)
            # steps() kept only the unbroken run of the chunk; rebuild the full list with the old steps
            full = json.load(open(f"{rd}/run.json")); old = {x["f"]: x for x in ((r0 or {}).get("steps", []))}
            for x in full["steps"]: old[x["f"]] = x
            ordered = []
            for s in want:
                if s in old: ordered.append(old[s])
                else: break
            for k_ in ("points", "pts_file"):
                if k_ in json.load(open(f"{rd}/run.json")): full[k_] = json.load(open(f"{rd}/run.json"))[k_]
            full.update(steps=ordered, fields=sorted({k for x in ordered for k in x["ranges"]}), complete=len(ordered) == len(want), expected=len(want))
            json.dump(full, open(f"{rd}/run.json", "w"), indent=1); r0 = full
            if not new: break
            files = [f"runs/{m}/{cyc}/single/{f}" for f in os.listdir(f"{rd}/single") if any(f.endswith(f"_f{s:03d}.png") or f.endswith(f"_f{s:03d}.json") for s in new)]
            if not a.dry_run:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(16) as ex: list(ex.map(lambda k: s3.upload_file(f"{D}/{k}", BUCKET, k, ExtraArgs={"ContentType": "application/json" if k.endswith(".json") else "image/png"}), files))
                s3.upload_file(f"{rd}/run.json", BUCKET, key, ExtraArgs={"ContentType": "application/json"})
                if first or full["complete"] or time.time() - LASTMAN.get(m, 0) >= MAN_EVERY:
                    publish_manifest(s3, D, m, prog=(cyc, ordered[-1]["f"] if ordered else None, want[-1], full["complete"])); LASTMAN[m] = time.time()
            print(f"{m} {cyc}: uploaded {len(files)} files, {len(ordered)}/{len(want)} steps live", flush=True); WORK[m] = WORK.get(m, 0) + len(new)
            for f in files: os.remove(f"{D}/{f}")   # keep the runner disk small
            if full["complete"]:
                if not a.dry_run:
                    try: write_agg(s3, m, cyc, full, f"{rd}/run.json", key)
                    except Exception as e: print(m, cyc, "aggregate town files failed (site falls back to per-step files):", e, flush=True)
                break

    for m in models: one(m)
    # --watch (10-31): keep polling (every --every s) while a model has a run due or in progress, so a new run starts within
    # about a minute of its first hours being out instead of waiting for the next (throttled, ~40 min apart) cron run
    while a.watch and time.time() < t_end - 180:
        due = [m for m in models if m not in MORE and run_due(s3, m)]
        if not due: print("watch: nothing due, done", flush=True); break
        time.sleep(a.every)
        for m in due: one(m)
    if a.watch:
        for m in models:
            if run_due(s3, m): MORE.add(m)   # still due when the budget ends -> re-dispatch (chains until the run is in)

MG_KEEP = 4   # runs per model with town data for the meteograms page
def write_agg(s3, m, cyc, full, local, key):
    """Complete run -> one single/{pts,mem}_all.json ({"f": [...], "d": [...]}) so a meteogram / the Pass Forecaster
    fetches 1 file instead of ~50. run.json "agg" lists the names; the site falls back to per-step files without it."""
    from concurrent.futures import ThreadPoolExecutor
    agg = []
    for name in ("pts", "mem"):
        fs = [x["f"] for x in full["steps"]]
        def get(f):
            try: return json.loads(s3.get_object(Bucket=BUCKET, Key=f"runs/{m}/{cyc}/single/{name}_f{f:03d}.json")["Body"].read())
            except Exception: return None
        with ThreadPoolExecutor(16) as ex: d = list(ex.map(get, fs))
        if not all(x is not None for x in d): continue
        s3.put_object(Bucket=BUCKET, Key=f"runs/{m}/{cyc}/single/{name}_all.json", Body=json.dumps({"f": fs, "d": d}, separators=(",", ":")).encode(),
                      ContentType="application/json")
        agg.append(name)
    if agg:
        full["agg"] = agg; json.dump(full, open(local, "w"), indent=1)
        s3.upload_file(local, BUCKET, key, ExtraArgs={"ContentType": "application/json"})
        print(m, cyc, "aggregate town files:", agg, flush=True)


def publish_manifest(s3, D, m, prog=None):
    keep = FE.MODELS[m]["keep"]
    pre = {o["Prefix"].split("/")[2] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{m}/", Delimiter="/").get("CommonPrefixes", [])}
    present = sorted(r for r in pre if "Contents" in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{m}/{r}/run.json", MaxKeys=1))
    # 10-31 (keep 2 -> 4): a run already slimmed (map images deleted, marker .../slim) must never come back into the map list
    def is_slim(r):
        try: s3.head_object(Bucket=BUCKET, Key=f"runs/{m}/{r}/slim"); return True
        except Exception: return False
    full = [r for r in present if not is_slim(r)]
    kept = full[-keep:]
    if FE.MODELS[m].get("keep_long"):   # also keep the newest full-length (00/12Z) run so 360 h stays on the site
        longs = [r for r in full if int(r[8:10]) not in FE.MODELS[m].get("short_cycles", ())]
        if longs and longs[-1] not in kept: kept = sorted(kept + [longs[-1]])
    # 10-30 meteograms page multi-run (old site showed 4 runs): the newest MG_KEEP runs keep their small town files
    # (run.json + pts_/mem_ JSON); map images of runs that left the map list are deleted ("slim" runs, marker key .../slim).
    mg = present[-MG_KEEP:]
    # 10-31: runs the box published for the hidden preview before this code was pushed (manifest "runs_x", file run_x.json, so
    # the old workflow never listed them). Once this code runs they are dropped from the manifest and deleted below.
    xr = []
    def both(mn):
        mn.setdefault("runs", {})[m] = kept; mn.setdefault("mgruns", {})[m] = sorted(set(mg) | set(kept))
        # 10-31: runs still coming in -> manifest "progress" {model: {cycle: [last hour live, last hour expected]}} so the site can
        # say "loading" (the production page ignores the key); dropped once complete or out of the list
        pg = mn.setdefault("progress", {}).setdefault(m, {})
        if prog:
            if prog[3]: pg.pop(prog[0], None)
            else: pg[prog[0]] = [prog[1], prog[2]]
        for k in [k for k in pg if k not in kept]: pg.pop(k)
        if not pg: mn["progress"].pop(m)
        xr[:] = (mn.get("runs_x") or {}).pop(m, None) or []
        if "runs_x" in mn and not mn["runs_x"]: del mn["runs_x"]
    man = update_manifest(s3, both)
    for old in [r for r in xr if r not in present]:
        ks = [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"runs/{m}/{old}/") for o in pg.get("Contents", [])]
        for i in range(0, len(ks), 1000): s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in ks[i:i + 1000]]})
        print("pruned preview run", m, old, len(ks), "objects", flush=True)
    json.dump(man, open(f"{D}/manifest.json", "w"))
    for old in [r for r in present if r not in kept]:
        slim = old in mg
        if slim:
            try: s3.head_object(Bucket=BUCKET, Key=f"runs/{m}/{old}/slim"); continue   # already slimmed
            except Exception: pass
        ks = [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"runs/{m}/{old}/") for o in pg.get("Contents", [])]
        if slim: ks = [k for k in ks if not (k.endswith("/run.json") or k.split("/")[-1].startswith(("pts_", "mem_")))]
        for i in range(0, len(ks), 1000): s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in ks[i:i + 1000]]})
        if slim: s3.put_object(Bucket=BUCKET, Key=f"runs/{m}/{old}/slim", Body=b"1")
        print("slimmed" if slim else "pruned", m, old, len(ks), "objects", flush=True)

if __name__ == "__main__":
    main()
    print("more work left:", sorted(MORE) or "none", flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f: f.write(f"more={'true' if MORE else 'false'}\n")
    sys.stdout.flush(); os._exit(0)
