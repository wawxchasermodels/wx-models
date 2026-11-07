#!/usr/bin/env python3
"""Point meteograms for WA towns: ECMWF EPS (open data, CC BY 4.0) and NOAA HRRR (public domain).

NOT scheduled. Run by hand only, e.g.
  python tools/forecast/meteograms.py eps  --town seattle --products eps_t2m_members,eps_qpf_plume --hours 144
  python tools/forecast/meteograms.py hrrr --town seattle --products hrrr_surface_summary,hrrr_multirun_t2m

ECMWF ENS open data has no point API, so each member field is a global 0.25 deg GRIB record
(~0.3-0.45 MB); one download serves every town, so all towns are extracted into the cache.
HRRR uses the NOMADS grib filter with a small subregion (a few KB per request).
Output PNGs + manifest fragments go to OUT/<source>/<town>/<product>.png
"""
import argparse, datetime as dt, json, os, sys, time, urllib.request, io
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import numpy as np
import eccodes as ec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("SITE_DIR", os.path.join(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "web", "forecast")), "meteograms")
CACHE = os.environ.get("METEO_CACHE", os.path.join(os.environ.get("SITE_BATCH", ".site_batch"), "meteo_cache"))
UA = {"User-Agent": "wx-models meteograms (personal, non-scheduled)"}

TOWNS = {  # id: (name, lat, lon). Official reporting-station points (ICAO verified 10-24-26 on aviationweather.gov), passes at the summit.
    "seattle": ("Seattle (SeaTac)", 47.44467, -122.31442),  # KSEA Seattle-Tacoma Intl
    "tacoma": ("Tacoma (Narrows)", 47.26744, -122.57624),  # KTIW Tacoma Narrows
    "everett": ("Everett (Paine Field)", 47.92323, -122.28308),  # KPAE Paine Field
    "arlington": ("Arlington", 48.15839, -122.15914),  # KAWO Arlington Municipal
    "bellingham": ("Bellingham", 48.7991, -122.5407),  # KBLI Bellingham Intl
    "olympia": ("Olympia", 46.97371, -122.90494),  # KOLM Olympia Regional
    "vancouver": ("Vancouver WA (Pearson)", 45.62102, -122.65421),  # KVUO Pearson Field
    "portangeles": ("Port Angeles", 48.12193, -123.50657),  # KCLM Port Angeles Intl
    "forks": ("Forks (Quillayute)", 47.93695, -124.55757),  # KUIL Quillayute Airport, nearest official station to Forks
    "aberdeen": ("Aberdeen (Hoquiam)", 46.97288, -123.93079),  # KHQM Bowerman Airport, Hoquiam
    "oceanshores": ("Ocean Shores", 46.9737, -124.1563),  # town point; no official station (nearest: KHQM, 17 km east)
    "spokane": ("Spokane", 47.62169, -117.52796),  # KGEG Spokane Intl
    "yakima": ("Yakima", 46.56398, -120.53489),  # KYKM McAllister Field
    "wenatchee": ("Wenatchee (Pangborn)", 47.39748, -120.20126),  # KEAT Pangborn Memorial
    "kennewick": ("Tri-Cities (Pasco)", 46.2695, -119.11817),  # KPSC Tri-Cities Airport, Pasco
    "wallawalla": ("Walla Walla", 46.09457, -118.28572),  # KALW Walla Walla Regional
    "moseslake": ("Moses Lake", 47.19295, -119.31459),  # KMWH Grant County Intl
    "ellensburg": ("Ellensburg", 47.03376, -120.53135),  # KELN Bowers Field
    "pullman": ("Pullman", 46.74377, -117.11582),  # KPUW Pullman-Moscow Regional
    "omak": ("Omak", 48.46114, -119.52091),  # KOMK Omak Airport
    "snoqualmie": ("Snoqualmie Pass", 47.4245, -121.413),  # I-90 summit; no METAR station there
    "stevens": ("Stevens Pass", 47.7466, -121.089),  # US 2 summit; no METAR station there
}

# ---- style: same dark base as the forecast maps (WATER 29,30,34 / LAND 62,64,68), 32 F line, blue <= 32
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house_style as HS
HS.use_for_plots()
BG, PANEL, GRID, INK, MUTED = HS.BG, "#20232a", "#3a3e46", HS.INK, HS.MUTED
WARM, COLD, RAIN, SNOW, MEAN = "#ff6a3d", "#5fa8ff", "#3fbf5a", "#8fd3ff", "#ffffff"
ECMWF_CREDIT = "Source: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int"
NOAA_CREDIT = "Data: NOAA HRRR (public domain)"


