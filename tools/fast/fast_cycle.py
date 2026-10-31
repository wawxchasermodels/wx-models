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

MORE = set()

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
    a = ap.parse_args(); t_end = time.time() + a.minutes * 60; D = a.out; os.makedirs(D, exist_ok=True)
    s3 = client(); s3.download_file(BUCKET, "manifest.json", f"{D}/manifest.json")
    for m in a.models.split(","):
        if time.time() > t_end - 120: print("time budget used up", flush=True); MORE.add(m); continue
        if m not in json.load(open(f"{D}/manifest.json")).get("models", {}): print(m, "no static layers in R2 yet, skipped", flush=True); continue
        c = target_cycle(m)
        if not c: print(m, "no cycle out", flush=True); continue
        cyc = f"{c:%Y%m%d%H}"; key = f"runs/{m}/{cyc}/run.json"; rd = f"{D}/runs/{m}/{cyc}"; os.makedirs(rd + "/single", exist_ok=True)
        try:
            s3.download_file(BUCKET, key, f"{rd}/run.json"); r0 = json.load(open(f"{rd}/run.json"))
            if r0.get("complete"): print(m, cyc, "complete in R2", flush=True); continue
        except Exception: r0 = None
        print(m, cyc, "has", len((r0 or {}).get("steps", [])), "steps in R2", flush=True)
        want = FE.steps_for(m, c.hour)
        # encode in chunks so the site gets new hours every few minutes (progressive publishing)
        chunk = 12 if m == "hrrr" else 24
        while True:
            if time.time() >= t_end - 60: MORE.add(m); break   # budget ran out with hours left -> ask for a re-dispatch
            have = {x["f"] for x in (json.load(open(f"{rd}/run.json"))["steps"] if os.path.exists(f"{rd}/run.json") else [])}
            nxt = [s for s in want if s not in have][:chunk]
            if not nxt or not avail(m, c, nxt[0]): break
            nxt = [s for s in nxt if avail(m, c, s)] if not avail(m, c, nxt[-1]) else nxt
            run, new = FE.steps(m, cyc, nxt, D, a.workers)
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
                publish_manifest(s3, D, m)
            print(f"{m} {cyc}: uploaded {len(files)} files, {len(ordered)}/{len(want)} steps live", flush=True)
            for f in files: os.remove(f"{D}/{f}")   # keep the runner disk small
            if full["complete"]:
                if not a.dry_run:
                    try: write_agg(s3, m, cyc, full, f"{rd}/run.json", key)
                    except Exception as e: print(m, cyc, "aggregate town files failed (site falls back to per-step files):", e, flush=True)
                break

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


def publish_manifest(s3, D, m):
    keep = FE.MODELS[m]["keep"]
    pre = {o["Prefix"].split("/")[2] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{m}/", Delimiter="/").get("CommonPrefixes", [])}
    present = sorted(r for r in pre if "Contents" in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{m}/{r}/run.json", MaxKeys=1))
    kept = present[-keep:]
    if FE.MODELS[m].get("keep_long"):   # also keep the newest full-length (00/12Z) run so 360 h stays on the site
        longs = [r for r in present if int(r[8:10]) not in FE.MODELS[m].get("short_cycles", ())]
        if longs and longs[-1] not in kept: kept = sorted(kept + [longs[-1]])
    # 10-30 meteograms page multi-run (old site showed 4 runs): the newest MG_KEEP runs keep their small town files
    # (run.json + pts_/mem_ JSON); map images of runs that left the map list are deleted ("slim" runs, marker key .../slim).
    mg = present[-MG_KEEP:]
    def both(mn): mn.setdefault("runs", {})[m] = kept; mn.setdefault("mgruns", {})[m] = sorted(set(mg) | set(kept))
    man = update_manifest(s3, both)
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
