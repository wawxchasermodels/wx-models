#!/usr/bin/env python3
"""Refresh production tide sidecars on the tide-archive branch (no site redeploy needed).

Writes, under --out/v1/:
  sst.json           updated W / ssta / last_day (k, clim, source kept; W = k × latest daily anomaly vs 1991-2020)
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

STAR_SSTA = ("https://www.star.nesdis.noaa.gov/pub/sod/mecb/crw/data/5km/"
             "v3.1-clim19912020-v1/nc/v1.0/daily/ssta")
STALE_H = 36
MIN_DAYS_90 = 60
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NDBC_RT = "https://www.ndbc.noaa.gov/data/realtime2"

def _get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _mean(xs):
    xs = [x for x in xs if x is not None and isinstance(x, (int, float))]
    return (sum(xs)/len(xs)) if xs else None

def _doy(d):
    if isinstance(d, str):
        d = D.date.fromisoformat(d[:10])
    return d.timetuple().tm_yday

def _coverage(daily, now, n):
    days = 0
    for i in range(n):
        if (now.date() - D.timedelta(days=i)).isoformat() in daily:
            days += 1
    return days

def fetch_coops_daily(sid, start, end):
    url = (f"{COOPS}?product=water_temperature&application=wx_models_tides&station={sid}"
           f"&begin_date={start.strftime('%Y%m%d')}&end_date={end.strftime('%Y%m%d')}"
           "&time_zone=gmt&units=metric&interval=h&format=json")
    raw = json.loads(_get(url, timeout=60))
    by, last_dt, last_v = {}, None, None
    hours = {}
    for p in raw.get("data") or []:
        try:
            t = p["t"]; v = float(p["v"])
        except (KeyError, ValueError, TypeError):
            continue
        hours[t] = v
        by.setdefault(t[:10], []).append(v)
        dt = D.datetime.fromisoformat(t)
        if last_dt is None or dt > last_dt:
            last_dt, last_v = dt, v
    daily = {d: sum(vs)/len(vs) for d, vs in by.items()}
    return daily, last_dt, last_v

def fetch_coops_daily_available(sid, start, end, max_back=5):
    """Request through end, then walk the end date back when today is not
    posted yet and the request fails or returns no observations."""
    last_err = None
    for i in range(max_back + 1):
        e = end - D.timedelta(days=i)
        if e < start:
            break
        try:
            daily, last_dt, last_v = fetch_coops_daily(sid, start, e)
        except Exception as ex:
            last_err = ex
            print(f"  coops {sid} end={e.isoformat()} fail: {ex}")
            continue
        if last_dt is not None:
            if i:
                print(f"  coops {sid} used end={e.isoformat()} (walked back {i} day(s))")
            return daily, last_dt, last_v
        print(f"  coops {sid} end={e.isoformat()} returned no observations")
    if last_err:
        raise last_err
    return {}, None, None

def fetch_mur_available(lat, lon, t0, end, max_back=5):
    """MUR usually lags 1-2 days; requesting through today 404s the whole series."""
    last_err = None
    for i in range(max_back + 1):
        e = end - D.timedelta(days=i)
        t1 = e.isoformat() + "T12:00:00Z"
        try:
            mur_raw = SST.fetch_series("mur", "jplMURSST41", "analysed_sst",
                                       lat, lon, t0, t1)
        except Exception as ex:
            last_err = ex
            print(f"  MUR end={e.isoformat()} fail: {ex}")
            continue
        if mur_raw:
            if i:
                print(f"  MUR used end={e.isoformat()} (walked back {i} day(s))")
            return mur_raw
        print(f"  MUR end={e.isoformat()} returned no values")
    if last_err:
        raise last_err
    return {}

def parse_ndbc_rt(raw):
    """NDBC realtime2 is newest-first. Skip MM / 99.0 missing WTMP (column 15)."""
    out = []
    for ln in raw.decode("latin1", errors="replace").splitlines():
        if ln.startswith("#") or ln.startswith("YY") or ln.startswith("yr"):
            continue
        p = ln.split()
        if len(p) < 15:
            continue
        try:
            y = int(p[0]);
            if y < 100:
                y += 2000
            mo, d, h, mi = int(p[1]), int(p[2]), int(p[3]), int(p[4])
            val = float(p[14])
        except Exception:
            continue
        if val > 90 or val < -2:
            continue
        out.append((D.datetime(y, mo, d, h, mi), val))
    return out

def fetch_ndbc(hid):
    daily, last_dt, last_v = {}, None, None
    try:
        raw = _get(f"{NDBC_RT}/{hid}.txt", timeout=40)
        rows = parse_ndbc_rt(raw)
    except Exception as e:
        print(f"  ndbc {hid} rt fail: {e}")
        rows = []
    by = {}
    for dt, v in rows:
        by.setdefault(dt.date().isoformat(), []).append(v)
        if last_dt is None or dt > last_dt:
            last_dt, last_v = dt, v
    daily = {d: sum(vs)/len(vs) for d, vs in by.items()}
    return daily, last_dt, last_v

def extract_crw_nc(path, lat, lon):
    from netCDF4 import Dataset
    import math
    ds = Dataset(path)
    la = ds.variables["lat"][:]
    lo = ds.variables["lon"][:]
    vv = ds.variables["sea_surface_temperature_anomaly"]
    data = vv[-1] if vv.ndim == 3 else vv[:]
    lo2 = lon + 360 if (float(lo.min()) >= 0 and lon < 0) else lon
    i = int(abs(la - lat).argmin()); j = int(abs(lo - lo2).argmin())
    val = float(data[i, j])
    if not math.isfinite(val):
        import numpy as np
        arr = __import__("numpy").array(data, dtype=float)
        for r in range(1, 6):
            w = arr[max(0, i-r):i+r+1, max(0, j-r):j+r+1]
            yy, xx = __import__("numpy").where(__import__("numpy").isfinite(w))
            if len(yy):
                val = float(w[yy[0], xx[0]]); break
    ds.close()
    if not math.isfinite(val):
        return None
    return round(float(val), 3)

def fetch_official_crw_days(needed, cache_dir, pixels_by_sid):
    """Download official 1991-2020 CRW daily NCs for the requested dates; extract each sid."""
    os.makedirs(cache_dir, exist_ok=True)
    out = {sid: {} for sid in pixels_by_sid}
    for day in needed:
        tag = day.replace("-", "")
        year = tag[:4]
        fn = f"ct5km_ssta_v3.1-clim19912020-v1_{tag}.nc"
        path = os.path.join(cache_dir, fn)
        url = f"{STAR_SSTA}/{year}/{fn}"
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            try:
                data = _get(url, timeout=90)
                open(path, "wb").write(data)
            except Exception as e:
                print(f"  CRW {day} download fail: {e}")
                continue
        for sid, pix in pixels_by_sid.items():
            if not pix or pix.get("lat") is None:
                continue
            try:
                val = extract_crw_nc(path, float(pix["lat"]), float(pix["lon"]))
            except Exception as e:
                print(f"  CRW extract {sid} {day}: {e}")
                val = None
            if val is not None:
                out[sid][day] = val
    return out

def _adopt_seed(live, seed):
    """Prefer the shipped in-situ-primary seed's station metadata; keep only rolling values from live if compatible."""
    if not seed or seed.get("sst_method") != "insitu-primary-1991-2020":
        return live or seed
    if not live or live.get("sst_method") != "insitu-primary-1991-2020":
        out = json.loads(json.dumps(seed))
        return out
    # same method: take metadata from seed (k, clim, sensors), keep any newer ssta if seed is older
    out = json.loads(json.dumps(seed))
    for sid, srow in (live.get("stations") or {}).items():
        row = (out.get("stations") or {}).get(sid)
        if not row:
            out.setdefault("stations", {})[sid] = srow
            continue
        # if live last_day is newer and k matches, keep live values as a starting guess
        if (srow.get("last_day") or "") > (row.get("last_day") or ""):
            for k in ("ssta", "ssta30_c", "W", "last_day", "sensor_last", "source", "source_short",
                      "crw_ssta_recent", "sensor_age_h", "sensor_cov90"):
                if k in srow:
                    row[k] = srow[k]
    return out