def get(url, rng=None, tries=3):
    h = dict(UA)
    if rng:
        h["Range"] = "bytes=%d-%d" % rng
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 + 3 * i)


# ======================= ECMWF EPS =======================
EPS_BASE = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-ef"
EPS_NEED = {"eps_t2m_members": [("2t", None)], "eps_qpf_plume": [("tp", None)],
            "eps_qpf_members": [("tp", None)], "eps_snow_plume": [("sf", None)],
            "eps_tmax_members": [("mx2t3", None)], "eps_tmin_members": [("mn2t3", None)],
            "eps_daily_hilo": [("mx2t3", None), ("mn2t3", None)], "eps_tcc_members": [("tcc", None)],
            "eps_gust_members": [("10fg", None)], "eps_mucape_members": [("mucape", None)],
            "eps_pwat_members": [("tcwv", None)], "eps_z500_t850": [("gh", "500"), ("t", "850")]}


def latest_eps_cycle():
    now = dt.datetime.now(dt.timezone.utc)
    for back in range(0, 48, 6):
        c = (now - dt.timedelta(hours=back)).replace(minute=0, second=0, microsecond=0)
        c = c.replace(hour=c.hour - c.hour % 12)  # 00/12Z go to 360 h
        url = EPS_BASE.format(d=c.strftime("%Y%m%d"), h=c.hour, s=144) + ".index"
        try:
            get(url, (0, 10))
            return c
        except Exception:
            continue
    raise SystemExit("no ENS run found")


def eps_fetch(cycle, params, steps):
    os.makedirs(CACHE, exist_ok=True)
    cpath = f"{CACHE}/eps_{cycle:%Y%m%d%H}.json"
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    total = [0]

    def one(step):
        base = EPS_BASE.format(d=cycle.strftime("%Y%m%d"), h=cycle.hour, s=step)
        recs = []
        for ln in get(base + ".index").decode().splitlines():
            r = json.loads(ln)
            for p, lev in params:
                if r["param"] == p and (lev is None or r.get("levelist") == lev) and f"{p}{lev or ''}|{step}" not in cache:
                    recs.append(r)
        recs.sort(key=lambda r: r["_offset"])
        groups = []  # coalesce adjacent byte ranges
        for r in recs:
            a, b = r["_offset"], r["_offset"] + r["_length"] - 1
            if groups and a == groups[-1][1] + 1:
                groups[-1][1] = b
            else:
                groups.append([a, b])
        out = {}
        for a, b in groups:
            blob = get(base + ".grib2", (a, b)); total[0] += len(blob)
            off = 0
            while True:
                i = blob.find(b"GRIB", off)
                if i < 0:
                    break
                L = int.from_bytes(blob[i + 8:i + 16], "big")
                g = ec.codes_new_from_message(blob[i:i + L])
                sn = ec.codes_get(g, "shortName"); lev = str(ec.codes_get(g, "level")) if sn in ("gh", "t") else ""
                num = ec.codes_get(g, "number")
                key = f"{sn}{lev}|{step}"
                for k, (_, la, lo) in TOWNS.items():
                    v = ec.codes_grib_find_nearest(g, la, lo)[0]["value"]
                    out.setdefault(key, {}).setdefault(k, {})[str(num)] = float(v)
                ec.codes_release(g); off = i + L
        return out

    with ThreadPoolExecutor(6) as ex:
        for res in ex.map(one, steps):
            cache.update(res)
    json.dump(cache, open(cpath, "w"))
    print(f"EPS {cycle:%Y%m%d%H}Z: downloaded {total[0]/1e6:.0f} MB for {len(steps)} steps", flush=True)
    return cache


def series(cache, key, town, steps):
    rows = []
    for s in steps:
        d = cache.get(f"{key}|{s}", {}).get(town)
        rows.append([d[m] for m in sorted(d, key=int)] if d else None)
    ok = [i for i, r in enumerate(rows) if r]
    nm = max(len(rows[i]) for i in ok)
    arr = np.full((len(steps), nm), np.nan)
    for i in ok:
        arr[i, :len(rows[i])] = rows[i]
    return arr


