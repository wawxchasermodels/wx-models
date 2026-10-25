#!/usr/bin/env python3
"""Town meteograms for every town at once: ECMWF ENS (50 members), NOAA HRRR and NOAA RRFS.

One download serves all towns: each needed GRIB record is fetched once (HTTP byte ranges from the .idx/.index files),
the values at every town are pulled out, and those small numbers are kept in a per-run point cache
(CACHE/<src>_<cycle>.json) so multi-run charts reuse earlier runs instead of downloading them again.
Charts go to OUT/<src>/<town>/<product>.png and are listed in OUT/made.json for the site manifest.

usage: meteo_suite.py eps|hrrr|rrfs [--cycle YYYYMMDDHH] [--hours N] [--every H] [--products a,b] [--towns a,b] [--runs 4]
"""
import argparse, datetime as dt, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np, eccodes as ec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker
from matplotlib.colors import BoundaryNorm, ListedColormap
import meteograms as MG
import house_style as HS
import member_grid as GRID_

PT, TOWNS, OUT, CACHE = MG.PT, MG.TOWNS, MG.OUT, MG.CACHE
BG, PANEL, GRID, INK, MUTED = MG.BG, MG.PANEL, MG.GRID, MG.INK, MG.MUTED
WARM, COLD, RAIN, SNOW, MEAN = MG.WARM, MG.COLD, MG.RAIN, MG.SNOW, MG.MEAN
ICE, PLUM = "#ff5fa2", "#b48cff"
MPH = 2.23694
HRRR_URL = {"sfc": "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfsfcf{f:02d}.grib2",
            "prs": "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfprsf{f:02d}.grib2",
            "nat": "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfnatf{f:02d}.grib2"}
RRFS_URL = {"sfc": "https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.2dfld.3km.f{f:03d}.conus.grib2",
            "prs": "https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.prslev.3km.f{f:03d}.conus.grib2"}
CREDIT = {"eps": MG.ECMWF_CREDIT, "hrrr": "Data: NOAA HRRR (public domain)", "rrfs": "Data: NOAA RRFS (public domain)"}


def get(url, rng=None):
    return MG.get(url, rng)


# ------------------------------------------------------------------------------------------------- point cache
class Points:
    def __init__(self, src, c):
        self.path = f"{CACHE}/{src}_{c:%Y%m%d%H}.json"; os.makedirs(CACHE, exist_ok=True)
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {}

    def has(self, key, f):   # cached only when every current town is in it (the town list can change between runs)
        v = self.d.get(f"{key}|{f}"); return isinstance(v, dict) and all(t in v for t in TOWNS)
    def put(self, key, f, vals): self.d[f"{key}|{f}"] = vals
    def get(self, key, f, town):
        v = (self.d.get(f"{key}|{f}") or {}).get(town)
        if isinstance(v, dict): v = [v[k] for k in sorted(v, key=int)]   # older meteograms.py cache: {member: value}
        return v
    def save(self): json.dump(self.d, open(self.path, "w"))


# ------------------------------------------------------------------------------------------------- NOAA (HRRR / RRFS)
_NEAR = {}
def town_index(g):
    """Nearest grid point to each town for this grid (computed once per grid size)."""
    k = (ec.codes_get(g, "Nx"), ec.codes_get(g, "Ny"))
    if k not in _NEAR:
        la = ec.codes_get_array(g, "latitudes"); lo = ec.codes_get_array(g, "longitudes"); lo = np.where(lo > 180, lo - 360, lo)
        _NEAR[k] = {t: int(np.argmin((la - v[1]) ** 2 + ((lo - v[2]) * np.cos(np.radians(v[1]))) ** 2)) for t, v in TOWNS.items()}
    return _NEAR[k]


def idx_lines(url):
    L = get(url + ".idx").decode().splitlines(); return [l.split(":") for l in L], [int(l.split(":")[1]) for l in L]


def pick(lines, var, lev, kind):
    """Index of the first idx record for VAR:LEVEL of the wanted kind: 'inst' (no ave/acc/max/min) or 'acc0' (0-N run total)."""
    for n, p in enumerate(lines):
        if len(p) < 6 or p[3] != var or p[4] != lev: continue
        st = p[5]
        if kind == "inst" and not any(w in st for w in ("ave", "acc", "max", "min")): return n
        if kind == "acc0" and (st.startswith("0-") and "acc" in st): return n
    return None


def noaa_fetch(P, urls, c, f, wants):
    """wants: list of (file, var, level, kind, cache_key). Fetch missing records of forecast hour f, store town values."""
    todo = [w for w in wants if not P.has(w[4], f)]
    if not todo: return 0
    nbytes = 0; jobs = []
    byfile = {}
    for w in todo: byfile.setdefault(w[0], []).append(w)
    for fk, ws in byfile.items():
        url = urls[fk].format(d=f"{c:%Y%m%d}", h=c.hour, f=f)
        try: lines, offs = idx_lines(url)
        except Exception: continue
        for w in ws:
            n = pick(lines, w[1], w[2], w[3])
            if n is None: continue
            jobs.append((url, offs[n], offs[n + 1] - 1 if n + 1 < len(offs) else None, w[4]))
    def one(j):
        url, a, b, key = j
        blob = get(url, (a, b if b is not None else a + 40_000_000)); g = ec.codes_new_from_message(blob)
        ti = town_index(g); v = ec.codes_get_values(g); ec.codes_release(g)
        return key, {t: float(v[i]) for t, i in ti.items()}, len(blob)
    with ThreadPoolExecutor(8) as ex:
        for key, vals, n in ex.map(one, jobs): P.put(key, f, vals); nbytes += n
    return nbytes


def prs_levels(urls, c, f):
    lines, _ = idx_lines(urls["prs"].format(d=f"{c:%Y%m%d}", h=c.hour, f=f))
    return sorted({int(p[4].split()[0]) for p in lines if len(p) > 5 and p[3] == "TMP" and p[4].endswith(" mb") and p[4].split()[0].isdigit()}, reverse=True)


# ------------------------------------------------------------------------------------------------- chart helpers
def frame(title, sub, src, ylabel, hourly=False, size=(12, 6.75)):
    fig, ax = MG.frame(title, sub, CREDIT[src], ylabel)
    if size != (12, 6.75): fig.set_size_inches(*size)
    if hourly:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-I %p", tz=PT)); ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[5, 17], tz=PT))
    return fig, ax


def floor0(ax, top=0.25):
    """y from 0, and at least `top` tall so an all-zero chart (no snow) reads as zero, not as noise."""
    lo, hi = ax.get_ylim(); ax.set_ylim(0, max(hi, top))


