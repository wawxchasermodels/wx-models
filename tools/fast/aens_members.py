#!/usr/bin/env python3
"""11-03 (Benjamin t2147u / t2148u / t2153u / t2156u; t2221u parity with EPS members): AIFS ENS single members for the fast site ("AIFS ENS members" under Runs).
One small file per member per hour: runs/aensm/<cycle>/m<NN>/mx_f<FFF>.webp (lossless WebP, 0.5 deg = every 2nd point of the AIFS ENS
0.25 deg crop, 8 bit on fixed ranges), two tiles stacked (run.json tiles=2): tile 0 R = MSLP, G = 500 mb height, B = snowfall total
(10:1, sqrt-coded); tile 1 R = 10 m u wind, G = 10 m v wind (kt). The site loads only the member that is asked for. Downloads only msl,
z 500, sf, 10u, 10v (HTTP byte ranges from the ECMWF index). AIFS ENS has no gust field: the wind map is MSLP + 10 m wind (speed + barbs).
(Before 11-03 2:30 PM runs were one tile, R = MSLP, G = 500 mb, file mem_f<FFF>.webp; the viewer reads both, per run.json.)
  aens_members.py --cycle 2026110300 --out <data dir> [--workers 3]"""
import os, sys, json, time, argparse, datetime as dt, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "forecast"))
import fast_encode as FE
STEPS = list(range(6, 121, 6)) + list(range(132, 361, 12))   # 6-hourly to F+120, then 12-hourly to F+360 (40 steps)
RNG = {"mslp": [920.0, 1070.0], "z500": [4600.0, 6000.0], "asnow": [0.0, 200.0, 2], "u10": [-100.0, 100.0], "v10": [-100.0, 100.0]}   # ~0.6 mb, ~5.5 m, 0.8 kt; asnow sqrt-coded
TILES = 2; FILE = "mx"
def key(x):
    p = x["param"]
    if p == "msl": return "mslp"
    if p == "z" and x.get("levelist") == "500": return "z500"
    return {"sf": "asnow", "10u": "u10", "10v": "v10"}.get(p)
CONV = {"mslp": lambda v: v / 100.0, "z500": lambda v: v / 9.80665, "asnow": lambda v: np.maximum(v, 0) * 0.393701,   # sf: kg/m2 (mm water) run total -> in at 10:1
        "u10": lambda v: v * 1.94384, "v10": lambda v: v * 1.94384}
SRC = ["https://data.ecmwf.int/forecasts/{d}/{h:02d}z/aifs-ens/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-pf",
       "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/{d}/{h:02d}z/aifs-ens/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-pf"]

def one(args):
    c, s, crop, out = args
    import temp_maps as TM, eccodes as ec
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    t = time.time(); idx = None
    for u in SRC:
        base = u.format(d=f"{c:%Y%m%d}", h=c.hour, s=s)
        try: idx = [json.loads(l) for l in TM.get(base + ".index").decode().splitlines()]; break
        except Exception as e: err = e
    if idx is None: return s, None, str(err)
    xs = [x for x in idx if x.get("type") == "pf" and key(x)]
    def fetch(x): return x, TM.get(base + ".grib2", (x["_offset"], x["_offset"] + x["_length"] - 1))
    i0, i1, j0, j1 = crop; M = {}; nb = 0
    with ThreadPoolExecutor(8) as ex:
        for x, blob in ex.map(fetch, xs):
            nb += len(blob); g = ec.codes_new_from_message(blob)
            ni, nj, lo0, d = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "iDirectionIncrementInDegrees")
            v = ec.codes_get_values(g).reshape(nj, ni); ec.codes_release(g)
            lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; v = FE.roll_ll(v[:, np.argsort(lon)])[i0:i1:2, j0:j1:2]   # same crop as EpsReader, every 2nd point
            k = key(x); M.setdefault(int(x["number"]), {})[k] = CONV[k](v)
    mem = sorted(k for k, v in M.items() if len(v) == len(RNG))
    if len(mem) < 40: return s, None, f"only {len(mem)} members"
    q = lambda a, lo, hi, *m: np.clip(np.round((np.sqrt(np.clip((a - lo) / (hi - lo), 0, 1)) if m and m[0] == 2 else (a - lo) / (hi - lo)) * 255), 0, 255).astype(np.uint8)
    size = 0
    for n in mem:
        a = M[n]; z = np.zeros(a["mslp"].shape, np.uint8)
        t0 = np.stack([q(a["mslp"], *RNG["mslp"]), q(a["z500"], *RNG["z500"]), q(a["asnow"], *RNG["asnow"])], -1)
        t1 = np.stack([q(a["u10"], *RNG["u10"]), q(a["v10"], *RNG["v10"]), z], -1)
        rgb = np.concatenate([t0, t1], 0)   # image row 0 = first (southern) grid row of tile 0
        d_ = f"{out}/m{n:02d}"; os.makedirs(d_, exist_ok=True); p = f"{d_}/{FILE}_f{s:03d}.webp"
        Image.fromarray(rgb, "RGB").save(p, "WEBP", lossless=True, quality=100, method=4, exact=True); size += os.path.getsize(p)
    return s, dict(members=mem, shape=list(t0.shape[:2]), size=size, grib=nb, sec=round(time.time() - t, 1)), None

