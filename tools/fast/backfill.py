#!/usr/bin/env python3
"""Re-encode runs already in R2 (box or Actions; R2 only, never the Pages projects or the live site).
Used when fields / town points were added after a run finished: the cron skips complete runs, so they would wait for the next cycle.
  backfill.py hrrr/2026103018 aifs/2026103012 ... [--workers 4] [--out data_bf]
Re-encodes the steps listed in the run's R2 run.json, uploads the step files + pts JSONs, then run.json (complete flag kept)."""
import os, sys, json, argparse, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE
from upload_r2 import client, BUCKET
from concurrent.futures import ThreadPoolExecutor
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("runs", nargs="+"); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(HERE, "data_bf")); a = ap.parse_args(); D = a.out; os.makedirs(D, exist_ok=True)
    s3 = client(); s3.download_file(BUCKET, "manifest.json", f"{D}/manifest.json")
    for r in a.runs:
        m, cyc = r.split("/"); key = f"runs/{m}/{cyc}/run.json"
        r0 = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()); fs = [x["f"] for x in r0["steps"]]
        rd = f"{D}/runs/{m}/{cyc}"; shutil.rmtree(rd, ignore_errors=True); os.makedirs(rd + "/single")
        run, new = FE.steps(m, cyc, fs, D, a.workers, only_missing=False)
        if len(run["steps"]) < len(r0["steps"]): print(r, "re-encode came up short", len(run["steps"]), "of", len(r0["steps"]), "- not uploaded", flush=True); continue
        run["complete"] = r0.get("complete", run["complete"]); run["expected"] = r0.get("expected", run["expected"])
        json.dump(run, open(f"{rd}/run.json", "w"), indent=1)
        files = [f"runs/{m}/{cyc}/single/{f}" for f in os.listdir(f"{rd}/single")]
        with ThreadPoolExecutor(16) as ex: list(ex.map(lambda k: s3.upload_file(f"{D}/{k}", BUCKET, k, ExtraArgs={"ContentType": "application/json" if k.endswith(".json") else "image/png"}), files))
        s3.upload_file(f"{rd}/run.json", BUCKET, key, ExtraArgs={"ContentType": "application/json"})
        print(r, "backfilled:", len(files), "files, fields", ",".join(run["fields"]), flush=True); shutil.rmtree(rd)
if __name__ == "__main__":
    main(); sys.stdout.flush(); os._exit(0)