def legend(ax, loc="upper right"): ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=INK, loc=loc, fontsize=9.5)


def members(ax, t, A, color, mean_label="Mean", lw=0.8, alpha=0.55):
    for m in range(A.shape[1]): ax.plot(t, A[:, m], color=color, lw=lw, alpha=alpha)
    mu = np.nanmean(A, 1); ax.plot(t, mu, color=MEAN, lw=3, label=mean_label)
    ax.plot(t, np.nanmedian(A, 1), color=WARM, lw=1.8, ls="--", label="Median"); return mu


def bands(ax, t, A, color, label):
    q = np.nanpercentile(A, [10, 25, 50, 75, 90], 1)
    ax.fill_between(t, q[0], q[4], color=color, alpha=0.18, label=f"{label} 10-90%")
    ax.fill_between(t, q[1], q[3], color=color, alpha=0.38, label=f"{label} 25-75%")
    ax.plot(t, q[2], color=color, lw=2.6, label=f"{label} median")


def runline(src, c, every=None):
    name = {"eps": "ECMWF ENS 0.25\u00b0, 50 members", "hrrr": "HRRR 3 km", "rrfs": "RRFS 3 km"}[src]
    return f"{name}, {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}" + (f", every {every} h" if every else "")


SMOKE_LEVELS = [2, 4, 8, 12, 20, 35, 55, 100, 150, 250, 500]
SMOKE_COLS = ["#d9d4c7", "#c6b98f", "#b89b5c", "#a87b3d", "#93602e", "#7d4626", "#6a2e2a", "#5a1d3a", "#4a1450", "#300a3c"]
RH_LEVELS = list(range(0, 101, 10))
RH_COLS = ["#7a5230", "#9b6e3f", "#c2995e", "#e3cf98", "#eef0d8", "#c9e6c0", "#8fcf9a", "#4fae7d", "#2b8a72", "#1d6a6a"]


def xsec(ax, t, y, Z, levels, cmap, norm=None):
    T, Y = np.meshgrid(mdates.date2num(t), y, indexing="ij")
    return ax.contourf(T, Y, Z, levels=levels, cmap=cmap, norm=norm or BoundaryNorm(levels, cmap.N), extend="both")


def wetbulb(T, RH):   # Stull (2011), T in C, RH in %; good to ~1 C for normal surface-to-mid-level conditions
    RH = np.clip(RH, 5, 100)
    return (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659)) + np.arctan(T + RH) - np.arctan(RH - 1.676331)
            + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH) - 4.686035)


def save(fig, src, town, pid):
    return MG.save(fig, src, town, pid)


# ================================================================================================= ECMWF ENS
EF = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-ef"
EF_MIRROR = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/{d}/{h:02d}z/ifs/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-ef"
CF_PARAMS = {"10fg", "mx2t3", "mn2t3", "tp"}
# ECMWF renames some ENS fields by step: 10fg3 (3 h max gust) at 93-144 h, mx2t6/mn2t6 (6 h max/min) after 144 h. Stored
# under the base name so each series is continuous (before 10-25-26 those steps were simply missing from the charts).
EPS_ALIAS = {"10fg3": "10fg", "mx2t6": "mx2t3", "mn2t6": "mn2t3"}   # control run also fetched for these (member-grid meteograms)
EPS_PARAMS = {"2t": None, "tp": None, "sf": None, "mx2t3": None, "mn2t3": None, "tcc": None, "10fg": None, "mucape": None,
              "tcwv": None, "gh": "500", "t": "850"}
_MIRROR_OK = [True]


def eps_native(s): return s % 3 == 0 if s <= 144 else s % 6 == 0


def eps_fetch(P, c, s, params):
    """Town values of all 50 members for the wanted params at step s -> P['<param><lev>'|s] = {town: [m1..m50]}."""
    key = lambda p: f"{p}{EPS_PARAMS[p] or ''}"
    want = [(p, EPS_PARAMS[p]) for p in params if not P.has(key(p), s)]
    want_cf = [(p, EPS_PARAMS[p]) for p in params if p in CF_PARAMS and not P.has(key(p) + "_cf", s)]   # control run
    if not want and not want_cf: return 0
    base = EF.format(d=f"{c:%Y%m%d}", h=c.hour, s=s); mirror = EF_MIRROR.format(d=f"{c:%Y%m%d}", h=c.hour, s=s)
    try: idx = [json.loads(l) for l in get(base + ".index").decode().splitlines()]
    except Exception: return 0
    pn = lambda r: EPS_ALIAS.get(r["param"], r["param"])
    recs = sorted([r for r in idx if (r.get("type") == "pf" and any(pn(r) == p and r.get("levelist") == l for p, l in want))
                   or (r.get("type") == "cf" and any(pn(r) == p and r.get("levelist") == l for p, l in want_cf))], key=lambda r: r["_offset"])
    groups = []
    for r in recs:
        a, b = r["_offset"], r["_offset"] + r["_length"] - 1
        if groups and a == groups[-1][1] + 1: groups[-1][1] = b
        else: groups.append([a, b])

    def fetch(ab):
        if _MIRROR_OK[0]:
            try:
                rq = urllib.request.Request(mirror + ".grib2", headers={"Range": "bytes=%d-%d" % tuple(ab), "User-Agent": "wx-models (personal)"})
                with urllib.request.urlopen(rq, timeout=60) as r: return r.read()
            except Exception: _MIRROR_OK[0] = False
        return get(base + ".grib2", tuple(ab))
    with ThreadPoolExecutor(8) as ex: blobs = list(ex.map(fetch, groups))
    got, n = {}, 0
    for blob in blobs:
        n += len(blob); off = 0
        while True:
            i = blob.find(b"GRIB", off)
            if i < 0: break
            L = int.from_bytes(blob[i + 8:i + 16], "big"); g = ec.codes_new_from_message(blob[i:i + L])
            sn = ec.codes_get(g, "shortName"); sn = EPS_ALIAS.get(sn, sn); lev = str(ec.codes_get(g, "level")) if ec.codes_get(g, "typeOfLevel") == "isobaricInhPa" else ""
            num = ec.codes_get(g, "number"); ni = ec.codes_get(g, "Ni")
            if ec.codes_get(g, "dataType") == "cf": lev += "_cf"   # control run (number 0) kept apart from the 50 members
            la0, lo0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
            d = ec.codes_get(g, "iDirectionIncrementInDegrees"); v = ec.codes_get_values(g); ec.codes_release(g)
            for t, (_, la, lo) in TOWNS.items():
                ii = int(round((la0 - la) / d)); jj = int(round(((lo - lo0) % 360) / d)) % ni
                got.setdefault(f"{sn}{lev}", {}).setdefault(t, {})[num] = float(v[ii * ni + jj])
            off = i + L
    for k, towns in got.items(): P.put(k, s, {t: [m[x] for x in sorted(m)] for t, m in towns.items()})
    return n


