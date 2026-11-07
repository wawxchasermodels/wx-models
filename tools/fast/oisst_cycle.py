#!/usr/bin/env python3
"""11-03 (Benjamin t2184u "push and deploy"): fast-models job for NOAA OISST v2.1 SST anomaly ("oisst", public domain).
Newest daily analysis out at NCEI -> if R2 has no run for that 14-day window yet: oisst.py builds it (14 x ~1.5 MB downloads) -> upload
(images first, run.json last) -> manifest runs.oisst = [that run] (ETag-checked) -> older oisst runs deleted. Static layers / LUTs /
keys and manifest models.oisst were written once from the box.
  oisst_cycle.py"""
import os, sys, json, tempfile, subprocess, datetime as dt, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from upload_r2 import client, BUCKET
from fast_cycle import update_manifest
import oisst as O

def newest():
    d = dt.datetime.utcnow().date()
    for _ in range(6):
        for sfx in ("", "_preliminary"):
            try: urllib.request.urlopen(urllib.request.Request(O.URL.format(d=d, sfx=sfx), method="HEAD"), timeout=30); return d
            except Exception: pass
        d -= dt.timedelta(days=1)
    return None

def main():
    s3 = client(); d = newest(); print("newest OISST day:", d, flush=True)
    if not d: return
    tmp = tempfile.mkdtemp(); man = json.loads(s3.get_object(Bucket=BUCKET, Key="manifest.json")["Body"].read())
    json.dump(man, open(f"{tmp}/manifest.json", "w"))
    cyc = f"{d - dt.timedelta(days=13):%Y%m%d}00"
    try: s3.head_object(Bucket=BUCKET, Key=f"runs/oisst/{cyc}/run.json"); have = True
    except Exception: have = False
    if not have:
        subprocess.run([sys.executable, os.path.join(HERE, "oisst.py"), "--out", tmp, "--days", "14", "--end", f"{d:%Y%m%d}", "--cache", f"{tmp}/cache"], check=False)
        rd = f"{tmp}/runs/oisst/{cyc}"
        if not os.path.exists(f"{rd}/run.json"): print("no run built for", cyc, flush=True); return
        for f in sorted(os.listdir(f"{rd}/single")): s3.upload_file(f"{rd}/single/{f}", BUCKET, f"runs/oisst/{cyc}/single/{f}", ExtraArgs={"ContentType": "image/png"})
        s3.upload_file(f"{rd}/run.json", BUCKET, f"runs/oisst/{cyc}/run.json", ExtraArgs={"ContentType": "application/json"})
        print("uploaded oisst", cyc, flush=True)
    def fn(mn): mn.setdefault("runs", {})["oisst"] = [cyc]
    update_manifest(s3, fn); print("manifest runs.oisst", [cyc], flush=True)
    pre = [o["Prefix"].split("/")[2] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="runs/oisst/", Delimiter="/").get("CommonPrefixes", [])]
    for old in [r for r in pre if r != cyc]:
        while True:
            ks = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/oisst/{old}/").get("Contents", [])]
            if not ks: break
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in ks]})
        print("pruned oisst", old, flush=True)
if __name__ == "__main__":
    main(); sys.stdout.flush(); os._exit(0)
