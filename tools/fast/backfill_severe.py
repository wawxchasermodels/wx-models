#!/usr/bin/env python3
"""Box-side: add the Severe tab fields (uh, cape3, srh03 -> pack "svr"; lr03, lr75 -> pack "lapse") to an already published,
COMPLETE HRRR / RRFS run, without re-uploading its other images (10-31-26). Writes only the new pack PNGs
(runs/<m>/<cycle>/single/{svr,lapse}_fFFF.png, new keys) and then run.json with their ranges / packs merged in.
Backup of the old run.json in --backup. Rollback: upload the backup run.json (the new PNGs are then just unused).
  backfill_severe.py --model hrrr --cycle 2026103112 --backup DIR [--workers 4] [--dry-run]
Env: CF_PAGES_KEY, CLOUDFLARE_ACCOUNT_ID. Run with python3 (encoder); uploads go through a subprocess on the R2 venv if boto3 is missing."""
import os, sys, json, argparse, shutil, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE
NEW = ("uh", "cape3", "srh03", "lr03", "lr75")
ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--cycle", required=True); ap.add_argument("--backup", required=True)
ap.add_argument("--workers", type=int, default=4); ap.add_argument("--work", default="/tmp/bf_severe"); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
m, cyc = a.model, a.cycle; W = f"{a.work}/{m}"; shutil.rmtree(W, ignore_errors=True); os.makedirs(f"{W}/runs/{m}/{cyc}/single", exist_ok=True)
D = "https://fast.invalid"
import urllib.request
def r2get(key, dest): subprocess.run([R2PY, "-c", f"import sys; sys.path.insert(0, {HERE!r}); from upload_r2 import client, BUCKET; client().download_file(BUCKET, {key!r}, {dest!r})"], check=True)
R2PY = os.environ.get("R2_PY", "/workspace/.venv-r2/bin/python")
r2get("manifest.json", f"{W}/manifest.json"); r2get(f"runs/{m}/{cyc}/run.json", f"{W}/run_old.json")
old = json.load(open(f"{W}/run_old.json")); assert old.get("complete"), "run not complete in R2 (the workflow still owns it)"
os.makedirs(a.backup, exist_ok=True); shutil.copy(f"{W}/run_old.json", f"{a.backup}/{m}_{cyc}_run.json")
FE.FIELDS = {k: v for k, v in FE.FIELDS.items() if k in NEW or k == "t2m"}   # t2m: steps() needs it; its PNG is not uploaded
run, new = FE.steps(m, cyc, [x["f"] for x in old["steps"]], W, a.workers)
by = {x["f"]: x for x in run["steps"]}; miss = [x["f"] for x in old["steps"] if x["f"] not in by]
assert not miss, f"steps failed: {miss}"
for x in old["steps"]:
    n = by[x["f"]]; x["ranges"].update({k: v for k, v in n["ranges"].items() if k in NEW})
    x.setdefault("packs", {}).update({k: v for k, v in n.get("packs", {}).items() if k in NEW})
old["fields"] = sorted(set(old["fields"]) | {k for x in old["steps"] for k in x["ranges"] if k in NEW})
json.dump(old, open(f"{W}/run_new.json", "w"), indent=1)
files = sorted(f for f in os.listdir(f"{W}/runs/{m}/{cyc}/single") if f.startswith(("svr_", "lapse_")))
tot = sum(os.path.getsize(f"{W}/runs/{m}/{cyc}/single/{f}") for f in files)
print(f"{m} {cyc}: {len(files)} new PNGs, {tot / 1e6:.1f} MB; fields now {len(old['fields'])}", flush=True)
if a.dry_run: sys.exit(0)
up = [(f"{W}/runs/{m}/{cyc}/single/{f}", f"runs/{m}/{cyc}/single/{f}", "image/png") for f in files] + [(f"{W}/run_new.json", f"runs/{m}/{cyc}/run.json", "application/json")]
code = f"""
import sys, json; sys.path.insert(0, {HERE!r}); from upload_r2 import client, BUCKET
from concurrent.futures import ThreadPoolExecutor
s3 = client(); up = json.loads({json.dumps(json.dumps(up))})
r0 = json.loads(s3.get_object(Bucket=BUCKET, Key=up[-1][1])["Body"].read()); assert r0.get("complete")
with ThreadPoolExecutor(16) as ex: list(ex.map(lambda t: s3.upload_file(t[0], BUCKET, t[1], ExtraArgs={{"ContentType": t[2]}}), up[:-1]))
s3.upload_file(up[-1][0], BUCKET, up[-1][1], ExtraArgs={{"ContentType": up[-1][2]}}); print("uploaded", len(up), "objects")
"""
subprocess.run([R2PY, "-c", code], check=True)
