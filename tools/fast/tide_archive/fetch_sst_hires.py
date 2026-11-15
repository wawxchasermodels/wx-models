#!/usr/bin/env python3
"""Fetch higher-res SST analyses and in-situ water temperature for WA/OR tide stations.

Products (public ERDDAP / CO-OPS / NDBC, no keys):
  mur           NASA JPL MUR v4.1 0.01 deg (jplMURSST41) — nearest water pixel
  geopolar_dn   NOAA Geo-Polar Blended Day+Night 5 km (nesdisBLENDEDsstDNDaily, 2019-)
  geopolar_n    NOAA Geo-Polar Blended Night Only 5 km (nesdisGeoPolarSSTN5NRT, 2002-)
  oisst         NOAA OISST v2.1 0.25 deg (final + NRT), nearest pixel (often no Sound coverage)
  ostia         UK Met OSTIA 0.05 deg — attempted if an ERDDAP ID is given via --ostia-id
  coops         CO-OPS water_temperature at the gauge, deg C
  ndbc          NDBC/CMAN WTMP at the same or nearby site, deg C
"""
from __future__ import annotations
import argparse, csv, datetime as D, io, json, os, time, urllib.parse, urllib.request, gzip, math

UA = {"User-Agent": "wx-models-tides"}
ERD = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NDBC_H = "https://www.ndbc.noaa.gov/data/historical/stdmet"
NDBC_RT = "https://www.ndbc.noaa.gov/data/realtime2"
OUT_DEFAULT = "/tmp/sst_work/hires"

STATIONS = {
    "9439040": {"name": "Astoria, OR", "lat": 46.207306, "lon": -123.7683, "sound": False, "ndbc": ["ASTO3", "46029"]},
    "9440581": {"name": "Cape Disappointment, WA", "lat": 46.28103, "lon": -124.04628, "sound": False, "ndbc": ["CPTW1", "46029"]},
    "9440910": {"name": "Toke Point, WA", "lat": 46.7075, "lon": -123.96694, "sound": False, "ndbc": ["TOKW1", "46041"]},
    "9441102": {"name": "Westport, WA", "lat": 46.90431, "lon": -124.10508, "sound": False, "ndbc": ["WPTW1", "46041"]},
    "9442396": {"name": "La Push, WA", "lat": 47.912838, "lon": -124.63574, "sound": False, "ndbc": ["LAPW1"]},
    "9443090": {"name": "Neah Bay, WA", "lat": 48.370724, "lon": -124.601585, "sound": False, "ndbc": ["NEAW1", "46087"]},
    "9444090": {"name": "Port Angeles, WA", "lat": 48.125, "lon": -123.44, "sound": True, "ndbc": ["PTAW1", "46088"]},
    "9444900": {"name": "Port Townsend, WA", "lat": 48.11122, "lon": -122.759674, "sound": True, "ndbc": ["PTWW1", "SISW1"]},
    "9449880": {"name": "Friday Harbor, WA", "lat": 48.545277, "lon": -123.0125, "sound": True, "ndbc": ["FRDW1"]},
    "9449424": {"name": "Cherry Point, WA", "lat": 48.862717, "lon": -122.75858, "sound": True, "ndbc": ["CHYW1", "CPNW1"]},
    "9447130": {"name": "Seattle, WA", "lat": 47.60264, "lon": -122.3393, "sound": True, "ndbc": ["WPOW1"]},
    "9446484": {"name": "Tacoma, WA", "lat": 47.2667, "lon": -122.4133, "sound": True, "ndbc": ["TCNW1", "TCMW1"]},
}

CW_ERD = "https://coastwatch.noaa.gov/erddap/griddap"
PRODUCTS = {
    "mur": {"ds": "jplMURSST41", "var": "analysed_sst", "box": 0.08, "start": "2019-01-01T09:00:00Z", "erd": ERD, "chunk": "year"},
    # PFEG retired nesdisBLENDEDsstDNDaily; the same Geo-Polar Day+Night 5 km analysis lives on CoastWatch.
    "geopolar_dn": {"ds": "noaacwBLENDEDsstDNDaily", "var": "analysed_sst", "box": 0.12, "start": "2019-07-22T12:00:00Z",
                    "erd": CW_ERD, "chunk": "month"},
    "geopolar_n": {"ds": "nesdisGeoPolarSSTN5NRT", "var": "analysed_sst", "box": 0.12, "start": "2019-01-01T12:00:00Z",
                   "erd": ERD, "chunk": "month"},
    "oisst": {"ds": "ncdcOisst21Agg", "var": "sst", "box": 0.40, "start": "2019-01-01T12:00:00Z", "zlev": True,
              "nrt": "ncdcOisst21NrtAgg", "erd": ERD, "chunk": "year", "lon360": True},
}