def eps_series(P, key, town, steps):
    rows = [P.get(key, s, town) for s in steps]; nm = max((len(r) for r in rows if r), default=50)
    A = np.full((len(steps), nm), np.nan)
    for i, r in enumerate(rows):
        if r: A[i, :len(r)] = r
    return A


def pt_days(times):
    return sorted({t.astimezone(PT).date() for t in times})


def daily(times, A, fn):
    """Per PT calendar day, apply fn over that day's rows (members kept). Days with fewer than 4 values are dropped."""
    days, out = [], []
    for d in pt_days(times):
        k = [i for i, t in enumerate(times) if t.astimezone(PT).date() == d and np.isfinite(A[i]).any()]
        if len(k) >= 4: days.append(d); out.append(fn(A[k], 0))
    return days, np.array(out)


def eps_charts(c, towns, prods, hours, every, runs):
    steps = [s for s in range(0, hours + 1, 3) if eps_native(s) and (s % every == 0 or s == 0)]
    P = Points("eps", c); n = 0
    with ThreadPoolExecutor(2) as ex:
        want_p = os.environ.get("METEO_EPS_PARAMS", "").split(",") if os.environ.get("METEO_EPS_PARAMS") else list(EPS_PARAMS)   # tests only
        for k in ex.map(lambda s: eps_fetch(P, c, s, want_p), steps): n += k
    P.save()
    past = []   # earlier runs for multi-run charts: whatever is cached, plus fetch the light fields for missing ones
    if any(p.startswith("eps_mr_") for p in prods):
        for b in range(1, runs):
            cc = c - dt.timedelta(hours=12 * b); Q = Points("eps", cc)
            st = [s for s in range(0, hours + 1 + 12 * b, 12)]
            for s in st: n += eps_fetch(Q, cc, s, ["2t", "tp", "sf", "mx2t3", "mn2t3"])
            Q.save(); past.append((cc, Q, st))
    print(f"EPS {c:%Y%m%d%H}Z: downloaded {n/1e6:.0f} MB", flush=True)
    T = [c + dt.timedelta(hours=s) for s in steps]; made = {}
    for town in towns:
        name = TOWNS[town][0]; run = runline("eps", c); S = lambda k: eps_series(P, k, town, steps)
        t2 = (S("2t") - 273.15) * 1.8 + 32; tp = S("tp") * 1000 / 25.4; sn = S("sf") * 1000 / 25.4 * 10
        tp[0] = 0; sn[0] = 0
        mx = (S("mx2t3") - 273.15) * 1.8 + 32; mn = (S("mn2t3") - 273.15) * 1.8 + 32
        def mk(pid, title, ylabel, draw):
            if pid not in prods: return
            fig, ax = frame(f"{name} {title}", run, "eps", ylabel); draw(ax); made.setdefault(town, {})[pid] = save(fig, "eps", town, pid)
        def roll(A, h):   # running h-hour total from a run-total series
            out = np.full_like(A, np.nan)
            for i, s in enumerate(steps):
                j = steps.index(s - h) if (s - h) in steps else (0 if s - h == 0 else None)
                if s >= h and j is not None: out[i] = A[i] - A[j]
            return np.clip(out, 0, None)
        def six(A, fn):   # 6 h max/min from the 3-hourly max/min fields (pairs of steps)
            out = np.full_like(A, np.nan)
            for i, s in enumerate(steps):
                if s % 6 or s == 0: continue
                k = [steps.index(x) for x in (s - 3, s) if x in steps and x > 0]
                out[i] = fn(A[k], 0)
            return out
        T6 = [t for t, s in zip(T, steps) if s % 6 == 0 and s]
        pick6 = lambda A: A[[i for i, s in enumerate(steps) if s % 6 == 0 and s]]

        def d_t2m(ax):
            members(ax, T, t2, MUTED); ax.axhline(32, color=COLD, lw=1.4, ls="--"); legend(ax)
        mk("eps_t2m_members", "2 m Temperature: Members and Mean", "\u00b0F", d_t2m)

        hi_days, hi = daily(T[1:], mx[1:], np.nanmax); lo_days, lo = daily(T[1:], mn[1:], np.nanmin)
        def d_hilo(ax):
            x = np.arange(len(hi_days))
            for arr, col, lab, off in ((hi, WARM, "High", -0.17), (lo, COLD, "Low", 0.17)):
                if not len(arr): continue
                q = np.nanpercentile(arr, [10, 25, 50, 75, 90], 1)
                ax.vlines(x[:len(arr)] + off, q[0], q[4], color=col, lw=1.6)
                ax.bar(x[:len(arr)] + off, q[3] - q[1], bottom=q[1], width=0.3, color=col, alpha=0.55, label=f"{lab}: 25-75% box, 10-90% whisker")
                ax.scatter(x[:len(arr)] + off, q[2], color=MEAN, s=26, zorder=5)
                for xi, v in zip(x[:len(arr)] + off, q[2]): ax.text(xi, v + 1, f"{v:.0f}", color=INK, ha="center", fontsize=9)
            ax.set_xticks(x); ax.set_xticklabels([f"{d:%a %-m/%-d}" for d in hi_days]); ax.axhline(32, color=COLD, lw=1.2, ls="--"); legend(ax, "upper left")
        if hi_days:
            fig, ax = MG.frame(f"{name} Daily High / Low Temperature", run + "  \u00b7  dots = median of 50 members", CREDIT["eps"], "\u00b0F")
            ax.xaxis.set_major_locator(matplotlib.ticker.AutoLocator()); ax.xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
            if "eps_daily_hilo" in prods: d_hilo(ax); made.setdefault(town, {})["eps_daily_hilo"] = save(fig, "eps", town, "eps_daily_hilo")
            else: plt.close(fig)
        def daily_members(pid, title, days, arr, col):
            if pid not in prods or not len(days): return
            fig, ax = frame(f"{name} {title}", run, "eps", "\u00b0F")
            tt = [dt.datetime(d.year, d.month, d.day, 12, tzinfo=PT) for d in days]
            members(ax, tt, arr, col, lw=1.0)
            if len(tt) < 3: [ax.scatter(tt, arr[:, m], color=col, s=10, alpha=0.6) for m in range(arr.shape[1])]
            ax.axhline(32, color=COLD, lw=1.2, ls="--"); legend(ax)
            made.setdefault(town, {})[pid] = save(fig, "eps", town, pid)
        # member grids (10-25-26): one row per member, control run on its own row, ensemble mean last
        Sc = lambda k: eps_series(P, k + "_cf", town, steps)[:, :1]
        def grid(pid, title, unit, note, times, A, Ac, fmt, levels, colors, daily_cols=False):
            if pid not in prods or not len(times): return
            hdr = [((f"{t:%a %-m/%-d}", "") if daily_cols else (f"{t.astimezone(PT):%a %-m/%-d}", f"{t.astimezone(PT):%-I %p}")) for t in times]
            ctrl = None if Ac is None or len(Ac) != len(times) or not np.isfinite(Ac).any() else Ac[:, 0]
            nm = A.shape[1]
            sub = run
            p_ = f"{OUT}/eps/{town}/{pid}.png"; os.makedirs(os.path.dirname(p_), exist_ok=True)
            mean = GRID_.grid_png(p_, f"{name} {title}", sub, CREDIT["eps"], hdr, ctrl, A.T, fmt, levels, colors, unit,
                                  note, f"CTRL = control run (member 0, unperturbed)  \u00b7  rows 1-{nm} = perturbed members  \u00b7  "
                                  f"MEAN = average of {'the control + ' if ctrl is not None else ''}{nm} members"
                                  + ("" if ctrl is not None else "  \u00b7  control not in this run's ECMWF open-data file"))
            print("wrote", p_); made.setdefault(town, {})[pid] = p_
        f0 = lambda v: f"{v:.0f}"; f2 = lambda v: f"{v:.2f}"
        mxc, mnc = (Sc("mx2t3") - 273.15) * 1.8 + 32, (Sc("mn2t3") - 273.15) * 1.8 + 32
        hi_c = daily(T[1:], mxc[1:], np.nanmax)[1] if len(hi_days) else None
        lo_c = daily(T[1:], mnc[1:], np.nanmin)[1] if len(lo_days) else None
        TL = [-20, 0, 10, 20, 32, 40, 50, 60, 70, 80, 90, 100]
        TC = ["#7f4fd6", "#5b6ee8", "#4f9be8", "#5fc3e8", "#7fd6c4", "#8fd68f", "#c4de6a", "#f0d45a", "#f0a040", "#e8603c", "#c0304a", "#a01860"]
        grid("eps_tmax_members", "Daily High Temperature: Each Member + Mean", "\u00b0F", "Highest of the 3 h max temps (6 h after day 6) in each PT day",
             hi_days, hi, hi_c, f0, TL, TC, daily_cols=True)
        grid("eps_tmin_members", "Daily Low Temperature: Each Member + Mean", "\u00b0F", "Lowest of the 3 h min temps (6 h after day 6) in each PT day",
             lo_days, lo, lo_c, f0, TL, TC, daily_cols=True)
        if "eps_spread_maxmin" in prods and len(hi_days):
            fig, ax = frame(f"{name} Spread: Daily High and Low", run, "eps", "\u00b0F")
            bands(ax, [dt.datetime(d.year, d.month, d.day, 12, tzinfo=PT) for d in hi_days], hi, WARM, "High")
            bands(ax, [dt.datetime(d.year, d.month, d.day, 12, tzinfo=PT) for d in lo_days], lo, COLD, "Low")
            ax.axhline(32, color=COLD, lw=1.2, ls="--"); legend(ax, "upper left"); made.setdefault(town, {})["eps_spread_maxmin"] = save(fig, "eps", town, "eps_spread_maxmin")

        def plume(A, col, unit_note):
            def d(ax):
                for m in range(A.shape[1]): ax.plot(T, A[:, m], color=col, lw=0.9, alpha=0.45)
                ax.plot(T, np.nanmean(A, 1), color=MEAN, lw=3, label=f"Mean {np.nanmean(A[-1]):.2f} in")
                ax.plot(T, np.nanmedian(A, 1), color=WARM, lw=2, ls="--", label=f"Median {np.nanmedian(A[-1]):.2f} in")
                floor0(ax); legend(ax, "upper left")
            return d
        mk("eps_qpf_plume", "Total Precipitation Plume", "inches (liquid)", plume(tp, RAIN, ""))
        mk("eps_snow_plume", "Total Snow Plume (10:1)", "inches of snow", plume(sn, SNOW, ""))

        def totals_bar(A, col, unit):
            def d(ax):
                ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(10)); ax.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%d"))
                v = np.sort(A[-1][np.isfinite(A[-1])]); ax.bar(np.arange(1, len(v) + 1), v, color=col, alpha=0.85, label="Each member, sorted")
                ax.axhline(np.nanmean(v), color=MEAN, lw=2.5, label=f"Mean {np.nanmean(v):.2f} {unit}"); floor0(ax)
                ax.set_xlabel(f"Member (sorted low to high), total to {T[-1].astimezone(PT):%a %-m/%-d %-I %p} PT", color=INK); legend(ax, "upper left")
            return d
        tpc = Sc("tp") * 1000 / 25.4; tpc[0] = 0
        QL = [0.01, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4]
        QC = ["#2f6f3f", "#3f9f4f", "#5fbf5a", "#9fd65a", "#e0e05a", "#f0b040", "#f07a30", "#e04040", "#c02a70", "#9a2ab0"]
        i6 = [i for i, s_ in enumerate(steps) if s_ % 6 == 0 and s_]
        grid("eps_qpf_members", "Total Precipitation: Each Member + Mean", "in", "Run total from the start of the run to each time (liquid)",
             [T[i] for i in i6], tp[i6], tpc[i6], f2, QL, QC)
        mk("eps_snow_members", "Total Snow by Member (10:1)", "inches of snow", totals_bar(sn, SNOW, "in"))
        q24, s24 = roll(tp, 24), roll(sn, 24)
        def d_roll(A, col):
            def d(ax): members(ax, T, A, col); floor0(ax); legend(ax, "upper left")
            return d
        i24 = [i for i, s_ in enumerate(steps) if s_ % 24 == 0 and s_]
        q24c = roll(tpc, 24)
        grid("eps_qpf24_members", "24-Hour Precipitation: Each Member + Mean", "in", "Liquid precipitation in the 24 h ending at each time",
             [T[i] for i in i24], q24[i24], q24c[i24], f2, QL, QC)
        mk("eps_snow24_members", "24-Hour Snow (10:1): Members and Mean", "inches in prior 24 h", d_roll(s24, SNOW))
        mk("eps_tcc_members", "Cloud Cover: Members and Mean", "%", lambda ax: (members(ax, T, S("tcc") * 100, MUTED), ax.set_ylim(0, 100), legend(ax)))
        g = S("10fg") * MPH; g6 = six(g, np.nanmax)
        gc = Sc("10fg") * MPH; g6c = six(gc, np.nanmax)
        GL = [10, 20, 30, 40, 45, 50, 58, 70]
        GC = ["#3f6f9f", "#4f9fbf", "#6fbf8f", "#d6d65a", "#f0b040", "#f07a30", "#e04040", "#b02ab0"]
        grid("eps_gust_members", "Max Wind Gust: Each Member + Mean", "mph",
             "Max 10 m gust in the 3 h (6 h after day 6) ending at each time; ECMWF ENS has no hourly output",
             T6, pick6(g6), pick6(g6c), f0, GL, GC)
        mk("eps_mucape_members", "Most-Unstable CAPE: Members and Mean", "J/kg", lambda ax: (members(ax, T, S("mucape"), PLUM), ax.set_ylim(bottom=0), legend(ax)))
        mk("eps_pwat_members", "Precipitable Water: Members and Mean", "inches", lambda ax: (members(ax, T, S("tcwv") / 25.4, RAIN), ax.set_ylim(bottom=0), legend(ax)))
        mk("eps_spread_qpf", "Spread: Total Precipitation", "inches (liquid)", lambda ax: (bands(ax, T, tp, RAIN, "Total"), ax.set_ylim(bottom=0), legend(ax, "upper left")))
        if "eps_z500_t850" in prods:
            fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 9), dpi=120, sharex=True); fig.patch.set_facecolor(BG)
            for ax in (a1, a2):
                ax.set_facecolor(PANEL); ax.grid(color=GRID, lw=0.8); ax.tick_params(colors=INK, labelsize=10); [s_.set_color(GRID) for s_ in ax.spines.values()]
            members(a1, T, S("gh500") / 10, MUTED); a1.set_ylabel("500 mb height (dam)", color=INK); legend(a1)
            members(a2, T, S("t850") - 273.15, COLD); a2.axhline(0, color=COLD, lw=1.2, ls="--"); a2.axhline(-5, color=SNOW, lw=1, ls=":")
            a2.set_ylabel("850 mb temp (\u00b0C)", color=INK); legend(a2)
            a2.xaxis.set_major_formatter(mdates.DateFormatter("%a %-m/%-d", tz=PT)); a2.xaxis.set_major_locator(mdates.DayLocator(tz=PT))
            fig.text(0.024, 0.975, f"{name} 500 mb Height and 850 mb Temperature", color=INK, fontproperties=HS.font(800, 20), va="top")
            fig.text(0.024, 0.94, run + "  \u00b7  850 mb: 0\u00b0C dashed, -5\u00b0C dotted (lowland snow rule of thumb)", color=HS.ACCENT, fontproperties=HS.font(600, 12), va="top")
            fig.text(0.024, 0.008, CREDIT["eps"], color=MUTED, fontproperties=HS.font(500, 9.5)); fig.subplots_adjust(left=0.08, right=0.98, top=0.9, bottom=0.07, hspace=0.1)
            made.setdefault(town, {})["eps_z500_t850"] = save(fig, "eps", town, "eps_z500_t850")

        # multi-run: ensemble mean of each run, newest bold
        mr = {"eps_mr_t2m": ("2 m Temperature", "\u00b0F", lambda Q, st: (eps_series(Q, "2t", town, st) - 273.15) * 1.8 + 32, None),
              "eps_mr_tmax6": ("Max Temperature (3 h window ending each step)", "\u00b0F", lambda Q, st: (eps_series(Q, "mx2t3", town, st) - 273.15) * 1.8 + 32, "max"),
              "eps_mr_tmin6": ("Min Temperature (3 h window ending each step)", "\u00b0F", lambda Q, st: (eps_series(Q, "mn2t3", town, st) - 273.15) * 1.8 + 32, "min"),
              "eps_mr_qpf6": ("6-Hour Precipitation", "inches", lambda Q, st: eps_series(Q, "tp", town, st) * 1000 / 25.4, 6),
              "eps_mr_snow6": ("6-Hour Snow (10:1)", "inches", lambda Q, st: eps_series(Q, "sf", town, st) * 10000 / 25.4, 6),
              "eps_mr_qpf24": ("24-Hour Precipitation", "inches", lambda Q, st: eps_series(Q, "tp", town, st) * 1000 / 25.4, 24),
              "eps_mr_snow24": ("24-Hour Snow (10:1)", "inches", lambda Q, st: eps_series(Q, "sf", town, st) * 10000 / 25.4, 24),
              "eps_mr_qpf": ("Total Precipitation", "inches", lambda Q, st: eps_series(Q, "tp", town, st) * 1000 / 25.4, "tot"),
              "eps_mr_snow": ("Total Snow (10:1)", "inches", lambda Q, st: eps_series(Q, "sf", town, st) * 10000 / 25.4, "tot")}
        for pid, (title, unit, fn, mode) in mr.items():
            if pid not in prods: continue
            fig, ax = frame(f"{name} Multi-run: {title}", f"Ensemble mean of the last {1 + len(past)} ENS runs, newest bold", "eps", unit)
            shades = ["#b5b7bb", "#8c8f95", "#6c6f75"]
            for k, (cc, Q, st) in enumerate([(c, P, steps)] + past):
                A = fn(Q, st); tt = np.array([cc + dt.timedelta(hours=s) for s in st])
                if isinstance(mode, int):   # increments over the window, from the run total
                    tot = np.nanmean(A, 1); tot[0] = 0 if st[0] == 0 else tot[0]
                    inc = [tot[i] - tot[st.index(s - mode)] if (s - mode) in st else np.nan for i, s in enumerate(st)]
                    y = np.clip(np.array(inc), 0, None)
                elif mode == "tot": y = np.nanmean(A, 1); y[0] = 0
                else: y = np.nanmean(A, 1); y[0] = np.nan
                ax.plot(tt, y, lw=3 if k == 0 else 1.5, color=WARM if k == 0 else shades[min(k - 1, 2)], label=f"{cc:%HZ %-m/%-d}")
            if unit == "\u00b0F": ax.axhline(32, color=COLD, lw=1.2, ls="--")
            else: floor0(ax)
            legend(ax, "upper left"); made.setdefault(town, {})[pid] = save(fig, "eps", town, pid)
    return made


