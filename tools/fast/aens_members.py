#!/usr/bin/env python3
"""11-03 (Benjamin t2147u / t2148u / t2153u / t2156u): AIFS ENS single members for the fast site ("AIFS ENS members" under Runs).
One small file per member per hour: runs/aensm/<cycle>/m<NN>/mem_f<FFF>.webp (lossless WebP, 0.5 deg = every 2nd point of the AIFS ENS
0.25 deg crop; R = MSLP, G = 500 mb height, 8 bit on fixed ranges), so the site loads only the member that is asked for. Downloads only
the MSLP and 500 mb height GRIB messages (HTTP byte ranges from the ECMWF index). Static layers / keys / climatology are the AIFS ones.
  aens_members.py --cycle 2026110300 --out <data dir> [--workers 3]"""
import os, sys, json, time, argparse, datetime as dt, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "forecast"))
import fast_encode as FE
STEPS = list(range(6, 121, 6)) + list(range(132, 361, 12))   # 6-hourly to F+120, then 12-hourly to F+360 (40 steps)
RNG = {"mslp": [920.0, 1070.0], "z500": [4600.0, 6000.0]}     # fixed: ~0.6 mb and ~5.5 m steps (the viewer smooths before contouring)
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
    xs = [x for x in idx if x.get("type") == "pf" and (x["param"] == "msl" or (x["param"] == "z" and x.get("levelist") == "500"))]
    def fetch(x): return x, TM.get(base + ".grib2", (x["_offset"], x["_offset"] + x["_length"] - 1))
    i0, i1, j0, j1 = crop; M = {}; nb = 0
    with ThreadPoolExecutor(8) as ex:
        for x, blob in ex.map(fetch, xs):
            nb += len(blob); g = ec.codes_new_from_message(blob)
            ni, nj, lo0, d = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "iDirectionIncrementInDegrees")
            v = ec.codes_get_values(g).reshape(nj, ni); ec.codes_release(g)
            lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; v = FE.roll_ll(v[:, np.argsort(lon)])[i0:i1:2, j0:j1:2]   # same crop as EpsReader, every 2nd point
            M.setdefault(int(x["number"]), {})["mslp" if x["param"] == "msl" else "z500"] = v / 100.0 if x["param"] == "msl" else v / 9.80665
    mem = sorted(k for k, v in M.items() if len(v) == 2)
    if len(mem) < 40: return s, None, f"only {len(mem)} members"
    q = lambda a, lo, hi: np.clip(np.round((a - lo) / (hi - lo) * 255), 0, 255).astype(np.uint8)
    size = 0
    for n in mem:
        a = M[n]; rgb = np.stack([q(a["mslp"], *RNG["mslp"]), q(a["z500"], *RNG["z500"]), np.zeros(a["mslp"].shape, np.uint8)], -1)
        d_ = f"{out}/m{n:02d}"; os.makedirs(d_, exist_ok=True); p = f"{d_}/mem_f{s:03d}.webp"
        Image.fromarray(rgb, "RGB").save(p, "WEBP", lossless=True, quality=100, method=4, exact=True); size += os.path.getsize(p)
    return s, dict(members=mem, shape=list(rgb.shape[:2]), size=size, grib=nb, sec=round(time.time() - t, 1)), None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cycle", required=True); ap.add_argument("--out", required=True); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--man", required=True, help="manifest.json with models.aens (crop)"); ap.add_argument("--steps")
    ap.add_argument("--index-only", action="store_true", help="write run.json from the member files already made (no downloads)"); a = ap.parse_args()
    import temp_maps as TM; PT = TM.PT
    man = json.load(open(a.man)); crop = man["models"]["aens"]["crop"]; i0, i1, j0, j1 = crop
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc); rd = f"{a.out}/runs/aensm/{a.cycle}"; os.makedirs(rd, exist_ok=True)
    want = STEPS if not a.steps else [s for s in STEPS if int(a.steps.split("-")[0]) <= s <= int(a.steps.split("-")[1])]
    from concurrent.futures import ProcessPoolExecutor
    done, tot = {}, [0, 0]
    def have(s):   # a step already made (all files written): skip its download
        ms = [n for n in range(1, 51) if os.path.exists(f"{rd}/m{n:02d}/mem_f{s:03d}.webp")]
        return dict(members=ms, size=sum(os.path.getsize(f"{rd}/m{n:02d}/mem_f{s:03d}.webp") for n in ms), grib=0, sec=0) if len(ms) >= 50 else None
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
        v = c + dt.timedelta(hours=s); vl = v.astimezone(PT)
        steps.append(dict(f=s, valid=v.isoformat(), valid_line=f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT", badge=[f"F+{s}", f"{v:%HZ %a}".upper()],
                          ranges=dict(RNG), packs={"mslp": ["mem", 0], "z500": ["mem", 1]}))
    mems = sorted(set.intersection(*[set(d["members"]) for d in done.values()])) if done else []
    run = dict(model="aensm", cycle=a.cycle, init=c.isoformat(), base=f"runs/aensm/{a.cycle}", fields=["mslp", "z500"], grid=dict(ny=i1 - i0, nx=j1 - j0),
               half=[(i1 - i0 + 1) // 2, (j1 - j0 + 1) // 2], members=mems,
               runline=f"ECMWF AIFS ENS member {{mem}} 0.5\u00b0 {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}", steps=steps,
               complete=len(steps) == len(want), expected=len(want), file="m{mem}/{name}_f{f:03d}.webp")
    json.dump(run, open(f"{rd}/run.json", "w"), indent=1)
    print(f"aensm {a.cycle}: {len(steps)}/{len(want)} steps, {len(mems)} members, files {tot[0]/1e6:.1f} MB, grib {tot[1]/1e9:.2f} GB", flush=True)
if __name__ == "__main__": main()
