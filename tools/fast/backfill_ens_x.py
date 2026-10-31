#!/usr/bin/env python3
"""Box-side (10-31-26, 06Z/18Z ensembles, hidden preview before a push): encode one whole 06Z/18Z EPS or AIFS ENS run and put it
in R2 WITHOUT the production page seeing it: step files go to runs/<m>/<cycle>/single/ as usual, but the run file is run_x.json
and the cycle is listed in manifest "runs_x" (only the new viewer / meteograms page read those). The pushed workflow only lists
runs that have a run.json, so it never shows or prunes these; once the new fast_cycle.py runs, it drops runs_x and deletes them.
  backfill_ens_x.py eps/2026103106 aens/2026103106 [--workers 3] [--out /workspace/ens_x] [--dry-run]
Env: CF_PAGES_KEY, CLOUDFLARE_ACCOUNT_ID. Run with python3 (encoder); R2 work goes through the R2 venv (R2_PY)."""
import os, sys, json, argparse, shutil, subprocess, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE
R2PY = os.environ.get("R2_PY", "/workspace/.venv-r2/bin/python")
def r2(code): subprocess.run([R2PY, "-c", f"import sys, json; sys.path.insert(0, {HERE!r}); from upload_r2 import client, BUCKET; s3 = client()\n" + code], check=True)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("runs", nargs="+"); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default="/workspace/ens_x"); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    D = a.out; os.makedirs(D, exist_ok=True); r2(f"s3.download_file(BUCKET, 'manifest.json', {D + '/manifest.json'!r})")
    for r in a.runs:
        m, cyc = r.split("/"); assert m in ("eps", "aens"), m
        want = FE.steps_for(m, int(cyc[8:10])); rd = f"{D}/runs/{m}/{cyc}"; shutil.rmtree(rd, ignore_errors=True); os.makedirs(rd + "/single")
        run, new = FE.steps(m, cyc, want, D, a.workers, only_missing=False)
        if len(run["steps"]) != len(want): print(r, "came up short", len(run["steps"]), "of", len(want), "- not uploaded", flush=True); continue
        run.update(complete=True, expected=len(want)); agg = []
        for name in ("pts", "mem"):   # same aggregate files as fast_cycle.write_agg (meteograms / Pass table fetch 1 file)
            fs = [x["f"] for x in run["steps"]]; ps = [f"{rd}/single/{name}_f{f:03d}.json" for f in fs]
            if all(os.path.exists(p) for p in ps):
                json.dump({"f": fs, "d": [json.load(open(p)) for p in ps]}, open(f"{rd}/single/{name}_all.json", "w"), separators=(",", ":")); agg.append(name)
        if agg: run["agg"] = agg
        os.remove(f"{rd}/run.json") if os.path.exists(f"{rd}/run.json") else None
        json.dump(run, open(f"{rd}/run_x.json", "w"), indent=1)
        files = sorted(os.listdir(f"{rd}/single")); mb = sum(os.path.getsize(f"{rd}/single/{f}") for f in files) / 1e6
        print(r, "encoded", len(run["steps"]), "steps,", len(files), "files,", f"{mb:.1f} MB, fields", ",".join(run["fields"]), flush=True)
        if a.dry_run: continue
        up = [(f"{rd}/single/{f}", f"runs/{m}/{cyc}/single/{f}", "application/json" if f.endswith(".json") else "image/png") for f in files]
        up.append((f"{rd}/run_x.json", f"runs/{m}/{cyc}/run_x.json", "application/json"))
        json.dump(up, open(f"{rd}/up.json", "w"))
        r2(f"""
from concurrent.futures import ThreadPoolExecutor
import time, random
up = json.load(open({rd + '/up.json'!r}))
with ThreadPoolExecutor(16) as ex: list(ex.map(lambda t: s3.upload_file(t[0], BUCKET, t[1], ExtraArgs={{"ContentType": t[2]}}), up))
for i in range(8):   # ETag-checked manifest write (same as fast_cycle.update_manifest)
    o = s3.get_object(Bucket=BUCKET, Key="manifest.json"); man = json.loads(o["Body"].read())
    if {cyc!r} in (man.get("runs", {{}}).get({m!r}) or []): print("already a regular run; manifest unchanged"); break
    rx = man.setdefault("runs_x", {{}}); rx[{m!r}] = sorted(set(rx.get({m!r}, [])) | {{{cyc!r}}})
    try: s3.put_object(Bucket=BUCKET, Key="manifest.json", Body=json.dumps(man).encode(), ContentType="application/json", IfMatch=o["ETag"]); print("manifest runs_x", man["runs_x"]); break
    except Exception as e:
        if "PreconditionFailed" not in str(e) and "412" not in str(e): raise
        time.sleep(0.5 + random.random() * 2)
print("uploaded", len(up), "objects")
""")
        shutil.rmtree(rd + "/single")
if __name__ == "__main__":
    main(); sys.stdout.flush(); os._exit(0)