# ================================================================================================= HRRR / RRFS
def latest_long(src, min_f):
    urls = HRRR_URL if src == "hrrr" else RRFS_URL
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 36):
        c = now - dt.timedelta(hours=b)
        if c.hour % 6: continue
        if os.environ.get("WX_CYCLE_HOUR") and c.hour != int(os.environ["WX_CYCLE_HOUR"]): continue   # scheduled run: 12Z only
        try: get(urls["sfc"].format(d=f"{c:%Y%m%d}", h=c.hour, f=min_f) + ".idx", (0, 10)); return c
        except Exception: pass
    raise SystemExit(f"no long {src} run found")


SFC = [("sfc", "TMP", "2 m above ground", "inst", "t2"), ("sfc", "DPT", "2 m above ground", "inst", "td"),
       ("sfc", "GUST", "surface", "inst", "gust"), ("sfc", "UGRD", "10 m above ground", "inst", "u"), ("sfc", "VGRD", "10 m above ground", "inst", "v"),
       ("sfc", "APCP", "surface", "acc0", "apcp"), ("sfc", "TCDC", "entire atmosphere", "inst", "tcc"),
       ("sfc", "TCDC", "entire atmosphere (considered as a single layer)", "inst", "tcc"),
       ("sfc", "ASNOW", "surface", "acc0", "asnow"), ("sfc", "PRES", "surface", "inst", "psfc"),
       ("sfc", "CRAIN", "surface", "inst", "crain"), ("sfc", "CSNOW", "surface", "inst", "csnow"),
       ("sfc", "CFRZR", "surface", "inst", "cfrzr"), ("sfc", "CICEP", "surface", "inst", "cicep")]
