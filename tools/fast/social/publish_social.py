#!/usr/bin/env python3
"""Publish rendered social frames (make_social.py output) for the fast site's Social tab.
  python3 publish_social.py thumbs <out>/<run>              (system python: PIL) -> <out>/<run>/jpg/*.jpg  (1280 px long side previews)
  <R2 venv python> publish_social.py upload <out>/<run> [--keep 2]
R2 layout: social/<run>/<name>.png (4K PNG), social/<run>/jpg/<name>.jpg, social/index.json
  {"runs": [newest first], "items": {run: {"prods": [...], "views": [...], "hours": [...], "aspects": ["v","h"]}}, "updated": iso}
Only the social/ prefix is touched (the map viewer never reads it); runs beyond --keep are deleted."""
import os, sys, json, glob, time, datetime as dt
mode, d = sys.argv[1], sys.argv[2].rstrip("/")
run = os.path.basename(d)
if mode == "thumbs":
    from PIL import Image
    os.makedirs(f"{d}/jpg", exist_ok=True)
    for p in sorted(glob.glob(f"{d}/*.png")):
        o = f"{d}/jpg/" + os.path.basename(p)[:-4] + ".jpg"
        if os.path.exists(o) and os.path.getmtime(o) >= os.path.getmtime(p): continue
        im = Image.open(p).convert("RGB"); k = 1280 / max(im.size); im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS).save(o, quality=86)
    print("thumbs", len(glob.glob(f"{d}/jpg/*.jpg"))); sys.exit()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import upload_r2 as U
from concurrent.futures import ThreadPoolExecutor
keep = int(sys.argv[sys.argv.index("--keep") + 1]) if "--keep" in sys.argv else 2
s3 = U.client(); B = U.BUCKET
files = [(p, f"social/{run}/" + os.path.relpath(p, d)) for p in glob.glob(f"{d}/*.png") + glob.glob(f"{d}/jpg/*.jpg")]
def put(a): s3.upload_file(a[0], B, a[1], ExtraArgs={"ContentType": "image/png" if a[0].endswith(".png") else "image/jpeg"})
t0 = time.time()
with ThreadPoolExecutor(16) as ex: list(ex.map(put, files))
names = [os.path.basename(p)[:-4] for p in glob.glob(f"{d}/*.png")]
parts = [n.split("_") for n in names]   # prod_view_fHHH_k
item = dict(prods=sorted({p[0] for p in parts}), views=sorted({p[1] for p in parts}), hours=sorted({int(p[2][1:]) for p in parts}), aspects=["v", "h"],
            files=sorted(names))
try: idx = json.loads(s3.get_object(Bucket=B, Key="social/index.json")["Body"].read())
except Exception: idx = {"runs": [], "items": {}}
idx["items"][run] = item; idx["runs"] = sorted(set(idx["runs"]) | {run}, reverse=True)
for old in idx["runs"][keep:]:
    ks = [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=f"social/{old}/") for o in pg.get("Contents", [])]
    for i in range(0, len(ks), 1000): s3.delete_objects(Bucket=B, Delete={"Objects": [{"Key": k} for k in ks[i:i + 1000]]})
    idx["items"].pop(old, None); print("pruned", old, len(ks))
idx["runs"] = idx["runs"][:keep]; idx["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
s3.put_object(Bucket=B, Key="social/index.json", Body=json.dumps(idx).encode(), ContentType="application/json", CacheControl="no-cache")
print("uploaded", len(files), "files in", round(time.time() - t0, 1), "s; runs", idx["runs"])
