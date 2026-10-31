#!/usr/bin/env python3
"""Read the website change-request queue ("Request a change" box -> /req -> R2 requests/). Read-only unless --mark.
  read_requests.py              newest 20 (time PT, who, page, state, text)
  read_requests.py --json       the same as JSON
  read_requests.py --mark KEY done|seen|queued   set a request's status (shown in the box's recent list)
Env: CF_PAGES_KEY, CLOUDFLARE_ACCOUNT_ID (same as upload_r2.py)."""
import sys, json, argparse, datetime as dt, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_r2 import client, BUCKET
ap = argparse.ArgumentParser(); ap.add_argument("--json", action="store_true"); ap.add_argument("-n", type=int, default=20); ap.add_argument("--mark", nargs=2)
a = ap.parse_args(); s3 = client()
if a.mark:
    k, stt = a.mark; r = json.loads(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()); r["status"] = stt
    s3.put_object(Bucket=BUCKET, Key=k, Body=json.dumps(r, indent=1).encode(), ContentType="application/json"); print("marked", k, stt); sys.exit()
keys = sorted((o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="requests/") for o in pg.get("Contents", [])), reverse=True)[: a.n]
items = [dict(key=k, **json.loads(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read())) for k in keys]
if a.json: print(json.dumps(items, indent=1)); sys.exit()
for r in items:
    t = dt.datetime.fromisoformat(r["time"].replace("Z", "+00:00")).astimezone(dt.timezone(dt.timedelta(hours=-7)))
    print(f"[{r.get('status','queued')}] {t:%a %m-%d %I:%M %p} PT  {r.get('who','')}  {r.get('page','')}  {json.dumps(r.get('state',{}))[:200]}\n    {r['text']}\n    key={r['key']}")
if not items: print("no requests")