SMOKE_SFC = [("sfc", "MASSDEN", "8 m above ground", "inst", "smoke8"), ("sfc", "COLMD", "entire atmosphere (considered as a single layer)", "inst", "colmd")]
NAT_LEVELS = list(range(1, 51))


def hires_charts(src, c, towns, prods, hours, every, runs):
    urls = HRRR_URL if src == "hrrr" else RRFS_URL; P = Points(src, c); n = 0
    fh = list(range(0, hours + 1, every)); fx = [f for f in fh if f % max(every, 3) == 0]
    want_x = any(("xsec" in p and "smoke" not in p) or "thermal" in p for p in prods)
    want_smoke = src == "hrrr" and any("smoke_xsec" in p for p in prods)
    levs = prs_levels(urls, c, 0) if want_x else []
    def step(f):
        w = list(SFC) + (SMOKE_SFC if src == "rrfs" else [])
        if want_x and f in fx:
            w += [("prs", v, f"{L} mb", "inst", f"{v}:{L}") for L in levs for v in ("TMP", "RH")]
        if want_smoke and f in fx:
            w += [("nat", "MASSDEN", f"{k} hybrid level", "inst", f"smoke:{k}") for k in NAT_LEVELS]
            if f == 0: w += [("nat", "HGT", f"{k} hybrid level", "inst", f"hgt:{k}") for k in NAT_LEVELS] + [("sfc", "HGT", "surface", "inst", "hsfc")]
        return noaa_fetch(P, urls, c, f, w)
    with ThreadPoolExecutor(2) as ex:
        for k in ex.map(step, fh): n += k
    P.save()
    past = []
    if any("multirun" in p for p in prods):
        for b in range(1, runs):
            cc = c - dt.timedelta(hours=6 * b); Q = Points(src, cc)
            for f in range(0, hours + 1, max(every, 3)):
                n += noaa_fetch(Q, urls, cc, f, [w for w in SFC if w[4] in ("t2", "apcp", "asnow")])
            Q.save(); past.append((cc, Q))
    print(f"{src.upper()} {c:%Y%m%d%H}Z: downloaded {n/1e6:.0f} MB", flush=True)
    T = [c + dt.timedelta(hours=f) for f in fh]; made = {}; tag = src.upper(); run = runline(src, c, every)
    for town in towns:
        name = TOWNS[town][0]
        g = lambda k, Q=P, ff=fh: np.array([np.nan if Q.get(k, f, town) is None else Q.get(k, f, town) for f in ff])
        t2 = (g("t2") - 273.15) * 1.8 + 32; td = (g("td") - 273.15) * 1.8 + 32
        A = np.nan_to_num(g("apcp")) / 25.4; A[0] = 0; A = np.fmax.accumulate(A); Pinc = np.diff(A, prepend=0).clip(0)
        SN = np.fmax.accumulate(np.nan_to_num(g("asnow")) * 39.3701); SN[0] = 0
        def out(pid, fig): made.setdefault(town, {})[pid] = save(fig, src, town, pid)
        def panels(k, h=13.5):
            fig, axs = plt.subplots(k, 1, figsize=(12, h), dpi=110, sharex=True); fig.patch.set_facecolor(BG)
            for ax in axs:
                ax.set_facecolor(PANEL); ax.grid(color=GRID, lw=0.8); ax.tick_params(colors=INK, labelsize=10); [s_.set_color(GRID) for s_ in ax.spines.values()]
            axs[-1].xaxis.set_major_formatter(mdates.DateFormatter("%a %-I %p", tz=PT)); axs[-1].xaxis.set_major_locator(mdates.HourLocator(byhour=[5, 17], tz=PT))
            return fig, axs
        def titles(fig, title, sub):
            fig.text(0.024, 0.985, f"{name} {tag} {title}", color=INK, fontproperties=HS.font(800, 20), va="top")
            fig.text(0.024, 0.958, sub, color=HS.ACCENT, fontproperties=HS.font(600, 12), va="top")
            fig.text(0.015, 0.006, CREDIT[src], color=MUTED, fontproperties=HS.font(500, 9.5)); fig.subplots_adjust(left=0.07, right=0.98, top=0.94, bottom=0.04, hspace=0.12)
        if f"{src}_surface_summary" in prods:
            fig, axs = panels(4)
            axs[0].plot(T, t2, color=WARM, lw=2.5, label="Temp"); axs[0].plot(T, td, color=RAIN, lw=2, label="Dew point"); axs[0].axhline(32, color=COLD, ls="--", lw=1.3); axs[0].set_ylabel("\u00b0F", color=INK)
            axs[1].plot(T, g("gust") * MPH, color=WARM, lw=2, label="Gust"); axs[1].plot(T, np.hypot(g("u"), g("v")) * MPH, color=INK, lw=1.6, label="Sustained"); axs[1].set_ylabel("mph", color=INK)
            axs[2].bar(T, Pinc, width=every / 24 * 0.85, color=RAIN, label=f"{every}-hour precip"); axs[2].plot(T, A, color=MEAN, lw=2, label=f"Total {A[-1]:.2f} in"); axs[2].set_ylabel("in", color=INK); axs[2].set_ylim(0, max(0.05, A[-1] * 1.15))
            axs[3].fill_between(T, g("tcc"), color=MUTED, alpha=0.6, label="Cloud cover"); axs[3].set_ylim(0, 100); axs[3].set_ylabel("%", color=INK)
            for ax in axs: legend(ax)
            titles(fig, "Surface Summary", run); out(f"{src}_surface_summary", fig)
        if f"{src}_winter_summary" in prods:
            fig, axs = panels(3, 11)
            axs[0].plot(T, t2, color=WARM, lw=2.5, label="Temp"); axs[0].plot(T, td, color=RAIN, lw=1.8, label="Dew point"); axs[0].axhline(32, color=COLD, ls="--", lw=1.3); axs[0].set_ylabel("\u00b0F", color=INK)
            typ = [(g("csnow"), SNOW, "Snow"), (g("cfrzr"), ICE, "Freezing rain"), (g("cicep"), PLUM, "Sleet"), (g("crain"), RAIN, "Rain")]
            bottom = np.zeros(len(T))
            for flag, col, lab in typ:
                part = Pinc * (np.nan_to_num(flag) > 0.5) * (bottom == 0); axs[1].bar(T, part, bottom=bottom, width=every / 24 * 0.85, color=col, label=lab); bottom = bottom + part
            other = np.where(bottom == 0, Pinc, 0); axs[1].bar(T, other, width=every / 24 * 0.85, color=MUTED, label="Type not set")
            axs[1].set_ylabel(f"in per {every} h", color=INK)
            axs[2].plot(T, SN, color=SNOW, lw=2.5, label=f"Model snowfall {SN[-1]:.1f} in"); axs[2].plot(T, A * 10, color=MUTED, lw=1.4, ls="--", label="10:1 of all precip")
            axs[2].set_ylabel("snow (in)", color=INK); axs[2].set_ylim(bottom=0)
            for ax in axs: legend(ax, "upper left")
            titles(fig, "Winter Weather Summary", run + "  \u00b7  precip bars colored by the model's precip type at each hour"); out(f"{src}_winter_summary", fig)
        if src == "rrfs" and "rrfs_smoke_sfc" in prods:
            fig, axs = panels(2, 9)
            axs[0].fill_between(T, g("smoke8") * 1e9, color="#a87b3d", alpha=0.8, label="Smoke at 8 m"); axs[0].set_ylabel("\u00b5g/m\u00b3", color=INK); axs[0].set_ylim(0, max(15.0, float(np.nanmax(g("smoke8") * 1e9)) * 1.15))
            for y, lab in ((12, "moderate"), (35, "unhealthy for sensitive groups"), (55, "unhealthy")): axs[0].axhline(y, color=GRID, lw=1, ls=":"); axs[0].text(T[0], y, f" {lab}", color=MUTED, fontsize=8, va="bottom")
            axs[1].fill_between(T, g("colmd") * 1e6, color="#7d4626", alpha=0.8, label="Smoke in the whole column"); axs[1].set_ylabel("mg/m\u00b2", color=INK); axs[1].set_ylim(bottom=0)
            for ax in axs: legend(ax, "upper left")
            titles(fig, "Near-Surface Smoke", run + "  \u00b7  lines are a rough guide to the 24 h PM2.5 categories"); out("rrfs_smoke_sfc", fig)
        # multi-run
        for kind, title, unit in (("t2m", "2 m Temperature", "\u00b0F"), ("qpf6", "6-Hour Precipitation", "in"), ("snow6", "6-Hour Snow", "in"),
                                  ("qpf", "Total Precipitation", "in"), ("snow", "Total Snow", "in")):
            pid = f"{src}_multirun_{kind}"
            if pid not in prods: continue
            fig, ax = frame(f"{name} {tag} Multi-run: {title}", f"Last {1 + len(past)} long {tag} runs, newest bold", src, unit, hourly=True)
            shades = ["#b5b7bb", "#8c8f95", "#6c6f75"]
            for k, (cc, Q) in enumerate([(c, P)] + past):
                ff = [f for f in range(0, hours + 1, every if k == 0 else max(every, 3)) if Q.get("t2", f, town) is not None]
                if not ff: continue
                gg = lambda key: np.array([np.nan if Q.get(key, f, town) is None else Q.get(key, f, town) for f in ff])
                tt = [cc + dt.timedelta(hours=f) for f in ff]
                if kind == "t2m": y = (gg("t2") - 273.15) * 1.8 + 32
                else:
                    tot = np.fmax.accumulate(np.nan_to_num(gg("apcp" if "qpf" in kind else "asnow")) * (1 / 25.4 if "qpf" in kind else 39.3701)); tot[0] = 0
                    y = tot if kind in ("qpf", "snow") else np.array([tot[i] - tot[ff.index(f - 6)] if f - 6 in ff else np.nan for i, f in enumerate(ff)])
                ax.plot(tt, y, lw=3 if k == 0 else 1.5, color=WARM if k == 0 else shades[min(k - 1, 2)], label=f"{cc:%HZ %-m/%-d}")
            if kind == "t2m": ax.axhline(32, color=COLD, ls="--", lw=1.3)
            else: ax.set_ylim(bottom=0)
            legend(ax, "upper left"); out(pid, fig)
        # time-height sections at the town
        if want_x:
            TX = [c + dt.timedelta(hours=f) for f in fx]
            ps = np.nan_to_num(np.array([P.get("psfc", f, town) or np.nan for f in fx]) / 100.0, nan=1013.0)
            def prof(v): return np.array([[np.nan if P.get(f"{v}:{L}", f, town) is None else P.get(f"{v}:{L}", f, town) for L in levs] for f in fx])
            TT = prof("TMP") - 273.15; RH = prof("RH"); under = np.array(levs)[None, :] > ps[:, None]
            TT[under] = np.nan; RH[under] = np.nan
            def tsec(pid, title, Z, levels, cmap, top, label, zero=None, extra_line=None, note=""):
                if pid not in prods: return
                fig, ax = frame(f"{name} {tag} {title}", run.split(", every")[0] + f", every {max(every, 3)} h" + note, src, "pressure (mb)", hourly=True)
                keep = np.array(levs) >= top; f_ = xsec(ax, TX, np.array(levs)[keep], Z[:, keep], levels, cmap)
                if zero is not None:
                    TTn, YY = np.meshgrid(mdates.date2num(TX), np.array(levs)[keep], indexing="ij")
                    k_ = ax.contour(TTn, YY, zero[:, keep], levels=[0], colors=["#0b1a3a"], linewidths=2.6)
                    k_.set(path_effects=HS.halo("white", 4.5))
                    if extra_line is not None: ax.contour(TTn, YY, extra_line[:, keep], levels=[0], colors=[MEAN], linewidths=1.6, linestyles="dashed")
                ax.set_yscale("log"); ax.set_ylim(min(1000, max(levs)), top); ax.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
                ax.set_yticks([L for L in (1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100) if L >= top]); ax.grid(color=GRID, lw=0.6)
                cb = fig.colorbar(f_, ax=ax, pad=0.01); cb.set_label(label, color=INK); cb.ax.tick_params(colors=INK)
                out(pid, fig)
            tcm = HS.temp_cmap(); tl = np.arange(-60, 31, 2)
            # full column: the house temperature palette stretched over -60..30 C so the cold upper levels keep their detail
            tcol = ListedColormap([HS.temp_color(-40 + (x + 60) / 90 * 150) for x in (tl[:-1] + tl[1:]) / 2])
            tsec(f"{src}_temp_xsec", "Temperature, Time-Height", TT, tl, tcol, 100, "\u00b0C", zero=TT, note="  \u00b7  dark line = 0\u00b0C, empty = below ground")
            tsec(f"{src}_temp_xsec_low", "Low-Level Temperature, Time-Height", TT, np.arange(-20, 21, 1),
                 ListedColormap([HS.temp_color(x * 1.8 + 32) for x in np.arange(-19.5, 20, 1)]), 700, "\u00b0C", zero=TT, note="  \u00b7  1000-700 mb, dark line = 0\u00b0C")
            tsec(f"{src}_rh_xsec", "Relative Humidity, Time-Height", RH, RH_LEVELS, ListedColormap(RH_COLS), 100, "%", note="  \u00b7  green = moist, brown = dry")
            TW = wetbulb(TT, RH)
            tsec(f"{src}_winter_thermal", "Winter Thermal Environment", TW, np.arange(-20, 21, 1),
                 ListedColormap([HS.temp_color(x * 1.8 + 32) for x in np.arange(-19.5, 20, 1)]), 600, "wet-bulb \u00b0C", zero=TW, extra_line=TT,
                 note="  \u00b7  fill = wet-bulb temp, dark line = 0\u00b0C wet bulb, white dashed = 0\u00b0C air temp")
        if want_smoke and any(p in prods for p in ("hrrr_smoke_xsec", "hrrr_smoke_xsec_low")):
            TX = [c + dt.timedelta(hours=f) for f in fx]; hs = P.get("hsfc", 0, town) or 0
            z = np.array([(P.get(f"hgt:{k}", 0, town) or np.nan) - hs for k in NAT_LEVELS]) / 1000.0
            SM = np.array([[np.nan if P.get(f"smoke:{k}", f, town) is None else P.get(f"smoke:{k}", f, town) * 1e9 for k in NAT_LEVELS] for f in fx])
            cm = ListedColormap(SMOKE_COLS); cm.set_under((0, 0, 0, 0))
            for pid, top, title in (("hrrr_smoke_xsec_low", 3.0, "Low-Level Smoke, Time-Height"), ("hrrr_smoke_xsec", 10.0, "Smoke, Time-Height")):
                if pid not in prods: continue
                fig, ax = frame(f"{name} HRRR {title}", run.split(", every")[0] + f", every {max(every, 3)} h  \u00b7  height above ground, km", src, "km above ground", hourly=True)
                ok = z <= top + 0.5
                if ok.sum() < 2: print(f"{town} {pid}: no level heights, skipped", flush=True); continue
                f_ = xsec(ax, TX, z[ok], SM[:, ok], SMOKE_LEVELS, cm, BoundaryNorm(SMOKE_LEVELS, cm.N)); ax.set_ylim(0, top)
                cb = fig.colorbar(f_, ax=ax, pad=0.01); cb.set_label("smoke \u00b5g/m\u00b3", color=INK); cb.ax.tick_params(colors=INK)
                out(pid, fig)
    return made