def frame(title, sub, credit, ylabel):
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=120)  # 1440x810
    fig.patch.set_facecolor(BG); ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=INK, labelsize=11); ax.grid(color=GRID, lw=0.8)
    ax.set_ylabel(ylabel, color=INK, fontsize=12)
    fig.patches.append(matplotlib.patches.Rectangle((0.012, 0.865), 0.0045, 0.105, transform=fig.transFigure, color=HS.ACCENT))
    fig.text(0.024, 0.965, title, color=INK, fontproperties=HS.font(800, 20), va="top")
    fig.text(0.024, 0.905, sub, color=HS.ACCENT, fontproperties=HS.font(600, 12.5), va="top")
    fig.text(0.024, 0.012, credit, color=MUTED, fontproperties=HS.font(500, 9.5))
    fig.subplots_adjust(left=0.07, right=0.98, top=0.83, bottom=0.12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-m/%-d", tz=PT))
    ax.xaxis.set_major_locator(mdates.DayLocator(tz=PT))
    return fig, ax


def save(fig, src, town, pid):
    d = f"{OUT}/{src}/{town}"; os.makedirs(d, exist_ok=True)
    p = f"{d}/{pid}.png"; fig.savefig(p, facecolor=BG); plt.close(fig)
    print("wrote", p); return p


def eps_products(cycle, town, products, hours):
    steps = list(range(0, hours + 1, 6))
    params = sorted({p for pr in products for p in EPS_NEED[pr]}, key=str)
    cache = eps_fetch(cycle, params, steps)
    times = [cycle + dt.timedelta(hours=s) for s in steps]
    name = TOWNS[town][0]
    run = f"ECMWF ENS 0.25\u00b0, 50 members, {cycle:%HZ} run {cycle.astimezone(PT):%-m-%-d-%y (%-I %p PT)}"
    made = {}
    for pr in products:
        if pr == "eps_t2m_members":
            a = (series(cache, "2t", town, steps) - 273.15) * 9 / 5 + 32
            fig, ax = frame(f"{name} 2m Temperature, Members and Mean", run, ECMWF_CREDIT, "\u00b0F")
            for m in range(a.shape[1]):
                ax.plot(times, a[:, m], color=GRID if True else None, lw=0.8, alpha=0.9)
            mean = np.nanmean(a, 1)
            ax.plot(times, np.where(mean > 32, mean, np.nan), color=WARM, lw=3, label="Mean")
            ax.plot(times, np.where(mean <= 32, mean, np.nan), color=COLD, lw=3)
            ax.axhline(32, color=COLD, lw=1.4, ls="--"); ax.fill_between(times, np.nanpercentile(a, 10, 1), np.nanpercentile(a, 90, 1), color=WARM, alpha=0.15, label="10-90%")
            ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=INK, loc="upper right")
            made[pr] = save(fig, "eps", town, pr)
        elif pr == "eps_qpf_plume":
            a = series(cache, "tp", town, steps) * 1000 / 25.4  # m -> in, accumulated from start
            fig, ax = frame(f"{name} Total QPF Plume", run, ECMWF_CREDIT, "inches")
            for m in range(a.shape[1]):
                ax.plot(times, a[:, m], color=RAIN, lw=0.9, alpha=0.45)
            ax.plot(times, np.nanmean(a, 1), color=MEAN, lw=3, label=f"Mean {np.nanmean(a[-1]):.2f} in")
            ax.plot(times, np.nanmedian(a, 1), color=WARM, lw=2, ls="--", label=f"Median {np.nanmedian(a[-1]):.2f} in")
            ax.set_ylim(bottom=0); ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=INK, loc="upper left")
            made[pr] = save(fig, "eps", town, pr)
        else:
            print("renderer not written yet for", pr)
    return made


# ======================= HRRR (NOMADS filter, subregion) =======================
NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl"