def apply_row_values(row, ssta_map, source, source_short, sensor_id=None, kind=None,
                     last_dt=None, now=None, reason=None):
    if not ssta_map:
        return False
    last = max(ssta_map)
    # W uses the latest daily anomaly vs the 1991-2020 normal. ssta30_c is a
    # legacy key kept for pickFresher / other ports and equals that daily value;
    # it is not a multi-day mean.
    ssta = ssta_map[last]
    k = float(row.get("k_ft_per_c") or 0)
    row["ssta"] = round(ssta, 3)
    row["ssta30_c"] = row["ssta"]
    row["W"] = round(k * ssta, 4)
    row["steric_ft"] = row["W"]
    row["last_day"] = last
    row["source"] = source
    row["source_short"] = source_short
    row["blend"] = source
    row["clim"] = "1991-2020"
    row["chosen_sat"] = "insitu" if kind in ("coops", "ndbc") else ("crw" if "Coral" in (source_short or "") else "oisst")
    if kind:
        row["sensor_kind"] = kind
        row["sensor_id"] = sensor_id
    if last_dt is not None and now is not None:
        row["sensor_last"] = last_dt.strftime("%Y-%m-%d %H:%M UTC")
        row["sensor_age_h"] = round((now - last_dt).total_seconds()/3600, 2)
    if reason:
        row["fallback_reason"] = reason
    elif kind in ("coops", "ndbc"):
        row.pop("fallback_reason", None)
    return True