def erd_of(cfg):
    return cfg.get("erd") or ERD

def wrap_lon(lon, cfg):
    lon = float(lon)
    if cfg.get("lon360") and lon < 0:
        return lon + 360.0
    return lon

def get(url, timeout=90, retries=5):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 + i * 3)
    raise last

def loadj(path):
    if os.path.exists(path):
        return json.load(open(path))
    return None

def savej(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"))
    os.replace(tmp, path)

def parse_erd_csv(raw):
    """Return list of (date, lat, lon, value) from ERDDAP .csv (skip units row).

    Header-aware so zlev products (time, zlev, latitude, longitude, sst) parse correctly.
    """
    text = raw.decode("utf-8", "replace")
    if text.startswith("<html") or "Error {" in text[:200]:
        raise RuntimeError("ERDDAP error: " + text[:300])
    lines = text.splitlines()
    if len(lines) < 3:
        return []
    header = [h.strip().lower() for h in next(csv.reader([lines[0]]))]
    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None
    i_t = col("time") or 0
    i_la = col("latitude", "lat", "analysed_sst_lat")
    i_lo = col("longitude", "lon", "analysed_sst_lon")
    # value: last non-coordinate numeric column, prefer known names
    i_v = col("analysed_sst", "sst", "sea_surface_temperature", "anom")
    if i_la is None or i_lo is None:
        # fallback: if a zlev column is present, columns are time, zlev, lat, lon, value
        if any("zlev" in h or h == "altitude" or h == "depth" for h in header) and len(header) >= 5:
            i_la, i_lo, i_v = 2, 3, len(header)-1
        else:
            i_la, i_lo, i_v = 1, 2, 3
    if i_v is None:
        i_v = len(header)-1
    out = []
    for row in csv.reader(lines[2:]):
        if len(row) <= max(i_t, i_la, i_lo, i_v):
            continue
        t, la, lo, v = row[i_t], row[i_la], row[i_lo], row[i_v]
        if v in ("", "NaN", "nan", "NA"):
            val = None
        else:
            try:
                val = float(v)
            except ValueError:
                val = None
        try:
            day = t[:10]
            lat = float(la); lon = float(lo)
        except ValueError:
            continue
        out.append((day, lat, lon, val))
    return out

def pick_pixel(prod, st, rec, probe_day="2026-10-15"):
    """Nearest finite pixel in a small box around the station on a recent day (try a few days)."""
    cfg = PRODUCTS[prod]
    lat, lon = rec["lat"], rec["lon"]
    b = cfg["box"]
    var = cfg["var"]
    days = [probe_day, "2026-08-15", "2025-08-15", "2024-08-15"]
    for day in days:
        # time will be snapped by ERDDAP
        z = "[(0.0)]" if cfg.get("zlev") else ""
        t0 = f"{day}T12:00:00Z"
        url = (f"{erd_of(cfg)}/{cfg['ds']}.csv?{var}[({t0}):1:({t0})]{z}"
               f"[({lat-b}):({lat+b})][({wrap_lon(lon-b, cfg)}):({wrap_lon(lon+b, cfg)})]")
        try:
            rows = parse_erd_csv(get(url, timeout=120))
        except Exception as e:
            print(f"  pixel probe fail {prod} {st} {day}: {e}", flush=True)
            continue
        good = [r for r in rows if r[3] is not None and math.isfinite(r[3])]
        if not good:
            continue
        def lon180(x):
            x = float(x)
            if x > 180: x -= 360.0
            if x <= -180: x += 360.0
            return x
        def d2(r):
            dlon = (lon180(r[2]) - lon + 180) % 360 - 180
            return (r[1]-lat)**2 + dlon**2
        good.sort(key=d2)
        plat, plon, sst = good[0][1], lon180(good[0][2]), good[0][3]
        dlon = (plon - lon + 180) % 360 - 180
        dist_km = ((plat-lat)**2 + dlon**2)**0.5 * 111.0
        if dist_km > 80:
            print(f"  pixel too far {prod} {st}: {plat},{plon} d={dist_km:.0f} km (skipped)", flush=True)
            continue
        return {"lat": plat, "lon": plon, "dist_km": round(dist_km, 2), "probe_day": day, "probe_sst": sst, "n_water": len(good)}
    return None

def fetch_series(prod, ds, var, plat, plon, t0, t1, zlev=False):
    z = "[(0.0)]" if zlev else ""
    base = erd_of(PRODUCTS.get(prod) or {})
    plon_q = wrap_lon(plon, PRODUCTS.get(prod) or {})
    url = (f"{base}/{ds}.csv?{var}[({t0}):1:({t1})]{z}[({plat}):({plat})][({plon_q}):({plon_q})]")
    rows = parse_erd_csv(get(url, timeout=180))
    ser = {}
    for day, la, lo, val in rows:
        if val is not None:
            ser[day] = round(val, 3)
    return ser

def fetch_product(prod, out, end="2026-11-13", only=None):
    cfg = PRODUCTS[prod]
    pix_path = os.path.join(out, "pixels.json")
    pixels = loadj(pix_path) or {}
    pixels.setdefault(prod, {})
    dest_dir = os.path.join(out, prod)
    os.makedirs(dest_dir, exist_ok=True)
    for sid, rec in STATIONS.items():
        if only and sid not in only:
            continue
        dest = os.path.join(dest_dir, f"{sid}.json")
        cur = loadj(dest) or {"station": sid, "product": prod, "series": {}}
        if not pixels[prod].get(sid):
            print(f"{prod} {sid} picking pixel...", flush=True)
            pix = pick_pixel(prod, sid, rec)
            if not pix:
                print(f"{prod} {sid} NO WATER PIXEL", flush=True)
                pixels[prod][sid] = {"error": "no water pixel"}
                savej(pix_path, pixels)
                continue
            pixels[prod][sid] = pix
            savej(pix_path, pixels)
            print(f"{prod} {sid} pixel {pix['lat']},{pix['lon']} d={pix['dist_km']} km n={pix['n_water']}", flush=True)
        pix = pixels[prod][sid]
        if "error" in pix:
            continue
        have = set(cur.get("series") or {})
        start_year = int(cfg["start"][:4])
        for y in range(start_year, 2027):
            t0 = max(cfg["start"], f"{y}-01-01T00:00:00Z")
            t1 = f"{min(y, 2026)}-12-31T12:00:00Z" if y < 2026 else f"{end}T12:00:00Z"
            days_expect = 360 if y < 2026 else 300
            have_y = sum(1 for d in have if d.startswith(str(y)))
            if have_y >= days_expect:
                continue
            windows = [(t0, t1)]
            if cfg.get("chunk") == "month":
                windows = []
                for mo in range(1, 13):
                    if y == 2026 and mo > 11:
                        break
                    mt0 = f"{y}-{mo:02d}-01T00:00:00Z"
                    if mo == 12:
                        mt1 = f"{y}-12-31T12:00:00Z"
                    else:
                        mt1 = f"{y}-{mo:02d}-28T12:00:00Z" if mo == 2 else f"{y}-{mo:02d}-30T12:00:00Z"
                        if mo in (1,3,5,7,8,10,12):
                            mt1 = f"{y}-{mo:02d}-31T12:00:00Z"
                    if y == 2026 and mo == 11:
                        mt1 = f"{end}T12:00:00Z"
                    if mt1[:10] < cfg["start"][:10]:
                        continue
                    if mt0 < cfg["start"]:
                        mt0 = cfg["start"]
                    windows.append((mt0, mt1))
            ser_year = {}
            ok_any = False
            for wt0, wt1 in windows:
                print(f"{prod} {sid} {wt0[:10]}..{wt1[:10]} ...", flush=True)
                try:
                    ser = fetch_series(prod, cfg["ds"], cfg["var"], pix["lat"], pix["lon"], wt0, wt1, cfg.get("zlev"))
                    if prod == "oisst" and wt1.startswith("2026"):
                        try:
                            nrt = fetch_series(prod, cfg["nrt"], cfg["var"], pix["lat"], pix["lon"], "2026-10-01T12:00:00Z", wt1, True)
                            ser.update(nrt)
                        except Exception as e:
                            print(f"  NRT skip: {e}", flush=True)
                    ser_year.update(ser)
                    ok_any = True
                    print(f"  {prod} {sid} {wt0[:7]} +{len(ser)}", flush=True)
                except Exception as e:
                    print(f"  FAIL {prod} {sid} {wt0[:7]}: {type(e).__name__}: {e}", flush=True)
                    continue
            if not ok_any and not ser_year:
                continue
            cur.setdefault("series", {}).update(ser_year)
            cur["pixel"] = pix
            cur["dataset"] = cfg["ds"]
            cur["erd"] = erd_of(cfg)
            savej(dest, cur)
            have = set(cur["series"])
            print(f"  {prod} {sid} {y} year+{len(ser_year)} total={len(cur['series'])}", flush=True)

    return 0

def coops_temp(sid, begin, end):
    """Hourly water temperature in deg C. begin/end YYYYMMDD."""
    u = (f"{COOPS}?product=water_temperature&application=wx_models_tides"
         f"&station={sid}&begin_date={begin}&end_date={end}"
         f"&time_zone=gmt&units=metric&interval=h&format=json")
    raw = get(u, timeout=120)
    j = json.loads(raw)
    out = {}
    for p in j.get("data") or []:
        v = p.get("v")
        if v in ("", None):
            continue
        try:
            out[p["t"]] = float(v)
        except ValueError:
            continue
    return out

def fetch_coops(out):
    dest_dir = os.path.join(out, "insitu_coops")
    os.makedirs(dest_dir, exist_ok=True)
    for sid, rec in STATIONS.items():
        dest = os.path.join(dest_dir, f"{sid}.json")
        cur = loadj(dest) or {"station": sid, "name": rec["name"], "source": "CO-OPS water_temperature metric", "hourly": {}}
        for y, b, e in [
            (2019, "20190101", "20191231"), (2020, "20200101", "20201231"),
            (2021, "20210101", "20211231"), (2022, "20220101", "20221231"),
            (2023, "20230101", "20231231"), (2024, "20240101", "20241231"),
            (2025, "20250101", "20251231"), (2026, "20260101", "20261115"),
        ]:
            have_y = sum(1 for t in cur["hourly"] if t.startswith(str(y)))
            if have_y > 8000:
                continue
            print(f"coops-wt {sid} {y} ...", flush=True)
            try:
                ser = coops_temp(sid, b, e)
            except Exception as e:
                print(f"  FAIL coops {sid} {y}: {e}", flush=True)
                continue
            cur["hourly"].update(ser)
            savej(dest, cur)
            print(f"  +{len(ser)} total={len(cur['hourly'])}", flush=True)
        # daily means
        by = {}
        for t, v in cur["hourly"].items():
            by.setdefault(t[:10], []).append(v)
        cur["daily"] = {d: round(sum(vs)/len(vs), 3) for d, vs in by.items()}
        savej(dest, cur)
        print(f"coops-wt {sid} days={len(cur['daily'])}", flush=True)

def parse_ndbc(text, historic=True):
    """Return {YYYY-MM-DDTHH:00: 'C'} from NDBC stdmet (WTMP deg C). Missing is 999 or MM."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("+")]
    if not lines:
        return {}
    # skip units line if starts with #
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        i += 1
    # sometimes first two are header + units
    if i < len(lines) and lines[i].lstrip().startswith("YY"):
        i += 1
        if i < len(lines) and lines[i].strip().startswith("#") or (i < len(lines) and "yr" in lines[i].lower()):
            i += 1
    # detect columns from a header if present
    header = None
    for ln in lines:
        if "WTMP" in ln and ("YY" in ln or "YYYY" in ln):
            header = ln.replace("#", " ").split()
            break
    out = {}
    # year month day hour ... WTMP is typically col after WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP
    # historic: YYYY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP DEWP VIS TIDE
    # realtime: YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP DEWP VIS TIDE
    for ln in lines:
        if ln.startswith("#") or "WTMP" in ln or ln.strip().startswith("yy") or ln.strip().startswith("YY"):
            continue
        p = ln.split()
        if len(p) < 15:
            continue
        try:
            y = int(p[0])
            if y < 100:
                y += 2000 if y < 70 else 1900
            mo, d, h = int(p[1]), int(p[2]), int(p[3])
            # WTMP index: if mm present (5 time fields) then 14 else 13
            # historic has mm: YYYY MM DD hh mm = 5 fields, WTMP is index 14
            # Some older files lack mm
            if len(p[0]) == 4 or (len(p) >= 16 and int(p[4]) in range(0, 61) and int(p[3]) in range(0, 24)):
                # has minute
                wtmp_i = 14
            else:
                wtmp_i = 13
            if header and "WTMP" in header:
                wtmp_i = header.index("WTMP")
            if wtmp_i >= len(p):
                continue
            v = p[wtmp_i]
            if v in ("MM", "999", "999.0", "99.0", "99"):
                continue
            val = float(v)
            if val > 40 or val < -2:
                continue
            key = f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:00"
            out[key] = val
        except (ValueError, IndexError):
            continue
    return out

def fetch_ndbc(out):
    dest_dir = os.path.join(out, "insitu_ndbc")
    os.makedirs(dest_dir, exist_ok=True)
    ids = []
    for rec in STATIONS.values():
        for i in rec["ndbc"]:
            if i not in ids:
                ids.append(i)
    for hid in ids:
        dest = os.path.join(dest_dir, f"{hid}.json")
        cur = loadj(dest) or {"id": hid, "source": "NDBC stdmet WTMP", "hourly": {}}
        for y in range(2019, 2027):
            have_y = sum(1 for t in cur["hourly"] if t.startswith(str(y)))
            if y < 2026 and have_y > 6000:
                continue
            url = f"{NDBC_H}/{hid.lower()}h{y}.txt.gz"
            print(f"ndbc {hid} {y} ...", flush=True)
            try:
                raw = get(url, timeout=60)
                if raw[:2] == b"\x1f\x8b":
                    text = gzip.decompress(raw).decode("utf-8", "replace")
                else:
                    text = raw.decode("utf-8", "replace")
                ser = parse_ndbc(text)
            except Exception as e:
                print(f"  skip {hid} {y}: {type(e).__name__} {e}", flush=True)
                ser = {}
            cur["hourly"].update(ser)
            savej(dest, cur)
            print(f"  +{len(ser)} total={len(cur['hourly'])}", flush=True)
        # realtime for 2026 remainder
        url = f"{NDBC_RT}/{hid}.txt"
        try:
            text = get(url, timeout=45).decode("utf-8", "replace")
            ser = parse_ndbc(text, historic=False)
            cur["hourly"].update(ser)
            print(f"  realtime {hid} +{len(ser)}", flush=True)
        except Exception as e:
            print(f"  realtime skip {hid}: {e}", flush=True)
        by = {}
        for t, v in cur["hourly"].items():
            by.setdefault(t[:10], []).append(v)
        cur["daily"] = {d: round(sum(vs)/len(vs), 3) for d, vs in by.items()}
        savej(dest, cur)

def fetch_ostia(out, ds_id):
    """If an ERDDAP dataset ID is provided, treat it like the other L4 analyses."""
    if not ds_id:
        print("OSTIA: no public ERDDAP ID configured (PFEG jplUKMO_OSTIAv20 is 404). Skipping.")
        return
    PRODUCTS["ostia"] = {"ds": ds_id, "var": "analysed_sst", "box": 0.12, "start": "2019-01-01T12:00:00Z"}
    fetch_product("ostia", out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--products", default="mur,geopolar_dn,geopolar_n,oisst,coops,ndbc")
    ap.add_argument("--ostia-id", default="")
    ap.add_argument("--stations", default="", help="comma-separated station ids (default: all)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    wanted = [p.strip() for p in args.products.split(",") if p.strip()]
    only = [s.strip() for s in args.stations.split(",") if s.strip()] or None
    if "coops" in wanted:
        fetch_coops(args.out)
    if "ndbc" in wanted:
        fetch_ndbc(args.out)
    for p in ("mur", "geopolar_dn", "geopolar_n", "oisst"):
        if p in wanted:
            fetch_product(p, args.out, only=only)
    if "ostia" in wanted:
        fetch_ostia(args.out, args.ostia-id if False else args.ostia_id)
    print("done")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
