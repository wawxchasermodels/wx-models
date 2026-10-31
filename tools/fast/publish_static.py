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
loc = json.load(open(f"{D}/manifest.json"))
import time; sv = time.strftime("%Y%m%d%H%M%S", time.gmtime())   # viewer cache-buster for static/
def merge(man):   # keep the runs lists in R2 (the Actions jobs own them); ETag-checked write, see fast_cycle.update_manifest
    runs = loc.get("runs", {}) if a.runs_from_local else man.get("runs", {})
    mgr = man.get("mgruns", {})   # meteograms page run lists (fast_cycle owns them too)
    man.clear(); man.update(loc); man["runs"] = dict(runs); man["static_v"] = sv
    if mgr: man["mgruns"] = dict(mgr)
    for m in man.get("models", {}): man["runs"].setdefault(m, [])
from fast_cycle import update_manifest
man = update_manifest(s3, merge)
print(f"static {len(fs)} files; manifest models {list(man['models'])} runs { {k: v for k, v in man['runs'].items()} }")