def hrrr_point(day, hh, fh, vars_levs, town):
    _, la, lo = TOWNS[town]
    q = {"dir": f"/hrrr.{day}/conus", "file": f"hrrr.t{hh:02d}z.wrfsfcf{fh:02d}.grib2",
         "subregion": "", "toplat": la + 0.15, "bottomlat": la - 0.15, "leftlon": lo - 0.15, "rightlon": lo + 0.15}
    for v, l in vars_levs:
        q[f"var_{v}"] = "on"; q[f"lev_{l}"] = "on"
    url = NOMADS + "?" + "&".join(f"{k}={v}" if v != "" else k for k, v in q.items())
    blob = get(url)
    out, off = {}, 0
    while True:
        i = blob.find(b"GRIB", off)
        if i < 0:
            break
        L = int.from_bytes(blob[i + 8:i + 16], "big")
        g = ec.codes_new_from_message(blob[i:i + L])
        k = f'{ec.codes_get(g, "shortName")}:{ec.codes_get(g, "level")}:{ec.codes_get(g, "stepRange")}'
        out[k] = float(ec.codes_grib_find_nearest(g, la, lo)[0]["value"])
        ec.codes_release(g); off = i + L
    time.sleep(0.4)  # be polite to NOMADS
    return out


def latest_hrrr_long(min_fh=48):
    now = dt.datetime.now(dt.timezone.utc)
    for back in range(0, 30):
        c = (now - dt.timedelta(hours=back)).replace(minute=0, second=0, microsecond=0)
        if c.hour % 6:
            continue
        try:
            u = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/hrrr/prod/hrrr.{c:%Y%m%d}/conus/hrrr.t{c:%H}z.wrfsfcf{min_fh:02d}.grib2.idx"
            get(u, (0, 10)); return c
        except Exception:
            pass
    raise SystemExit("no long HRRR run found")


def hrrr_products(town, products):
    c0 = latest_hrrr_long()
    name = TOWNS[town][0]
    made = {}
    if "hrrr_surface_summary" in products:
        V = [("TMP", "2_m_above_ground"), ("DPT", "2_m_above_ground"), ("GUST", "surface"),
             ("UGRD", "10_m_above_ground"), ("VGRD", "10_m_above_ground"), ("APCP", "surface"), ("TCDC", "entire_atmosphere")]
        rows = [hrrr_point(f"{c0:%Y%m%d}", c0.hour, f, V, town) for f in range(0, 49)]
        t = [c0 + dt.timedelta(hours=f) for f in range(49)]
        pick = lambda pre: np.array([next((v for k, v in r.items() if k.startswith(pre)), np.nan) for r in rows])
        T = (pick("2t:") - 273.15) * 1.8 + 32; D = (pick("2d:") - 273.15) * 1.8 + 32
        G = pick("gust:") * 2.23694; W = np.hypot(pick("10u:"), pick("10v:")) * 2.23694
        # APCP hourly bucket: use the 'f-1 to f' records (k ends with stepRange 'f-1-f')
        P = np.array([next((v for k, v in r.items() if k.startswith("tp:") and k.split(":")[2] == f"{f-1}-{f}"), 0.0) if f else 0.0
                      for f, r in enumerate(rows)]) / 25.4
        C = pick("tcc:")
        fig, axs = plt.subplots(4, 1, figsize=(12, 13.5), dpi=110, sharex=True)
        fig.patch.set_facecolor(BG)
        for ax in axs:
            ax.set_facecolor(PANEL); ax.grid(color=GRID, lw=0.8); ax.tick_params(colors=INK, labelsize=10)
            [s.set_color(GRID) for s in ax.spines.values()]
        axs[0].plot(t, T, color=WARM, lw=2.5, label="Temp"); axs[0].plot(t, D, color=RAIN, lw=2, label="Dew point")
        axs[0].axhline(32, color=COLD, ls="--", lw=1.3); axs[0].set_ylabel("\u00b0F", color=INK)
        axs[1].plot(t, G, color=WARM, lw=2, label="Gust"); axs[1].plot(t, W, color=INK, lw=1.6, label="Sustained"); axs[1].set_ylabel("mph", color=INK)
        axs[2].bar(t, P, width=1 / 24 * 0.85, color=RAIN, label="Hourly precip"); axs[2].plot(t, np.cumsum(P), color=MEAN, lw=2, label=f"Total {np.sum(P):.2f} in"); axs[2].set_ylabel("in", color=INK); axs[2].set_ylim(0, max(0.05, float(np.sum(P)) * 1.15))
        axs[3].fill_between(t, C, color=MUTED, alpha=0.6, label="Cloud cover"); axs[3].set_ylim(0, 100); axs[3].set_ylabel("%", color=INK)
        for ax in axs:
            ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=INK, loc="upper right", fontsize=9)
        axs[-1].xaxis.set_major_formatter(mdates.DateFormatter("%a %-I %p", tz=PT)); axs[-1].xaxis.set_major_locator(mdates.HourLocator(byhour=[5, 17], tz=PT))
        fig.text(0.024, 0.985, f"{name} HRRR Surface Summary", color=INK, fontproperties=HS.font(800, 20), va="top")
        fig.text(0.024, 0.958, f"HRRR 3 km, {c0:%HZ} run {c0.astimezone(PT):%-m-%-d-%y (%-I %p PT)}", color=MUTED, fontsize=12, va="top")
        fig.text(0.015, 0.006, NOAA_CREDIT, color=MUTED, fontsize=9)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.94, bottom=0.04, hspace=0.12)
        made["hrrr_surface_summary"] = save(fig, "hrrr", town, "hrrr_surface_summary")
    if "hrrr_multirun_t2m" in products:
        fig, ax = frame(f"{name} HRRR Multi-run 2m Temperature", "Last 4 long HRRR runs (00/06/12/18Z), newest bold", NOAA_CREDIT, "\u00b0F")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-I %p", tz=PT)); ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[5, 17], tz=PT))
        for i, back in enumerate([18, 12, 6, 0]):
            c = c0 - dt.timedelta(hours=back)
            fhs = range(0, 49, 1 if back == 0 else 3)
            vals = [hrrr_point(f"{c:%Y%m%d}", c.hour, f, [("TMP", "2_m_above_ground")], town) for f in fhs]
            T = [(list(v.values())[0] - 273.15) * 1.8 + 32 if v else np.nan for v in vals]
            ax.plot([c + dt.timedelta(hours=f) for f in fhs], T, lw=3 if back == 0 else 1.4,
                    color=WARM if back == 0 else ["#6c6f75", "#8c8f95", "#b5b7bb"][i], label=f"{c:%HZ %-m/%-d}")
        ax.axhline(32, color=COLD, ls="--", lw=1.3)
        ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=INK, loc="upper right")
        made["hrrr_multirun_t2m"] = save(fig, "hrrr", town, "hrrr_multirun_t2m")
    return made, c0


