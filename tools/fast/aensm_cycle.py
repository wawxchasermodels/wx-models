#!/usr/bin/env python3
"""11-03 (Benjamin t2176u "Push and deploy"): GitHub Actions job for AIFS ENS single members ("aensm", fast-models.yml matrix).
Progressive, resumable: newest AIFS ENS cycle(s) out on data.ecmwf.int -> the hours not yet in R2 (aens_members.one: msl + z500 byte
ranges, 50 lossless 0.5 deg WebP per hour) -> upload -> run.json (unbroken hours from F+6) -> manifest runs.aensm = newest 2 runs in R2
(ETag-checked) -> older aensm runs deleted. Manifest models.aensm (static entry) is written once from the box.
  aensm_cycle.py --minutes 40 --workers 4"""
import os, sys, json, time, argparse, datetime as dt, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "forecast"))
import aens_members as AM
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

def run_json(c, steps_meta, mems, crop):
    import temp_maps as TM; PT = TM.PT; i0, i1, j0, j1 = crop
    return dict(model="aensm", cycle=f"{c:%Y%m%d%H}", init=c.isoformat(), base=f"runs/aensm/{c:%Y%m%d%H}", fields=["mslp", "z500"], grid=dict(ny=i1 - i0, nx=j1 - j0),
                half=[(i1 - i0 + 1) // 2, (j1 - j0 + 1) // 2], members=mems,
                runline=f"ECMWF AIFS ENS member {{mem}} 0.5\u00b0 {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}", steps=steps_meta,
                complete=len(steps_meta) == len(AM.STEPS), expected=len(AM.STEPS), file="m{mem}/{name}_f{f:03d}.webp")

def step_meta(c, s):
    import temp_maps as TM; PT = TM.PT; v = c + dt.timedelta(hours=s); vl = v.astimezone(PT)
    return dict(f=s, valid=v.isoformat(), valid_line=f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT", badge=[f"F+{s}", f"{v:%HZ %a}".upper()],
                ranges=dict(AM.RNG), packs={"mslp": ["mem", 0], "z500": ["mem", 1]})

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=float, default=40); ap.add_argument("--workers", type=int, default=4); a = ap.parse_args()
    t_end = time.time() + a.minutes * 60; s3 = client(); more = False
    man = r2_json(s3, "manifest.json"); crop = man["models"]["aens"]["crop"]   # same crop as aens_members.py
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    cycles = [c for c in (now - dt.timedelta(hours=b) for b in range(0, 36)) if c.hour % 6 == 0 and src_has(c, AM.STEPS[0])][:KEEP]
    print("cycles out:", [f"{c:%Y%m%d%H}" for c in cycles], flush=True)
    from concurrent.futures import ProcessPoolExecutor
    for c in sorted(cycles):   # older first: finish it, then the newest
        cyc = f"{c:%Y%m%d%H}"; R = r2_json(s3, f"runs/aensm/{cyc}/run.json") or {}
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
                        p = f"{tmp}/m{n:02d}/mem_f{s:03d}.webp"; s3.upload_file(p, BUCKET, f"runs/aensm/{cyc}/m{n:02d}/mem_f{s:03d}.webp", ExtraArgs={"ContentType": "image/webp"}); os.remove(p)
                    meta[s] = step_meta(c, s); mems = sorted(set(mems) & set(info["members"])) if mems else list(info["members"])   # members present at every hour
                    print(cyc, f"f{s:03d}", len(info["members"]), "members", f"{info['size']/1e3:.0f} KB", f"{info['sec']} s", flush=True)
                steps = []
                for s in AM.STEPS:
                    if s in meta: steps.append(meta[s])
                    else: break
                if steps: s3.put_object(Bucket=BUCKET, Key=f"runs/aensm/{cyc}/run.json", Body=json.dumps(run_json(c, steps, mems, crop)).encode(), ContentType="application/json")
        shutil.rmtree(tmp, ignore_errors=True)
        if time.time() > t_end - 300: more = True
        if more: break
    # manifest: newest KEEP runs whose run.json is in R2; prune the rest
    pre = sorted(o["Prefix"].split("/")[2] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="runs/aensm/", Delimiter="/").get("CommonPrefixes", []))
    present = [r for r in pre if r2_json(s3, f"runs/aensm/{r}/run.json")]
    kept = present[-KEEP:]
    def fn(mn): mn.setdefault("runs", {})["aensm"] = kept
    update_manifest(s3, fn); print("manifest runs.aensm", kept, flush=True)
    for old in [r for r in pre if r not in kept]:
        while True:
            ks = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/aensm/{old}/").get("Contents", [])]
            if not ks: break
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in ks]})
        print("pruned aensm", old, flush=True)
    if not more:   # a cycle still incomplete at the source counts as more work only if its source has the next hour
        for c in cycles:
            R = r2_json(s3, f"runs/aensm/{c:%Y%m%d%H}/run.json") or {}
            if not R.get("complete") and src_has(c, AM.STEPS[len(R.get("steps", []))] if len(R.get("steps", [])) < len(AM.STEPS) else AM.STEPS[-1]): more = True
    print("more work left:", more, flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f: f.write(f"more={'true' if more else 'false'}\n")
if __name__ == "__main__":
    main(); sys.stdout.flush(); os._exit(0)   # eccodes can abort at interpreter exit ("double free"); everything is written by now
