#!/usr/bin/env python3
"""Upload fast-style data to R2 bucket wx-models-data (S3 API; keys derived from the Cloudflare API token in CF_PAGES_KEY,
access key = token id, secret = sha256(token); the token is never printed).
  upload_r2.py --data <site/data> [--run 2026102918] [--static] [--keep 2] [--dry-run]
Order: static (if asked) -> run files -> run.json -> manifest (lists only runs present in R2, newest --keep) -> prune older runs."""
import os, sys, json, hashlib, argparse, urllib.request, mimetypes, time
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config
BUCKET = os.environ.get("R2_BUCKET", "wx-models-data")
CT = {".png": "image/png", ".json": "application/json", ".bin": "application/octet-stream", ".webp": "image/webp"}

def client():
    tok = os.environ["CF_PAGES_KEY"]; acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or os.environ["ACC"]
    rq = urllib.request.Request("https://api.cloudflare.com/client/v4/user/tokens/verify", headers={"Authorization": "Bearer " + tok})
    tid = json.load(urllib.request.urlopen(rq))["result"]["id"]
    return boto3.client("s3", endpoint_url=f"https://{acc}.r2.cloudflarestorage.com", aws_access_key_id=tid,
                        aws_secret_access_key=hashlib.sha256(tok.encode()).hexdigest(), region_name="auto",
                        config=Config(max_pool_connections=32, retries={"max_attempts": 5, "mode": "standard"}))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--run", action="append", default=[])
    ap.add_argument("--static", action="store_true"); ap.add_argument("--keep", type=int, default=2); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="hrrr"); a = ap.parse_args(); D = a.data.rstrip("/")
    s3 = None if a.dry_run else client(); t0 = time.time(); n = [0, 0]
    def put(rel, cache=None):
        p = f"{D}/{rel}"; n[0] += 1; n[1] += os.path.getsize(p)
        if a.dry_run: return
        s3.upload_file(p, BUCKET, rel, ExtraArgs={"ContentType": CT.get(os.path.splitext(p)[1], "application/octet-stream")})
    files = []
    if a.static: files += [f"static/{f}" for f in sorted(os.listdir(f"{D}/static"))]
    for r in a.run:
        rd = f"runs/{a.model}/{r}"; files += [f"{rd}/single/{f}" for f in sorted(os.listdir(f"{D}/{rd}/single")) if f.endswith(".png")]
    with ThreadPoolExecutor(16) as ex: list(ex.map(put, files))
    for r in a.run: put(f"runs/{a.model}/{r}/run.json")
    # manifest: runs = those whose run.json is in R2 (or local in dry run), newest --keep
    if a.dry_run: present = sorted(a.run)
    else:
        present = sorted({o["Prefix"].split("/")[2] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{a.model}/", Delimiter="/").get("CommonPrefixes", [])})
        present = [r for r in present if "Contents" in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{a.model}/{r}/run.json", MaxKeys=1)]
    keep = present[-a.keep:]; man = json.load(open(f"{D}/manifest.json")); man.setdefault("runs", {})[a.model] = keep
    if not a.dry_run:
        s3.put_object(Bucket=BUCKET, Key="manifest.json", Body=json.dumps(man).encode(), ContentType="application/json")
        for old in present[:-a.keep]:   # prune (the lifecycle rule also expires runs/ after 3 days)
            ks = [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"runs/{a.model}/{old}/") for o in pg.get("Contents", [])]
            for i in range(0, len(ks), 1000): s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in ks[i:i + 1000]]})
            print("pruned", old, len(ks), "objects")
    print(f"{'DRY RUN ' if a.dry_run else ''}uploaded {n[0]} files, {n[1]/1e6:.1f} MB in {time.time()-t0:.1f} s; manifest runs {keep}")
if __name__ == "__main__": main()
