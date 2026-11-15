#!/usr/bin/env python3
"""Retry missing years for MUR / Geo-Polar / OISST point series. Tries the year, then two halves."""
from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_sst_hires as F

OUT = sys.argv[1] if len(sys.argv)>1 else "/tmp/sst_work/hires"
PRODS = [p for p in (sys.argv[2].split(",") if len(sys.argv)>2 else ["mur","geopolar_dn","geopolar_n","oisst"])]
ENDD = "2026-11-13"
EXPECT = {y: (366 if (y%4==0 and y!=2026) else 365) for y in range(2019,2026)}
EXPECT[2026] = 317

def have_year(series, y):
    return sum(1 for d in series if d.startswith(str(y)))

def fetch_range(prod, cfg, pix, t0, t1):
    ser = F.fetch_series(prod, cfg["ds"], cfg["var"], pix["lat"], pix["lon"], t0, t1, cfg.get("zlev"))
    if prod=="oisst" and t1.startswith("2026"):
        try:
            nrt = F.fetch_series(prod, cfg["nrt"], cfg["var"], pix["lat"], pix["lon"], "2026-10-01T12:00:00Z", t1, True)
            ser.update(nrt)
        except Exception as e:
            print("  NRT skip", e)
    return ser

def main():
    for prod in PRODS:
        cfg = F.PRODUCTS[prod]
        pixs = (F.loadj(os.path.join(OUT,"pixels.json")) or {}).get(prod) or {}
        start_year = int(cfg["start"][:4])
        for sid in F.STATIONS:
            dest = os.path.join(OUT, prod, f"{sid}.json")
            cur = F.loadj(dest) or {"station":sid,"product":prod,"series":{}}
            pix = pixs.get(sid) or cur.get("pixel")
            if not pix or "error" in pix or "lat" not in pix:
                print(f"{prod} {sid} no pixel, skip")
                continue
            series = cur.setdefault("series", {})
            for y in range(max(start_year,2019), 2027):
                nexp = EXPECT[y]
                # geopolar_dn starts mid-2019
                if prod=="geopolar_dn" and y==2019:
                    nexp = 160
                if have_year(series,y) >= nexp-8:
                    continue
                windows = [
                    (f"{y}-01-01T00:00:00Z" if y>start_year else cfg["start"],
                     f"{y}-12-31T12:00:00Z" if y<2026 else f"{ENDD}T12:00:00Z"),
                    (f"{y}-01-01T00:00:00Z", f"{y}-06-30T12:00:00Z"),
                    (f"{y}-07-01T00:00:00Z", f"{y}-12-31T12:00:00Z" if y<2026 else f"{ENDD}T12:00:00Z"),
                ]
                # try full year first; if still short, halves
                for i,(t0,t1) in enumerate(windows):
                    if i>0 and have_year(series,y) >= nexp-8:
                        break
                    if i==1 and have_year(series,y) >= nexp-8:
                        break
                    print(f"{prod} {sid} {y} try{i} {t0[:10]}..{t1[:10]} have={have_year(series,y)}", flush=True)
                    last=None
                    for attempt in range(4):
                        try:
                            ser = fetch_range(prod, cfg, pix, t0, t1)
                            series.update(ser)
                            cur["pixel"]=pix
                            F.savej(dest, cur)
                            print(f"  +{len(ser)} year={have_year(series,y)} total={len(series)}", flush=True)
                            last=None
                            break
                        except Exception as e:
                            last=e
                            print(f"  attempt {attempt+1} {type(e).__name__}: {e}", flush=True)
                            time.sleep(4+attempt*5)
                    if last and i==0:
                        print(f"  will try halves for {prod} {sid} {y}", flush=True)
            print(f"done {prod} {sid} total={len(series)}")
    print("backfill done")

if __name__=="__main__":
    main()
