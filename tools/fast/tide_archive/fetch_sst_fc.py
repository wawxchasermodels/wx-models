#!/usr/bin/env python3
"""Forecast sea temperature anomaly sidecar for the tide page (v1/sst_fc.json on the tide-archive branch).

For each station in sst.json:  forecast anomaly(day N) = latest observed anomaly (sst.json, vs 1991-2020)
  + [model SST(day N) - model SST(init day)] - [climatology(day N) - climatology(init day)]
The model's own bias cancels (only its change is used) and our 1991-2020 baseline is kept. The seasonal
term uses the station's own 1991-2020 OISST climatology (clim_doy in sst.json) or, if it has none, the NOAA
Coral Reef Watch daily climatology at its CRW pixel (sst_fc_clim.json). Days before the model init day are 0
(persistence); after the last model day tide.js holds the last value.
The sidecar stores only the change (deg C) per day, so tide.js adds k x change to its own current W.
Sources (public, keyless):
  NOAA Global RTOFS  https://noaa-nws-rtofs-pds.s3.amazonaws.com/rtofs.YYYYMMDD/rtofs_glo_3dz_{n024,f024..f192}_6hrly_hvr_US_west.nc
                     (temperature at depth 0 m, 00 UTC each day; read with HTTP range requests)
  ECMWF ENS (open)   {host}/YYYYMMDD/00z/ifs/0p25/enfo/YYYYMMDD000000-{step}h-enfo-ef.grib2  param skt, 50 members,
                     steps 0-360 every 12 h; day N = 0.25*(24N-12h) + 0.5*(24N) + 0.25*(24N+12h) so 00z and 12z weigh equally
A station whose nearest model ocean point is too far (Puget Sound, inner SF Bay) gets no entry -> flat SST term.
"""
from __future__ import annotations
import argparse, datetime as D, io, json, os, sys, time, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "wx-models-tides"}
ECM_HOSTS = ["https://storage.googleapis.com/ecmwf-open-data", "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
             "https://data.ecmwf.int/forecasts"]   # ECMWF open-data mirrors (Google, AWS) first; data.ecmwf.int is slow
RTOFS = "https://noaa-nws-rtofs-pds.s3.amazonaws.com"
MODE = "ecmwf"   # 2026-11-16 backtest (21 runs Oct 4-Nov 13, WA/OR/CA): ECMWF beat flat by 34%, RTOFS and RTOFS+ECMWF did not
RTOFS_DAYS, ECM_DAYS = 8, 15
MAX_KM = {"rtofs": 30.0, "ecmwf": 40.0}

def log(*a): print("sst_fc:", *a, flush=True)

def get(url, rng=None, timeout=60, tries=2):
    h = dict(UA)
    if rng: h["Range"] = f"bytes={rng[0]}-{rng[1]}"
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(3 * (i + 1))
    raise last

class HTTPFile(io.RawIOBase):
    """Read-only HTTP range file for h5py (256 KB block cache)."""
    BS = 1 << 18
    def __init__(self, url):
        self.url, self.pos, self.cache = url, 0, {}
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=60) as r:
            self.size = int(r.headers["Content-Length"])
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off); return self.pos
    def _block(self, b):
        if b not in self.cache:
            s = b * self.BS; self.cache[b] = get(self.url, (s, min(self.size, s + self.BS) - 1))
        return self.cache[b]
    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0: return 0
        out, p = bytearray(), self.pos
        while len(out) < n:
            b = p // self.BS; blk = self._block(b); o = p - b * self.BS
            take = blk[o:o + n - len(out)]; out += take; p += len(take)
        buf[:n] = out; self.pos += n; return n

# ---------- RTOFS ----------
def rtofs_latest(now):
    for back in range(0, 4):
        d = (now - D.timedelta(days=back)).date()
        u = f"{RTOFS}/rtofs.{d:%Y%m%d}/rtofs_glo_3dz_f{24*RTOFS_DAYS:03d}_6hrly_hvr_US_west.nc"
        try:
            urllib.request.urlopen(urllib.request.Request(u, method="HEAD", headers=UA), timeout=30); return d
        except Exception:
            continue
    return None

