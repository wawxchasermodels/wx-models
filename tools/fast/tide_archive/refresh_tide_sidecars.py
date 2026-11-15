#!/usr/bin/env python3
"""Refresh production tide sidecars on the tide-archive branch (no site redeploy needed).

Writes, under --out/v1/:
  sst.json           updated W / ssta / last_day (k, clim, source kept)
  aifs_ens_msl.json  latest complete AIFS ENS (or AIFS-single / IFS fallback) MSL
  stofs_anom.json    latest STOFS 5-day station anomaly, for the Wind surge toggle

The viewer ships a copy of sst.json / aifs_ens_msl.json / stofs_anom.json with the site
and prefers a newer file from this branch when it is reachable. A 404 here must not
break the page.
"""
from __future__ import annotations
import argparse, datetime as D, json, os, shutil, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_sst_hires as SST
import fetch_aifs_ens_msl as AIFS
import fetch_stofs_anom as ANOM

LATENT_D = 2
UA = {"User-Agent": "wx-models-tides"}

def loadj(path):
    return json.load(open(path)) if os.path.exists(path) else None

def savej(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"), separators=(",", ":"))
    os.replace(tmp, path)

def doy(d):
    return d.timetuple().tm_yday

def refresh_sst(out, seed):
    dest = os.path.join(out, "v1", "sst.json")
    live = loadj(dest) or seed
    if not live or not live.get("stations"):
        if seed:
            savej(dest, seed)
            live = seed
        else:
            print("no sst.json seed; skip SST refresh")
            return None
    today = D.datetime.now(D.timezone.utc).date()
    cutoff = today - D.timedelta(days=LATENT_D)
    t0 = (cutoff - D.timedelta(days=40)).isoformat() + "T00:00:00Z"
    t1 = cutoff.isoformat() + "T12:00:00Z"
    for sid, row in (live.get("stations") or {}).items():
        prod = row.get("chosen_sat") or "mur"
        if prod not in SST.PRODUCTS:
            print(f"sst {sid}: unknown product {prod}, leave as-is")
            continue
        pix = row.get("pixel") or {}
        if "lat" not in pix:
            print(f"sst {sid}: no pixel, leave as-is")
            continue
        cfg = SST.PRODUCTS[prod]
        try:
            ser = SST.fetch_series(prod, cfg["ds"], cfg["var"], pix["lat"], pix["lon"], t0, t1, cfg.get("zlev"))
            if prod == "oisst":
                try:
                    ser.update(SST.fetch_series(prod, cfg["nrt"], cfg["var"], pix["lat"], pix["lon"], t0, t1, True))
                except Exception as e:
                    print("  oisst nrt skip", e)
        except Exception as e:
            print(f"sst {sid} sat fetch failed: {type(e).__name__}: {e}")
            continue
        if not ser:
            print(f"sst {sid}: empty series")
            continue
        bias = float(row.get("sat_bias_removed_C") or 0)
        temps = {D.date.fromisoformat(k): float(v) - bias for k, v in ser.items() if k <= cutoff.isoformat()}
        src = (row.get("source") or "")
        if src.startswith("blend:"):
            # merge recent CO-OPS daily water temp when the operational series is a blend
            try:
                rec = {"lat": 0, "lon": 0}
                # reuse fetch_coops one-station window via the API directly
                def coops_daily(sid, a, b):
                    # metric daily means
                    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
                           f"product=water_temperature&application=wx_models_tides&station={sid}"
                           f"&begin_date={a.strftime('%Y%m%d')}&end_date={b.strftime('%Y%m%d')}"
                           "&time_zone=gmt&units=metric&interval=h&format=json")
                    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
                    j = json.loads(raw)
                    by = {}
                    for p in j.get("data") or []:
                        try:
                            t = p["t"]; v = float(p["v"])
                        except (KeyError, ValueError, TypeError):
                            continue
                        day = t[:10]
                        by.setdefault(day, []).append(v)
                    return {D.date.fromisoformat(d): sum(vs)/len(vs) for d, vs in by.items()}
                ins = coops_daily(sid, cutoff - D.timedelta(days=40), cutoff)
                for d, v in ins.items():
                    sat = temps.get(d, v)
                    temps[d] = 0.7 * v + 0.3 * sat
            except Exception as e:
                print(f"  blend in-situ skip {sid}: {e}")
        clim = {int(k): float(v) for k, v in (row.get("clim_doy") or {}).items()}
        usable = {}
        for d, v in temps.items():
            c = clim.get(doy(d))
            if c is not None:
                usable[d] = v - c
        if not usable:
            print(f"sst {sid}: no usable anomalies")
            continue
        last = max(usable)
        window = [usable[last - D.timedelta(days=k)] for k in range(30) if (last - D.timedelta(days=k)) in usable]
        ssta = usable[last]
        ssta30 = (sum(window)/len(window)) if window else ssta
        k = float(row.get("k_ft_per_c") or 0)
        W = k * ssta30
        row["ssta"] = round(ssta, 3)
        row["ssta30_c"] = round(ssta30, 3)
        row["W"] = round(W, 4)
        row["steric_ft"] = round(W, 4)
        row["last_day"] = last.isoformat()
        print(f"sst {sid} last={last} ssta30={ssta30:.3f} W={W:.4f}")
    live["refreshed_at"] = D.datetime.now(D.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    savej(dest, live)
    return dest

def latest_aifs_cycle(now=None):
    now = now or D.datetime.now(D.timezone.utc).replace(minute=0, second=0, microsecond=0)
    # AIFS ENS 00/06/12/18Z, typically 3-6 h late; walk back 36 h
    t = now.replace(hour=(now.hour // 6) * 6)
    out = []
    for _ in range(8):
        out.append(t)
        t -= D.timedelta(hours=6)
    return out

def refresh_aifs(out, work):
    os.makedirs(work, exist_ok=True)
    dest = os.path.join(out, "v1", "aifs_ens_msl.json")
    picked = None
    for c in latest_aifs_cycle():
        print(f"aifs try {c:%Y%m%d%H}", flush=True)
        path, n, msg = AIFS.do_cycle(c, work, AIFS.STEPS)
        print(f"  {msg} -> {path}")
        rec = loadj(path)
        if not rec:
            continue
        st = rec.get("steps") or {}
        if "0" in st and "72" in st and len(st) >= 13:
            picked = rec
            break
        if not picked and "0" in st and len(st) >= 8:
            picked = rec  # usable but short
    if not picked:
        print("aifs: no usable cycle")
        return None
    savej(dest, picked)
    print("aifs wrote", dest, "cycle", picked.get("cycle"), "steps", len(picked.get("steps") or {}))
    return dest

def refresh_anom(out):
    dest = os.path.join(out, "v1", "stofs_anom.json")
    now = D.datetime.now(D.timezone.utc).replace(minute=0, second=0, microsecond=0)
    t = now.replace(hour=(now.hour // 6) * 6)
    last = None
    for _ in range(6):
        try:
            with __import__("tempfile").TemporaryDirectory() as tmp:
                rec = ANOM.extract(t.replace(tzinfo=None), tmp)
            if rec and rec.get("stations"):
                last = rec
                break
        except Exception as e:
            print(f"anom {t:%Y%m%d%H} fail: {type(e).__name__}: {e}")
        t -= D.timedelta(hours=6)
    if not last:
        print("anom: no usable cycle")
        return None
    savej(dest, last)
    print("anom wrote", dest, "cycle", last.get("cycle"))
    return dest

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="tide-archive checkout (writes v1/)")
    ap.add_argument("--seed-sst", default="", help="site sst.json to copy if v1/sst.json is missing")
    ap.add_argument("--aifs-work", default="/tmp/aifs_ens_msl")
    ap.add_argument("--skip-sst", action="store_true")
    ap.add_argument("--skip-aifs", action="store_true")
    ap.add_argument("--skip-anom", action="store_true")
    args = ap.parse_args()
    os.makedirs(os.path.join(args.out, "v1"), exist_ok=True)
    seed = loadj(args.seed_sst) if args.seed_sst else None
    if not args.skip_sst:
        refresh_sst(args.out, seed)
    if not args.skip_aifs:
        refresh_aifs(args.out, args.aifs_work)
    if not args.skip_anom:
        refresh_anom(args.out)
    print("refresh_tide_sidecars done")
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
