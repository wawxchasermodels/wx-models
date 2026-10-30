#!/usr/bin/env python3
"""Box-side: upload static layers + the models part of manifest.json to R2, keeping the runs lists already in R2.
  publish_static.py --data ../data [--runs-from-local]"""
import os, sys, json, argparse
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_r2 import client, BUCKET, CT
ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--runs-from-local", action="store_true"); a = ap.parse_args()
s3 = client(); D = a.data.rstrip("/")
fs = [f"static/{f}" for f in sorted(os.listdir(f"{D}/static"))]
with ThreadPoolExecutor(16) as ex: list(ex.map(lambda k: s3.upload_file(f"{D}/{k}", BUCKET, k, ExtraArgs={"ContentType": CT.get(os.path.splitext(k)[1], "application/octet-stream")}), fs))
man = json.load(open(f"{D}/manifest.json"))
if not a.runs_from_local:
    try: man["runs"] = json.loads(s3.get_object(Bucket=BUCKET, Key="manifest.json")["Body"].read()).get("runs", {})
    except Exception: man["runs"] = {}
import time; man["static_v"] = time.strftime("%Y%m%d%H%M%S", time.gmtime())   # viewer cache-buster for static/
for m in man.get("models", {}): man.setdefault("runs", {}).setdefault(m, [])
s3.put_object(Bucket=BUCKET, Key="manifest.json", Body=json.dumps(man).encode(), ContentType="application/json")
print(f"static {len(fs)} files; manifest models {list(man['models'])} runs { {k: v for k, v in man['runs'].items()} }")