def rtofs_series(init, pts):
    import h5py
    rows = {sid: p["j"] for sid, p in pts.items()}; cols = {sid: p["i"] for sid, p in pts.items()}
    j0, j1 = min(rows.values()), max(rows.values()) + 1; i0, i1 = min(cols.values()), max(cols.values()) + 1
    out = {sid: [] for sid in pts}
    for n in range(0, RTOFS_DAYS + 1):
        fn = "n024" if n == 0 else f"f{24*n:03d}"
        f = HTTPFile(f"{RTOFS}/rtofs.{init:%Y%m%d}/rtofs_glo_3dz_{fn}_6hrly_hvr_US_west.nc")
        with h5py.File(f, "r") as h:
            if n == 0:   # guard against a grid change: the stored points must still match
                la = h["Latitude"][j0:j1, i0:i1]
                for sid, p in pts.items():
                    if abs(float(la[p["j"]-j0, p["i"]-i0]) - p["lat"]) > 0.01:
                        raise RuntimeError(f"RTOFS grid moved at {sid}")
            T = h["temperature"][0, 0, j0:j1, i0:i1]
        for sid, p in pts.items():
            v = float(T[p["j"]-j0, p["i"]-i0])
            out[sid].append(v if -3 < v < 40 else None)
    return out

# ---------- ECMWF ENS skt ----------
def ecm_index(host, run, step):
    stem = f"{run:%Y%m%d}/00z/ifs/0p25/enfo/{run:%Y%m%d}000000-{step}h-enfo-ef"
    txt = get(f"{host}/{stem}.index", timeout=60, tries=2).decode()
    return stem, [json.loads(l) for l in txt.splitlines() if l.strip()]

def ecm_latest(now):
    for back in range(0, 4):
        run = (now - D.timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)
        for host in ECM_HOSTS:
            try:
                _, L = ecm_index(host, run, 360)
                if sum(1 for x in L if x["param"] == "skt") >= 40: return run, host
            except Exception:
                continue
    return None, None

def ecm_fields(host, run, step, params):
    last = None
    for h in [host] + [x for x in ECM_HOSTS if x != host]:
        try:
            return ecm_fields1(h, run, step, params)
        except Exception as e:
            last = e; log("ecmwf step", step, "host", h, "failed:", type(e).__name__, e)
    raise last

def ecm_fields1(host, run, step, params):
    import eccodes
    stem, L = ecm_index(host, run, step)
    L = sorted([x for x in L if x["param"] in params], key=lambda x: x["_offset"])
    groups = []
    for x in L:
        s, e = x["_offset"], x["_offset"] + x["_length"] - 1
        if groups and s <= groups[-1][1] + 1: groups[-1][1] = max(groups[-1][1], e); groups[-1][2].append(x)
        else: groups.append([s, e, [x]])
    out = []
    for s, e, xs in groups:
        buf = get(f"{host}/{stem}.grib2", (s, e), timeout=120)
        for x in xs:
            o = x["_offset"] - s; m = eccodes.codes_new_from_message(buf[o:o + x["_length"]])
            try:
                if eccodes.codes_get(m, "Ni") != 1440 or eccodes.codes_get(m, "Nj") != 721:
                    raise RuntimeError("unexpected ECMWF grid")
                out.append((x["param"], eccodes.codes_get_values(m)))
            finally:
                eccodes.codes_release(m)
    return out

def ecm_series(host, run, pts):
    steps = list(range(0, 24 * ECM_DAYS + 1, 12)); val = {}
    for st in steps:
        f = ecm_fields(host, run, st, ("skt",))
        if len(f) < 40: raise RuntimeError(f"ECMWF step {st}: only {len(f)} members")
        mean = np.mean([v for _, v in f], axis=0)
        val[st] = {sid: float(mean[p["k"]]) - 273.15 for sid, p in pts.items()}
    out = {sid: [] for sid in pts}
    for n in range(0, ECM_DAYS + 1):
        for sid in pts:
            a, b, c = (val.get(24*n-12) or {}).get(sid), val[24*n][sid], (val.get(24*n+12) or {}).get(sid)
            if a is not None and c is not None: v = 0.25*a + 0.5*b + 0.25*c
            elif a is not None or c is not None: v = 0.5*b + 0.5*(a if a is not None else c)
            else: v = b
            out[sid].append(v)
    return out

# ---------- assemble ----------
def clim_fn(row, crw):
    c = {int(k): float(v) for k, v in (row.get("clim_doy") or {}).items()} or {int(k): float(v) for k, v in (crw or {}).items()}
    if not c: return None
    return lambda d: c.get(min(d.timetuple().tm_yday, 365 if 366 not in c else 366))