# ======================= RRFS (NOAA operational, AWS noaa-rrfs-ops-pds, byte ranges from .idx) =======================
RRFS = "https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.2dfld.3km.f{f:03d}.conus.grib2"


def idx_point(url, wants, town):
    """wants: list of (':VAR:LEVEL:' substring, optional extra substring). Returns {var: value} at the town."""
    lines = get(url + ".idx").decode().splitlines()
    offs = [int(l.split(":")[1]) for l in lines]
    _, la, lo = TOWNS[town]; out = {}
    for key, extra in wants:
        for n, l in enumerate(lines):
            if key in l and (extra is None or extra in l):
                end = offs[n + 1] - 1 if n + 1 < len(lines) else None
                blob = get(url, (offs[n], end)) if end else get(url)[offs[n]:]
                g = ec.codes_new_from_message(blob)
                out[key] = float(ec.codes_grib_find_nearest(g, la, lo)[0]["value"]); ec.codes_release(g)
                break
    return out


def latest_rrfs_long(min_fh=60):
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 30):
        c = now - dt.timedelta(hours=b)
        if c.hour % 6: continue
        if os.environ.get("WX_CYCLE_HOUR") and c.hour != int(os.environ["WX_CYCLE_HOUR"]): continue   # scheduled run: 12Z only
        try:
            get(RRFS.format(d=f"{c:%Y%m%d}", h=c.hour, f=min_fh) + ".idx", (0, 10)); return c
        except Exception: pass
    raise SystemExit("no long RRFS run found")