def refresh_sst(out, seed):
    dest = os.path.join(out, "v1", "sst.json")
    live = _adopt_seed(loadj(dest), seed)
    if not live or not live.get("stations"):
        print("no sst.json seed; skip SST refresh")
        return None
    now = D.datetime.now(D.timezone.utc).replace(tzinfo=None)
    today = now.date()
    stale_h = int(live.get("stale_hours") or STALE_H)
    min90 = int(live.get("min_days_in_90") or MIN_DAYS_90)

    # Official CRW: fill any station that might need a fallback, last 40 days
    need_days = [(today - D.timedelta(days=i)).isoformat() for i in range(0, 42)]
    pixels = {sid: (row.get("crw_pixel") or {})
              for sid, row in (live.get("stations") or {}).items()
              if sid != "birchbay" and (row.get("crw_pixel") or {}).get("lat") is not None}
    # only fetch days not already present for every station? fetch last 5 always + missing
    have_max = []
    for row in (live.get("stations") or {}).values():
        rec = row.get("crw_ssta_recent") or {}
        if rec:
            have_max.append(max(rec))
    newest_have = max(have_max) if have_max else "1970-01-01"
    fetch_days = [d for d in need_days if d > newest_have or d >= (today - D.timedelta(days=4)).isoformat()]
    cache = os.path.join(out, ".crw_nc") if out else "/tmp/sst_work/crw_mur/official_nc"
    # reuse the existing official_nc cache when present
    if os.path.isdir("/tmp/sst_work/crw_mur/official_nc"):
        cache = "/tmp/sst_work/crw_mur/official_nc"
    crw_new = {}
    if fetch_days and pixels:
        print(f"CRW official fetch {len(fetch_days)} day(s): {min(fetch_days)}..{max(fetch_days)}")
        crw_new = fetch_official_crw_days(sorted(fetch_days), cache, pixels)

    start90 = today - D.timedelta(days=89)
    for sid, row in list((live.get("stations") or {}).items()):
        if sid == "birchbay" or row.get("alias_of"):
            continue
        name = row.get("name") or sid
        # merge new CRW into stored recent
        rec = dict(row.get("crw_ssta_recent") or {})
        rec.update(crw_new.get(sid) or {})
        # drop very old
        rec = {d: v for d, v in rec.items() if d >= (today - D.timedelta(days=60)).isoformat()}
        if rec:
            row["crw_ssta_recent"] = rec
            if rec:
                row["crw_official_1991_2020"] = rec.get(max(rec))

        clim = {int(k): float(v) for k, v in (row.get("clim_doy") or {}).items()}
        bias = row.get("bias_insitu_minus_sat_C")
        use_insitu = False
        reason = None
        daily, last_dt, last_v, kind, hid = {}, None, None, None, None

        # try CO-OPS at the gauge first (sensor_id if coops, else the station id)
        gauge_id = sid if sid.isdigit() else None
        try:
            dly, dt, val = fetch_coops_daily_available(sid, start90, today)
            daily, last_dt, last_v, kind, hid = dly, dt, val, "coops", sid
        except Exception as e:
            print(f"  coops {sid} skip: {e}")

        def fresh(dt, dly):
            if dt is None:
                return False, "no live in-situ water temperature within 36 h"
            age = (now - dt).total_seconds()/3600
            if age > stale_h:
                return False, f"in-situ last obs {age:.1f} h old (limit {stale_h} h)"
            cov90 = _coverage(dly, now, 90)
            d30 = _coverage(dly, now, 30)
            if cov90 >= min90:
                return True, None
            if d30 >= 25 and (row.get("bias_n") or 0) >= 365 and clim:
                row["coverage_flag"] = (f"only {cov90} of last 90 days have a daily mean; "
                                        f"recent coverage is still sufficient, so the latest daily anomaly is used")
                return True, None
            return False, f"in-situ live but only {cov90} of last 90 days and {d30} of last 30"

        ok, reason = fresh(last_dt, daily) if last_dt else (False, reason or "no live in-situ water temperature within 36 h")
        # NDBC if gauge is stale/missing
        if not ok:
            for nid in (row.get("ndbc_ids") or []):
                try:
                    dly, dt, val = fetch_ndbc(nid)
                except Exception as e:
                    print(f"  ndbc {nid} skip: {e}")
                    continue
                ok2, reason2 = fresh(dt, dly)
                if ok2:
                    daily, last_dt, last_v, kind, hid = dly, dt, val, "ndbc", nid
                    ok, reason = True, None
                    break
                else:
                    reason = reason2 or reason

        ssta = {}
        if ok and clim and bias is not None:
            for d, tval in daily.items():
                c = clim.get(_doy(d))
                if c is None:
                    continue
                ssta[d] = tval - c - float(bias)
            label = row.get("source_short")
            if kind == "coops":
                label = f"NOAA gauge at {(name or '').split(',')[0]}"
            elif kind == "ndbc":
                label = row.get("source_short") if row.get("sensor_id")==hid else f"NDBC {hid}"
            if apply_row_values(row, ssta, f"in-situ {label}", label, hid, kind, last_dt, now):
                row["sensor_cov90"] = _coverage(daily, now, 90)
                print(f"sst {sid} in-situ {label} last={row['last_day']} ssta={row['ssta']} W={row['W']}")
                continue
            reason = reason or "in-situ is live but 1991-2020 climatology could not be applied"
        elif ok and rec and (row.get("bias_sat") == "MUR" or not clim):
            # Tacoma-style: official CRW + in-situ departure from MUR (held 2 days if MUR lags)
            try:
                pix = row.get("mur_pixel") or {}
                mur = {}
                if pix.get("lat") is not None:
                    t0 = (today - D.timedelta(days=40)).isoformat() + "T00:00:00Z"
                    # Walk the end date back: MUR for UTC today is not posted yet
                    # and a today-end request 404s the whole series (Tacoma then
                    # fell back to CRW even when the gauge was fresh).
                    mur_raw = fetch_mur_available(pix["lat"], pix["lon"], t0, today)
                    for k, v in (mur_raw or {}).items():
                        v = float(v)
                        if v > 200:
                            v -= 273.15
                        mur[k[:10]] = v
                last_mur = max(mur) if mur else None
                b = float(bias) if bias is not None else 0.0
                for d, tval in daily.items():
                    if d not in rec:
                        continue
                    sat = mur.get(d)
                    if sat is None and last_mur and d >= last_mur:
                        # hold last MUR up to 2 days
                        if (D.date.fromisoformat(d) - D.date.fromisoformat(last_mur)).days <= 2:
                            sat = mur[last_mur]
                    if sat is None:
                        continue
                    ssta[d] = rec[d] + (tval - sat - b)
                label = f"NOAA gauge at {(name or '').split(',')[0]}"
                if apply_row_values(row, ssta, f"in-situ {label}", label, hid, kind, last_dt, now):
                    row["sensor_cov90"] = _coverage(daily, now, 90)
                    print(f"sst {sid} in-situ/CRW+MUR {label} last={row['last_day']} ssta={row['ssta']} W={row['W']}")
                    continue
            except Exception as e:
                print(f"  {sid} MUR departure path failed: {e}")
                reason = reason or f"MUR departure path failed: {e}"
            reason = reason or "in-situ is live but 1991-2020 climatology could not be applied"

        # Fallback: official CRW 1991-2020
        if rec:
            label = "NOAA Coral Reef Watch"
            apply_row_values(row, rec, label, label, None, "fallback", None, now, reason)
            print(f"sst {sid} fallback CRW last={row.get('last_day')} ssta={row.get('ssta')} W={row.get('W')} ({reason})")
        else:
            print(f"sst {sid}: no in-situ and no official CRW; leave as-is")

    # Birch Bay alias
    if "9449424" in (live.get("stations") or {}):
        alias = dict(live["stations"]["9449424"])
        alias["name"] = (live.get("stations", {}).get("birchbay") or {}).get("name") or "Birch Bay, WA (Cherry Point gauge)"
        alias["alias_of"] = "9449424"
        live["stations"]["birchbay"] = alias

    days = [r.get("last_day") for r in live["stations"].values() if r.get("last_day")]
    live["last_day"] = max(days) if days else None
    live["sst_method"] = "insitu-primary-1991-2020"
    live["refreshed_at"] = D.datetime.now(D.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    live["generated_at"] = live["refreshed_at"]
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
        try:
            path, n, msg = AIFS.do_cycle(c, work, AIFS.STEPS)
        except Exception as e:
            # A cycle not posted yet (index 404 / empty / not JSON) must not stop the walk-back,
            # and must not prevent the STOFS anomaly sidecar from refreshing later in this job.
            print(f"  aifs {c:%Y%m%d%H} skipped: {type(e).__name__}: {e}", flush=True)
            continue
        print(f"  {msg} -> {path}")
        rec = loadj(path)
        if not rec:
            continue
        st = rec.get("steps") or {}
        # Prefer a cycle that reaches at least 240 h (covers a 9-day chart). Do not
        # publish a newer 72 h extract over an older full-horizon one: that snap-back
        # to issue-time IB put a step in the Conditional line.
        leads = [int(k) for k in st]
        lead = max(leads) if leads else -1
        if "0" in st and lead >= 240 and len(st) >= 41:
            picked = rec
            break
        if "0" in st and len(st) >= 8:
            if not picked or lead > max(int(k) for k in (picked.get("steps") or {})):
                picked = rec  # usable but short; keep looking for a longer cycle
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
    # Each sidecar is independent: one failing must not stop the others (the site keeps its shipped copy).
    # The STOFS anomaly runs before AIFS so a slow or missing AIFS cycle cannot leave Wind surge stale.
    for skip, name, fn in ((args.skip_sst, "sst", lambda: refresh_sst(args.out, seed)),
                           (args.skip_anom, "anom", lambda: refresh_anom(args.out)),
                           (args.skip_aifs, "aifs", lambda: refresh_aifs(args.out, args.aifs_work))):
        if skip:
            continue
        try:
            fn()
        except Exception as e:
            print(f"sidecar step {name} failed (kept previous copy): {type(e).__name__}: {e}", flush=True)
    v1 = os.path.join(args.out, "v1")
    idx_fn = os.path.join(v1, "index.json")
    try:
        idx = json.load(open(idx_fn)) if os.path.exists(idx_fn) else {}
        idx["sidecars"] = {fn: True for fn in ("sst.json", "aifs_ens_msl.json", "stofs_anom.json")
                           if os.path.exists(os.path.join(v1, fn))}
        savej(idx_fn, idx)
    except Exception as e:
        print("index sidecar list skip:", e)
    print("refresh_tide_sidecars done")
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