def build(sst, points, crw_clim, now, mode=MODE, prev=None):
    runs, rt, ec = {}, {}, {}
    if mode in ("rtofs", "combo"):
        init = rtofs_latest(now)
        if init:
            pts = {s: p for s, p in points["rtofs"].items() if p["dist_km"] <= MAX_KM["rtofs"] and not p.get("skip")}
            rt = rtofs_series(init, pts); runs["rtofs"] = f"RTOFS {init:%Y-%m-%d} 00 UTC"; rt_init = init
            log("rtofs", init, len(rt), "stations")
    if mode in ("ecmwf", "combo"):
        run, host = ecm_latest(now)
        if run and prev and (prev.get("runs") or {}).get("ecmwf") == f"ECMWF ENS {run:%Y-%m-%d} 00 UTC" and prev.get("source") == mode \
                and set(prev.get("stations") or {}) >= {s for s in (sst.get("stations") or {}) if s in points["ecmwf"] and not points["ecmwf"][s].get("skip") and points["ecmwf"][s]["dist_km"] <= MAX_KM["ecmwf"]}:
            log("ecmwf run", run, "already in sst_fc.json; keep it")
            return prev
        if run:
            pts = {s: p for s, p in points["ecmwf"].items() if p["dist_km"] <= MAX_KM["ecmwf"] and not p.get("skip")}
            ec = ecm_series(host, run, pts); runs["ecmwf"] = f"ECMWF ENS {run:%Y-%m-%d} 00 UTC"; ec_init = run.date()
            log("ecmwf", run, host, len(ec), "stations")
    if not runs: raise RuntimeError("no model run available")
    out = {}
    for sid, row in (sst.get("stations") or {}).items():
        key = row.get("alias_of") or sid
        if key == "birchbay": key = "9449424"
        cf = clim_fn((sst["stations"].get(key) or row), crw_clim.get(key))
        if cf is None: continue
        series = []   # (date, model SST change since init, init date)
        if mode in ("rtofs", "combo") and key in rt and all(v is not None for v in rt[key]):
            for n in range(0, RTOFS_DAYS + 1): series.append((rt_init + D.timedelta(days=n), rt[key][n] - rt[key][0], rt_init))
        if mode in ("ecmwf", "combo") and key in ec:
            if series:   # combo: extend RTOFS day 8 with the ECMWF change after it
                d8 = series[-1][0]; n8 = (d8 - ec_init).days
                if 0 <= n8 < ECM_DAYS:
                    for n in range(n8 + 1, ECM_DAYS + 1):
                        series.append((ec_init + D.timedelta(days=n), (rt[key][-1] - rt[key][0]) + (ec[key][n] - ec[key][n8]), rt_init))
            else:
                for n in range(0, ECM_DAYS + 1): series.append((ec_init + D.timedelta(days=n), ec[key][n] - ec[key][0], ec_init))
        if not series: continue
        d = []
        for day, dm, init in series:
            c0, cn = cf(init), cf(day)
            if c0 is None or cn is None: break
            d.append([day.isoformat(), round(dm - (cn - c0), 3)])
        if len(d) >= 2: out[sid] = {"d": d, "init": series[0][2].isoformat()}
    label = {"rtofs": "NOAA RTOFS", "ecmwf": "ECMWF ensemble", "combo": "NOAA RTOFS and ECMWF ensemble"}[mode]
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": mode, "source_short": label, "runs": runs,
            "method": "change in anomaly vs the latest observed day: model SST change since its init day minus the 1991-2020 seasonal change; tide.js adds k x change after the newest observation and holds the last day",
            "stations": out}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="tide-archive checkout (writes v1/sst_fc.json)")
    ap.add_argument("--sst", default="", help="sst.json (default: OUT/v1/sst.json)")
    ap.add_argument("--mode", default=MODE)
    a = ap.parse_args()
    sst = json.load(open(a.sst or os.path.join(a.out, "v1", "sst.json")))
    points = json.load(open(os.path.join(HERE, "sst_fc_points.json")))
    crw = json.load(open(os.path.join(HERE, "sst_fc_clim.json")))["stations"]
    now = D.datetime.now(D.timezone.utc).replace(tzinfo=None)
    dest = os.path.join(a.out, "v1", "sst_fc.json")
    prev = json.load(open(dest)) if os.path.exists(dest) else None
    j = build(sst, points, crw, now, a.mode, prev)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"; json.dump(j, open(tmp, "w"), separators=(",", ":")); os.replace(tmp, dest)
    log("wrote", dest, len(j["stations"]), "stations", j["runs"])

if __name__ == "__main__":
    main()
