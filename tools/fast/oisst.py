#!/usr/bin/env python3
"""11-03 (Benjamin t2169u): NOAA OISST v2.1 daily SST anomaly for the fast site (model "oisst", Waves tab). NCEI files are public domain
(~1.5 MB each, only the newest N days are fetched). The 0.25 deg OISST grid (cell centres at .125) is regridded bilinearly (land-aware) to
the GFS 0.25 deg grid so the GFS crop / LUTs / layers fit. One run = the newest N daily analyses; step f = hours after the first day.
  oisst.py --out <data dir> [--days 14] [--end 20261101]"""
import os, sys, json, argparse, datetime as dt, urllib.request, io, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "forecast"))
import fast_encode as FE
URL = "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr/{d:%Y%m}/oisst-avhrr-v02r01.{d:%Y%m%d}{sfx}.nc"
RNG = [-8.1, 8.0]   # deg F; land / ice-free-missing -> q 0 (= -8.1, under the product's min_show -8.0: not drawn)

def fetch(d, cache):
    os.makedirs(cache, exist_ok=True)
    for sfx in ("", "_preliminary"):
        p = f"{cache}/oisst_{d:%Y%m%d}{sfx}.nc"
        if os.path.exists(p): return p, sfx
        try: b = urllib.request.urlopen(URL.format(d=d, sfx=sfx), timeout=60).read()
        except Exception: continue
        open(p, "wb").write(b); return p, sfx
    return None, None

def regrid(a):
    """OISST (720 x 1440, lat -89.875.., lon 0.125..) -> GFS grid (721 x 1440, lat 90..-90, lon 0..359.75), bilinear over the valid points."""
    lat_t = 90 - 0.25 * np.arange(721); lon_t = 0.25 * np.arange(1440)
    fi = np.clip((lat_t + 89.875) / 0.25, 0, 719); fj = (lon_t - 0.125) / 0.25
    i0 = np.clip(np.floor(fi).astype(int), 0, 718); ti = (fi - i0)[:, None]
    j0 = np.floor(fj).astype(int); tj = (fj - j0)[None, :]; j0m = j0 % 1440; j1m = (j0 + 1) % 1440
    v = np.isfinite(a); z = np.where(v, a, 0.0)
    num = 0; den = 0
    for di, dj, w in ((0, 0, (1 - ti) * (1 - tj)), (0, 1, (1 - ti) * tj), (1, 0, ti * (1 - tj)), (1, 1, ti * tj)):
        rows = (i0 + di)[:, None]; cols = (j1m if dj else j0m)[None, :]
        num = num + w * z[rows, cols]; den = den + w * v[rows, cols]
    out = np.where(den > 0.25, num / np.maximum(den, 1e-9), np.nan)   # more than a quarter of the weight on sea, else land
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--days", type=int, default=14); ap.add_argument("--end")
    ap.add_argument("--cache", default="/workspace/oisst_cache"); a = ap.parse_args()
    import h5py, temp_maps as TM; from PIL import Image
    PT = TM.PT
    man = json.load(open(f"{a.out}/manifest.json")); i0, i1, j0, j1 = man["models"]["oisst"]["crop"]
    end = dt.datetime.strptime(a.end, "%Y%m%d").date() if a.end else dt.datetime.utcnow().date()
    got = []   # newest a.days days that exist
    d = end
    while len(got) < a.days and (end - d).days < a.days + 6:
        p, sfx = fetch(d, a.cache)
        if p: got.append((d, p, sfx))
        d -= dt.timedelta(days=1)
    got.sort(); first = got[0][0]; c = dt.datetime(first.year, first.month, first.day, tzinfo=dt.timezone.utc)
    rd = f"{a.out}/runs/oisst/{c:%Y%m%d%H}"; os.makedirs(f"{rd}/single", exist_ok=True); steps = []
    for d, p, sfx in got:
        f_ = h5py.File(p); x = f_["anom"][0, 0].astype(float); x[x == -999] = np.nan; x *= 0.01 * 1.8   # deg C -> deg F
        g = regrid(x)[i0:i1, j0:j1]; g = np.where(np.isfinite(g), np.clip(g, -8.0, 8.0), RNG[0])
        s = int((dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc) - c).total_seconds() // 3600)
        Image.fromarray(FE.q8(g, *RNG), "L").save(f"{rd}/single/ssta_f{s:03d}.png", optimize=True)
        v = c + dt.timedelta(hours=s)
        steps.append(dict(f=s, valid=v.isoformat(), valid_line=f"Analysis {d:%a %-m-%-d}" + (" (preliminary)" if sfx else ""), badge=[f"{d:%b %-d}".upper(), "DAILY"],
                          ranges={"ssta": list(RNG)}))
        print(d, sfx or "final", f"{os.path.getsize(f'{rd}/single/ssta_f{s:03d}.png')/1e3:.0f} KB", flush=True)
    run = dict(model="oisst", cycle=f"{c:%Y%m%d%H}", init=c.isoformat(), base=f"runs/oisst/{c:%Y%m%d%H}", fields=["ssta"], grid=dict(ny=i1 - i0, nx=j1 - j0),
               runline=f"NOAA OISST v2.1 0.25\u00b0 daily analyses {got[0][0]:%-m-%-d} to {got[-1][0]:%-m-%-d}", steps=steps, complete=True, expected=len(steps),
               file="single/{name}_f{f:03d}.png")
    json.dump(run, open(f"{rd}/run.json", "w"), indent=1); print("run", run["base"], len(steps), "days")
if __name__ == "__main__": main()
