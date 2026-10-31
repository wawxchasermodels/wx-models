#!/usr/bin/env python3
"""Box-side (10-31-26, Severe tab): publish products that a static --x2-only build wrote to <src>/products_x_<m>.json
(+ their color keys static/key_<m>_<pid>_<view>.png) as manifest models[m]["products_x"]. Only the new viewer reads products_x,
so the production page's product list is unchanged. Also merged into the box copy of the static data (--data) so a later
publish_static.py keeps them. ETag-checked manifest write (fast_cycle.update_manifest). Run with the R2 venv python.
  publish_products_x.py --src /workspace/st_sev --models hrrr,rrfs --data ../../fast_deploy/data [--dry-run]
10-31: products are now MERGED into an existing products_x (not replaced), and if the build ran with WX_X2_CLIM it also merges
<src>/<m>/clim_<m>.json into models[m]["clim"] and uploads those climatology PNGs (MSLP anomaly needs clim "slp")."""
import os, sys, json, argparse, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_r2 import client, BUCKET
def update_manifest(s3, fn, tries=8):   # same as fast_cycle.update_manifest (that module needs numpy; this runs on the R2 venv)
    import time, random
    for i in range(tries):
        o = s3.get_object(Bucket=BUCKET, Key="manifest.json"); man = json.loads(o["Body"].read()); fn(man)
        try:
            s3.put_object(Bucket=BUCKET, Key="manifest.json", Body=json.dumps(man).encode(), ContentType="application/json", IfMatch=o["ETag"]); return man
        except Exception as e:
            if "PreconditionFailed" not in str(e) and "412" not in str(e): raise
            time.sleep(0.5 + random.random() * 2)
    raise SystemExit("manifest.json kept changing; gave up")
ap = argparse.ArgumentParser(); ap.add_argument("--src", required=True); ap.add_argument("--models", required=True); ap.add_argument("--data")
ap.add_argument("--backup"); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
s3 = client(); PX = {}; CL = {}; up = []
for m in a.models.split(","):
    px = json.load(open(f"{a.src}/{m}/products_x_{m}.json")); PX[m] = px
    for pid, P in px.items():
        for vid, fn in P["keys"].items(): assert os.path.exists(f"{a.src}/{m}/{fn}"), fn; up.append((m, fn))
    print(m, "products_x:", list(px), "keys", sum(len(P["keys"]) for P in px.values()))
    cf = f"{a.src}/{m}/clim_{m}.json"
    if os.path.exists(cf):
        CL[m] = json.load(open(cf))
        for var, C in CL[m].items():
            for fn in C["files"]: assert os.path.exists(f"{a.src}/{m}/{fn}"), fn; up.append((m, fn))
        print(m, "clim:", list(CL[m]))
if a.dry_run: sys.exit(0)
if a.backup:
    os.makedirs(a.backup, exist_ok=True); s3.download_file(BUCKET, "manifest.json", f"{a.backup}/manifest_before.json")
for m, fn in up: s3.upload_file(f"{a.src}/{m}/{fn}", BUCKET, fn, ExtraArgs={"ContentType": "image/png"})
def merge(man):
    for m, px in PX.items(): man["models"][m].setdefault("products_x", {}).update(px)
    for m, cl in CL.items(): man["models"][m].setdefault("clim", {}).update(cl)
update_manifest(s3, merge); print("manifest: products_x merged for", list(PX), "; clim merged for", list(CL), "; uploaded", len(up), "files")
if a.data and os.path.exists(f"{a.data}/manifest.json"):
    loc = json.load(open(f"{a.data}/manifest.json"))
    for m, px in PX.items():
        if m in loc.get("models", {}): loc["models"][m].setdefault("products_x", {}).update(px)
    for m, cl in CL.items():
        if m in loc.get("models", {}): loc["models"][m].setdefault("clim", {}).update(cl)
    json.dump(loc, open(f"{a.data}/manifest.json", "w"), separators=(",", ":"))
    for m, fn in up: os.makedirs(os.path.dirname(f"{a.data}/{fn}"), exist_ok=True); shutil.copy(f"{a.src}/{m}/{fn}", f"{a.data}/{fn}")
    print("box static copy updated:", a.data)