# ================================================================================================= main
EPS_ALL = ["eps_daily_hilo", "eps_qpf_plume", "eps_snow_plume", "eps_spread_maxmin", "eps_tmax_members", "eps_tmin_members", "eps_t2m_members",
           "eps_qpf24_members", "eps_qpf_members", "eps_snow24_members", "eps_snow_members", "eps_tcc_members", "eps_gust_members",
           "eps_mucape_members", "eps_pwat_members", "eps_mr_t2m", "eps_mr_tmax6", "eps_mr_tmin6", "eps_mr_qpf6", "eps_mr_snow6",
           "eps_mr_qpf24", "eps_mr_snow24", "eps_mr_qpf", "eps_mr_snow", "eps_spread_qpf", "eps_z500_t850"]
HIRES_ALL = {"hrrr": ["hrrr_surface_summary", "hrrr_smoke_xsec_low", "hrrr_multirun_t2m", "hrrr_multirun_qpf6", "hrrr_multirun_snow6",
                      "hrrr_multirun_qpf", "hrrr_multirun_snow", "hrrr_smoke_xsec", "hrrr_winter_summary", "hrrr_winter_thermal",
                      "hrrr_temp_xsec", "hrrr_temp_xsec_low", "hrrr_rh_xsec"],
             "rrfs": ["rrfs_surface_summary", "rrfs_multirun_t2m", "rrfs_multirun_qpf6", "rrfs_multirun_snow6", "rrfs_multirun_qpf",
                      "rrfs_multirun_snow", "rrfs_smoke_sfc", "rrfs_winter_summary", "rrfs_winter_thermal", "rrfs_temp_xsec",
                      "rrfs_temp_xsec_low", "rrfs_rh_xsec"]}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("source", choices=["eps", "hrrr", "rrfs"]); ap.add_argument("--cycle")
    ap.add_argument("--hours", type=int); ap.add_argument("--every", type=int); ap.add_argument("--products"); ap.add_argument("--towns")
    ap.add_argument("--runs", type=int, default=4)
    a = ap.parse_args(); src = a.source
    towns = a.towns.split(",") if a.towns else list(TOWNS)
    if src == "eps":
        c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else MG.latest_eps_cycle()
        prods = a.products.split(",") if a.products else EPS_ALL
        made = eps_charts(c, towns, prods, a.hours or 240, a.every or 3, a.runs)
    else:
        hours = a.hours or (48 if src == "hrrr" else 60)
        c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else latest_long(src, hours)
        prods = a.products.split(",") if a.products else HIRES_ALL[src]
        made = hires_charts(src, c, towns, prods, hours, a.every or 1, a.runs)
    mf = f"{OUT}/made.json"; m = json.load(open(mf)) if os.path.exists(mf) else {}
    for town, d in made.items():
        for pid, p in d.items():
            m.setdefault(src, {}).setdefault(town, {})[pid] = {"src": os.path.relpath(p, os.path.dirname(OUT)), "run": f"{c:%Y%m%d%H}",
                                                               "made": dt.datetime.now(PT).isoformat(timespec="minutes")}
    json.dump(m, open(mf, "w"), indent=1)
    print(f"{src}: {sum(len(d) for d in made.values())} charts for {len(made)} towns")
    sys.stdout.flush(); os._exit(0)