def rrfs_products(town, products, hours=60, every=3):
    c0 = latest_rrfs_long(hours); name = TOWNS[town][0]; made = {}
    if "rrfs_surface_summary" in products:
        fhs = list(range(0, hours + 1, every)); rows = []
        for f in fhs:
            W = [(":TMP:2 m above ground:", None), (":DPT:2 m above ground:", None), (":GUST:surface:", None),
                 (":UGRD:10 m above ground:", None), (":VGRD:10 m above ground:", None), (":TCDC:entire atmosphere", None)]
            if f: W.append((":APCP:surface:", f":0-{f} hour acc" if f % 24 else f":0-{f // 24} day acc"))  # GRIB writes whole days as "day"
            rows.append(idx_point(RRFS.format(d=f"{c0:%Y%m%d}", h=c0.hour, f=f), W, town))
        t = [c0 + dt.timedelta(hours=f) for f in fhs]
        g = lambda k: np.array([r.get(k, np.nan) for r in rows])
        T = (g(":TMP:2 m above ground:") - 273.15) * 1.8 + 32; D = (g(":DPT:2 m above ground:") - 273.15) * 1.8 + 32
        G = g(":GUST:surface:") * 2.23694; Wd = np.hypot(g(":UGRD:10 m above ground:"), g(":VGRD:10 m above ground:")) * 2.23694
        A = g(":APCP:surface:") / 25.4; A[0] = 0; A = np.fmax.accumulate(np.nan_to_num(A)); P = np.diff(A, prepend=0).clip(0)
        C = g(":TCDC:entire atmosphere")
        fig, axs = plt.subplots(4, 1, figsize=(12, 13.5), dpi=110, sharex=True); fig.patch.set_facecolor(BG)
        for ax in axs:
            ax.set_facecolor(PANEL); ax.grid(color=GRID, lw=0.8); ax.tick_params(colors=INK, labelsize=10)
            [s.set_color(GRID) for s in ax.spines.values()]
        axs[0].plot(t, T, color=WARM, lw=2.5, label="Temp"); axs[0].plot(t, D, color=RAIN, lw=2, label="Dew point")
        axs[0].axhline(32, color=COLD, ls="--", lw=1.3); axs[0].set_ylabel("\u00b0F", color=INK)
        axs[1].plot(t, G, color=WARM, lw=2, label="Gust"); axs[1].plot(t, Wd, color=INK, lw=1.6, label="Sustained"); axs[1].set_ylabel("mph", color=INK)
        axs[2].bar(t, P, width=every / 24 * 0.85, color=RAIN, label=f"{every}-hour precip"); axs[2].plot(t, A, color=MEAN, lw=2, label=f"Total {A[-1]:.2f} in")
        axs[2].set_ylabel("in", color=INK); axs[2].set_ylim(0, max(0.05, float(A[-1]) * 1.15))
        axs[3].fill_between(t, C, color=MUTED, alpha=0.6, label="Cloud cover"); axs[3].set_ylim(0, 100); axs[3].set_ylabel("%", color=INK)
        for ax in axs: ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=INK, loc="upper right", fontsize=9)
        axs[-1].xaxis.set_major_formatter(mdates.DateFormatter("%a %-I %p", tz=PT)); axs[-1].xaxis.set_major_locator(mdates.HourLocator(byhour=[5, 17], tz=PT))
        fig.text(0.024, 0.985, f"{name} RRFS Surface Summary", color=INK, fontproperties=HS.font(800, 20), va="top")
        fig.text(0.024, 0.958, f"RRFS 3 km, {c0:%HZ} run {c0.astimezone(PT):%-m-%-d-%y (%-I %p PT)}, every {every} h", color=MUTED, fontsize=12, va="top")
        fig.text(0.015, 0.006, "Data: NOAA RRFS (public domain)", color=MUTED, fontsize=9)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.94, bottom=0.04, hspace=0.12)
        made["rrfs_surface_summary"] = save(fig, "rrfs", town, "rrfs_surface_summary")
    return made, c0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["eps", "hrrr", "rrfs"])
    ap.add_argument("--town", default="seattle", choices=list(TOWNS))
    ap.add_argument("--products", required=True)
    ap.add_argument("--hours", type=int, default=144)
    ap.add_argument("--cycle", help="EPS run YYYYMMDDHH (UTC), default newest 00/12Z")
    a = ap.parse_args()
    prods = a.products.split(",")
    if a.source == "eps":
        c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else latest_eps_cycle()
        made = eps_products(c, a.town, prods, a.hours); run = f"{c:%Y%m%d%H}"
    elif a.source == "rrfs":
        made, c = rrfs_products(a.town, prods); run = f"{c:%Y%m%d%H}"
    else:
        made, c = hrrr_products(a.town, prods); run = f"{c:%Y%m%d%H}"
    os.makedirs(f"{OUT}", exist_ok=True)
    mf = f"{OUT}/made.json"
    m = json.load(open(mf)) if os.path.exists(mf) else {}
    for pid, p in made.items():
        m.setdefault(a.source, {}).setdefault(a.town, {})[pid] = {"src": os.path.relpath(p, os.path.dirname(OUT)), "run": run,
                                                                  "made": dt.datetime.now(PT).isoformat(timespec="minutes")}
    json.dump(m, open(mf, "w"), indent=1)
