#!/usr/bin/env python3
"""11-03 (Benjamin t2209u, member-number lookup): GitHub Actions job for ECMWF EPS single members ("epsm", fast-models.yml matrix).
Copy of aensm_cycle.py for the EPS: 00Z and 12Z runs only (06Z/18Z EPS stops at F+144). Progressive, resumable: newest EPS cycle(s)
out on data.ecmwf.int -> the hours not yet in R2 (eps_members.one: msl + gh500 + 10fg + sf byte ranges, 50 lossless 0.5 deg 2-tile WebP
per hour) -> upload -> run.json (unbroken hours from F+6) -> manifest runs.epsm = newest 2 runs in R2 (ETag-checked) -> older epsm runs
deleted. Manifest models.epsm (static entry) is written once from the box.
  epsm_cycle.py --minutes 40 --workers 4"""
import os, sys, json, time, argparse, datetime as dt, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "forecast"))
import eps_members as AM
from upload_r2 import client, BUCKET
from fast_cycle import update_manifest
KEEP = 2

def src_has(c, s):
    import temp_maps as TM
    for u in AM.SRC:
        try: TM.get(u.format(d=f"{c:%Y%m%d}", h=c.hour, s=s) + ".index", (0, 10)); return True
        except Exception: pass
    return False

def r2_json(s3, k):
    try: return json.loads(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read())
    except Exception: return None

run_json, step_meta = AM.run_json, AM.step_meta

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=float, default=40); ap.add_argument("--workers", type=int, default=4); a = ap.parse_args()
    t_end = time.time() + a.minutes * 60; s3 = client(); more = False
    man = r2_json(s3, "manifest.json"); crop = man["models"]["eps"]["crop"]   # same crop as eps_members.py
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    cycles = [c for c in (now - dt.timedelta(hours=b) for b in range(0, 48)) if c.hour % 12 == 0 and src_has(c, AM.STEPS[0])][:KEEP]
    print("cycles out:", [f"{c:%Y%m%d%H}" for c in cycles], flush=True)
    from concurrent.futures import ProcessPoolExecutor
    for c in sorted(cycles):   # older first: finish it, then the newest
        cyc = f"{c:%Y%m%d%H}"; R = r2_json(s3, f"runs/epsm/{cyc}/run.json") or {}
        have = {x["f"] for x in R.get("steps", [])}; mems = R.get("members") or []
        todo = [s for s in AM.STEPS if s not in have]
        if not todo: print(cyc, "complete in R2", flush=True); continue
        tmp = tempfile.mkdtemp(); meta = {x["f"]: x for x in R.get("steps", [])}
        with ProcessPoolExecutor(a.workers) as ex:
            for k in range(0, len(todo), a.workers):
                if time.time() > t_end - 300: more = True; break
                batch = [s for s in todo[k:k + a.workers] if src_has(c, s)]
                if not batch: break
                for s, info, err in ex.map(AM.one, [(c, s, crop, tmp) for s in batch]):
                    if err: print(cyc, f"f{s:03d}", err, flush=True); continue
                    for n in info["members"]:
                        p = f"{tmp}/m{n:02d}/mem_f{s:03d}.webp"; s3.upload_file(p, BUCKET, f"runs/epsm/{cyc}/m{n:02d}/mem_f{s:03d}.webp", ExtraArgs={"ContentType": "image/webp"}); os.remove(p)
                    meta[s] = step_meta(c, s); mems = sorted(set(mems) & set(info["members"])) if mems else list(info["members"])   # members present at every hour
                    print(cyc, f"f{s:03d}", len(info["members"]), "members", f"{info['size']/1e3:.0f} KB", f"{info['sec']} s", flush=True)
                steps = []
                for s in AM.STEPS:
                    if s in meta: steps.append(meta[s])
                    else: break
                if steps: s3.put_object(Bucket=BUCKET, Key=f"runs/epsm/{cyc}/run.json", Body=json.dumps(run_json(c, steps, mems, crop)).encode(), ContentType="application/json")
        shutil.rmtree(tmp, ignore_errors=True)
        if time.time() > t_end - 300: more = True
        if more: break
    # manifest: newest KEEP runs whose run.json is in R2; prune the rest
    pre = sorted(o["Prefix"].split("/")[2] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="runs/epsm/", Delimiter="/").get("CommonPrefixes", []))
    present = [r for r in pre if r2_json(s3, f"runs/epsm/{r}/run.json")]
    kept = present[-KEEP:]
    def fn(mn): mn.setdefault("runs", {})["epsm"] = kept
    update_manifest(s3, fn); print("manifest runs.epsm", kept, flush=True)
    for old in [r for r in pre if r not in kept]:
        while True:
            ks = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/epsm/{old}/").get("Contents", [])]
            if not ks: break
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in ks]})
        print("pruned epsm", old, flush=True)
    if not more:   # a cycle still incomplete at the source counts as more work only if its source has the next hour
        for c in cycles:
            R = r2_json(s3, f"runs/epsm/{c:%Y%m%d%H}/run.json") or {}
            if not R.get("complete") and src_has(c, AM.STEPS[len(R.get("steps", []))] if len(R.get("steps", [])) < len(AM.STEPS) else AM.STEPS[-1]): more = True
    print("more work left:", more, flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f: f.write(f"more={'true' if more else 'false'}\n")
if __name__ == "__main__":
    main(); sys.stdout.flush(); os._exit(0)   # eccodes can abort at interpreter exit ("double free"); everything is written by now