def step_meta(c, s):
    import temp_maps as TM; PT = TM.PT; v = c + dt.timedelta(hours=s); vl = v.astimezone(PT)
    return dict(f=s, valid=v.isoformat(), valid_line=f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT", badge=[f"F+{s}", f"{v:%HZ %a}".upper()],
                ranges=dict(RNG), packs={"mslp": [FILE, 0, 0], "z500": [FILE, 1, 0], "asnow": [FILE, 2, 0], "u10": [FILE, 0, 1], "v10": [FILE, 1, 1]})

def run_json(c, steps_meta, mems, crop):
    import temp_maps as TM; PT = TM.PT; i0, i1, j0, j1 = crop
    return dict(model="aensm", cycle=f"{c:%Y%m%d%H}", init=c.isoformat(), base=f"runs/aensm/{c:%Y%m%d%H}", fields=list(RNG), grid=dict(ny=i1 - i0, nx=j1 - j0),
                half=[(i1 - i0 + 1) // 2, (j1 - j0 + 1) // 2], tiles=TILES, members=mems,
                runline=f"ECMWF AIFS ENS member {{mem}} 0.5\u00b0 {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}", steps=steps_meta,
                complete=len(steps_meta) == len(STEPS), expected=len(STEPS), file="m{mem}/{name}_f{f:03d}.webp")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cycle", required=True); ap.add_argument("--out", required=True); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--man", required=True, help="manifest.json with models.aens (crop)"); ap.add_argument("--steps")
    ap.add_argument("--index-only", action="store_true", help="write run.json from the member files already made (no downloads)"); a = ap.parse_args()
    man = json.load(open(a.man)); crop = man["models"]["aens"]["crop"]; i0, i1, j0, j1 = crop
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc); rd = f"{a.out}/runs/aensm/{a.cycle}"; os.makedirs(rd, exist_ok=True)
    want = STEPS if not a.steps else [s for s in STEPS if int(a.steps.split("-")[0]) <= s <= int(a.steps.split("-")[1])]
    from concurrent.futures import ProcessPoolExecutor
    done, tot = {}, [0, 0]
    def have(s):   # a step already made (all files written): skip its download
        ms = [n for n in range(1, 51) if os.path.exists(f"{rd}/m{n:02d}/{FILE}_f{s:03d}.webp")]
        return dict(members=ms, size=sum(os.path.getsize(f"{rd}/m{n:02d}/{FILE}_f{s:03d}.webp") for n in ms), grib=0, sec=0) if len(ms) >= 50 else None
    for s in list(want):
        h = have(s)
        if h: done[s] = h; tot[0] += h["size"]
    todo = [] if a.index_only else [s for s in want if s not in done]
    with ProcessPoolExecutor(a.workers) as ex:
        for s, info, err in ex.map(one, [(c, s, crop, rd) for s in todo]):
            if err: print(f"f{s:03d} {err}", flush=True); continue
            done[s] = info; tot[0] += info["size"]; tot[1] += info["grib"]
            print(f"f{s:03d} {len(info['members'])} members {info['size']/1e3:.0f} KB (grib {info['grib']/1e6:.1f} MB) {info['sec']} s", flush=True)
    steps = []
    for s in want:
        if s not in done: break
        steps.append(step_meta(c, s))
    mems = sorted(set.intersection(*[set(d["members"]) for d in done.values()])) if done else []
    run = run_json(c, steps, mems, crop); run["complete"] = len(steps) == len(want); run["expected"] = len(want)
    json.dump(run, open(f"{rd}/run.json", "w"), indent=1)
    print(f"aensm {a.cycle}: {len(steps)}/{len(want)} steps, {len(mems)} members, files {tot[0]/1e6:.1f} MB, grib {tot[1]/1e9:.2f} GB", flush=True)
if __name__ == "__main__": main(); sys.stdout.flush(); os._exit(0)
