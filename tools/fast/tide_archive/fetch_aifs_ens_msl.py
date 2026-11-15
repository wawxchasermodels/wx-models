#!/usr/bin/env python3
"""Download ECMWF AIFS ENS open-data MSL, ensemble mean at tide-station nearest 0.25 deg points.

AIFS ENS open data publishes control (cf) and 50 perturbed (pf) members, not a pre-made
-ep / type=em file (checked 2026-11-14 18Z on AWS and data.ecmwf.int). The ensemble mean
is the mean of those 51 members. Byte-range only the msl messages. 6-hourly steps 0-360 h
(the AIFS ENS open-data horizon; 72 h was too short for a 9-day tide chart and snapped the Conditional line).

If a run or lead is missing, fall back to AIFS single (oper/fc) then IFS oper/fc, and record it.

Writes one JSON per cycle under --out (default /tmp/sst_work/aifs_ens_msl/<YYYYMMDDHH>.json).
Safe to re-run: completed cycles and steps are skipped.
"""
from __future__ import annotations
import argparse, json, os, sys, time, shutil, subprocess, tempfile, datetime as dt

STATIONS = {
    "9439040": ("Astoria, OR", 46.207306, -123.7683),
    "9440910": ("Toke Point, WA", 46.7075, -123.96694),
    "9441102": ("Westport, WA", 46.90431, -124.10508),
    "9442396": ("La Push, WA", 47.912838, -124.63574),
    "9443090": ("Neah Bay, WA", 48.370724, -124.601585),
    "9444090": ("Port Angeles, WA", 48.125, -123.44),
    "9444900": ("Port Townsend, WA", 48.11122, -122.759674),
    "9449880": ("Friday Harbor, WA", 48.545277, -123.0125),
    "9449424": ("Cherry Point, WA", 48.862717, -122.75858),
    "9447130": ("Seattle, WA", 47.60264, -122.3393),
    "9446484": ("Tacoma, WA", 47.2667, -122.4133),
}
HOSTS = [
    "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
    "https://data.ecmwf.int/forecasts",
]
STEPS = list(range(0, 361, 6))
MIN_MEM = 40

def log(msg):
    print(msg, flush=True)

def curl_get(url, dest=None, rng=None, timeout=120):
    cmd = ["curl", "-sS", "-L", "--retry", "5", "--retry-delay", "2", "--retry-all-errors",
           "--connect-timeout", "20", "--max-time", str(timeout), "-A", "wx-models-tides"]
    if rng:
        cmd += ["-H", f"Range: bytes={rng[0]}-{rng[1]}"]
    if dest:
        cmd += ["-o", dest, url]
        r = subprocess.run(cmd)
        if r.returncode != 0 or not os.path.exists(dest) or os.path.getsize(dest) == 0:
            raise RuntimeError(f"curl {r.returncode} {url}")
        return dest
    cmd += [url]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(f"curl {r.returncode} {url}: {r.stderr[-200:]}")
    return r.stdout

def curl_head_meta(url):
    cmd = ["curl", "-sSI", "-L", "--retry", "3", "--retry-delay", "1", "--max-time", "30",
           "-A", "wx-models-tides", "-o", "/dev/null", "-w",
           "%{http_code}\n%{size_download}\n%{header_json}", url]
    # header_json may not exist on older curl; fallback
    r = subprocess.run(["curl", "-sSI", "-L", "--retry", "3", "--retry-delay", "1", "--max-time", "30",
                        "-A", "wx-models-tides", url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        return None
    code, last_mod, length = None, None, None
    for line in r.stdout.splitlines():
        if line.startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                code = int(parts[1])
        if line.lower().startswith("last-modified:"):
            last_mod = line.split(":", 1)[1].strip()
        if line.lower().startswith("content-length:"):
            try: length = int(line.split(":", 1)[1].strip())
            except ValueError: pass
    if code not in (200, 206):
        return None
    return {"status": code, "last_modified": last_mod, "length": length}

def load_index(url_base):
    last = None
    for host in HOSTS:
        # url_base starts with first host path suffix when rewritten
        if "://" in url_base:
            # replace host
            rest = url_base.split("/", 3)[3] if url_base.startswith("http") else url_base
            # actually url_base we pass as path after host: 20261114/18z/...
            url = f"{host}/{url_base}" if not url_base.startswith("http") else url_base
        else:
            url = f"{host}/{url_base}"
        try:
            raw = curl_get(url + ".index")
            rows = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
            return rows, url
        except Exception as e:
            last = e
    raise last

def nearest(lat, lon, ni, nj, la0, lo0, dx, dy):
    i = int(round((la0 - lat) / dy))
    i = max(0, min(nj - 1, i))
    lon360 = lon % 360
    j = int(round(((lon360 - lo0) % 360) / dx)) % ni
    glat = la0 - i * dy
    glon = ((lo0 + j * dx + 180) % 360) - 180
    return i, j, glat, glon

def decode_msl(blob, idxs):
    import eccodes as ec
    g = ec.codes_new_from_message(blob)
    try:
        ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
        la0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees")
        lo0 = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
        dx = ec.codes_get(g, "iDirectionIncrementInDegrees")
        dy = ec.codes_get(g, "jDirectionIncrementInDegrees")
        v = ec.codes_get_values(g)
        grid = (ni, nj, la0, lo0, dx, dy)
        out = {}
        # reshape row-major Nj x Ni
        arr = v.reshape(nj, ni)
        for sid, (i, j, glat, glon) in idxs.items():
            out[sid] = (float(arr[i, j]), glat, glon)
        return grid, out
    finally:
        ec.codes_release(g)

def build_idxs(grid):
    ni, nj, la0, lo0, dx, dy = grid
    return {sid: nearest(lat, lon, ni, nj, la0, lo0, dx, dy) for sid, (_, lat, lon) in STATIONS.items()}

def fetch_ranges(grib_url, messages, tmp, parallel=12):
    """Download listed index entries of one GRIB into tmp/{i}.bin; return list of paths in order."""
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for i, x in enumerate(messages):
        dest = os.path.join(tmp, f"{i:03d}.bin")
        paths.append((dest, x))
    def ok(dest, x):
        return os.path.exists(dest) and os.path.getsize(dest) == x["_length"]
    def one(dest, x):
        cmd = ["curl", "-sS", "-L", "--retry", "5", "--retry-delay", "2", "--retry-all-errors",
               "--connect-timeout", "20", "--max-time", "180", "-A", "wx-models-tides",
               "-H", f"Range: bytes={x['_offset']}-{x['_offset'] + x['_length'] - 1}",
               "-o", dest, grib_url]
        last = b""
        for attempt in range(3):
            r = subprocess.run(cmd, stderr=subprocess.PIPE)
            last = r.stderr or b""
            if r.returncode == 0 and ok(dest, x):
                return dest
        got = os.path.getsize(dest) if os.path.exists(dest) else 0
        raise RuntimeError(f"curl {dest} got {got} want {x['_length']} {last[-200:]!r}")
    # wave of `parallel` processes
    i = 0
    while i < len(paths):
        batch = paths[i:i + parallel]
        procs = []
        for dest, x in batch:
            cmd = ["curl", "-sS", "-L", "--retry", "5", "--retry-delay", "2", "--retry-all-errors",
                   "--connect-timeout", "20", "--max-time", "180", "-A", "wx-models-tides",
                   "-H", f"Range: bytes={x['_offset']}-{x['_offset'] + x['_length'] - 1}",
                   "-o", dest, grib_url]
            procs.append((dest, x, subprocess.Popen(cmd, stderr=subprocess.PIPE)))
        for dest, x, proc in procs:
            proc.communicate()
            if not ok(dest, x):
                # truncated or failed range: retry sequentially with a size check
                one(dest, x)
        i += parallel
    missing = [p for p, x in paths if not ok(p, x)]
    if missing:
        raise RuntimeError(f"missing {len(missing)} range files")
    return paths


def aifs_ens_path(c, s, kind):
    d, h = f"{c:%Y%m%d}", c.hour
    return f"{d}/{h:02d}z/aifs-ens/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-{kind}"

def aifs_single_path(c, s):
    d, h = f"{c:%Y%m%d}", c.hour
    return f"{d}/{h:02d}z/aifs-single/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc"

def ifs_oper_path(c, s):
    d, h = f"{c:%Y%m%d}", c.hour
    return f"{d}/{h:02d}z/ifs/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc"

def mean_from_members(paths):
    # first blob -> grid + idxs
    grid, first = decode_msl(open(paths[0][0], "rb").read(), None if False else {})
    # need idxs; decode again properly
    # get grid from first message then idxs
    import eccodes as ec
    g = ec.codes_new_from_message(open(paths[0][0], "rb").read())
    ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
    la0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees")
    lo0 = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
    dx = ec.codes_get(g, "iDirectionIncrementInDegrees")
    dy = ec.codes_get(g, "jDirectionIncrementInDegrees")
    ec.codes_release(g)
    grid = (int(ni), int(nj), float(la0), float(lo0), float(dx), float(dy))
    idxs = build_idxs(grid)
    acc = {sid: 0.0 for sid in STATIONS}
    n = 0
    glatlon = {sid: (idxs[sid][2], idxs[sid][3]) for sid in STATIONS}
    for dest, _ in paths:
        grid2, pts = decode_msl(open(dest, "rb").read(), idxs)
        n += 1
        for sid, (v, _, _) in pts.items():
            acc[sid] += v
    msl = {sid: acc[sid] / n / 100.0 for sid in STATIONS}  # Pa -> hPa
    return msl, glatlon, n, grid

def extract_single_file(path_base, tmp, idxs_hint=None):
    """AIFS single or IFS: one msl message."""
    rows, url = load_index(path_base)
    msl = [x for x in rows if x.get("param") == "msl"]
    if not msl:
        raise RuntimeError(f"no msl in {path_base}")
    paths = fetch_ranges(url + ".grib2", [msl[0]], tmp, parallel=1)
    # reuse mean_from_members for one member
    msl_h, glatlon, n, grid = mean_from_members(paths)
    return msl_h, glatlon, n, grid, url

def extract_ens_step(c, s, tmp):
    """Return dict for one step, with source tag."""
    note = None
    try:
        pf_rows, pf_url = load_index(aifs_ens_path(c, s, "pf"))
        cf_rows, cf_url = load_index(aifs_ens_path(c, s, "cf"))
        pf_m = [x for x in pf_rows if x.get("param") == "msl"]
        cf_m = [x for x in cf_rows if x.get("param") == "msl"]
        if len(pf_m) + len(cf_m) < MIN_MEM:
            raise RuntimeError(f"only {len(pf_m)+len(cf_m)} msl members")
        # same grib url per kind
        tdir = os.path.join(tmp, "ens")
        os.makedirs(tdir, exist_ok=True)
        paths = []
        if pf_m:
            paths += fetch_ranges(pf_url + ".grib2", pf_m, os.path.join(tmp, "pf"), parallel=12)
        if cf_m:
            paths += fetch_ranges(cf_url + ".grib2", cf_m, os.path.join(tmp, "cf"), parallel=2)
        msl, glatlon, n, grid = mean_from_members(paths)
        if n < MIN_MEM:
            raise RuntimeError(f"decoded {n} members")
        return {"source": "aifs-ens-mean", "n_members": n, "msl_hpa": msl,
                "grid": {sid: list(glatlon[sid]) for sid in STATIONS},
                "grid_spec": list(grid), "note": note}
    except Exception as e:
        note = f"aifs-ens failed ({type(e).__name__}: {e})"
    # fallback AIFS single
    try:
        msl, glatlon, n, grid, url = extract_single_file(aifs_single_path(c, s), os.path.join(tmp, "single"))
        return {"source": "aifs-single", "n_members": n, "msl_hpa": msl,
                "grid": {sid: list(glatlon[sid]) for sid in STATIONS},
                "grid_spec": list(grid), "note": note + "; fell back to AIFS single"}
    except Exception as e2:
        note = (note or "") + f"; aifs-single failed ({type(e2).__name__}: {e2})"
    # fallback IFS oper
    msl, glatlon, n, grid, url = extract_single_file(ifs_oper_path(c, s), os.path.join(tmp, "ifs"))
    return {"source": "ifs-oper", "n_members": n, "msl_hpa": msl,
            "grid": {sid: list(glatlon[sid]) for sid in STATIONS},
            "grid_spec": list(grid), "note": note + "; fell back to IFS oper"}

def cycle_meta(c):
    """HEAD the 0h cf grib on AWS (and portal) for last-modified / latency."""
    d, h = f"{c:%Y%m%d}", c.hour
    out = {"init": c.strftime("%Y-%m-%dT%H:%M:%SZ"), "cycle": c.strftime("%Y%m%d%H")}
    for name, host in (("aws", HOSTS[0]), ("ecmwf", HOSTS[1])):
        url = f"{host}/{d}/{h:02d}z/aifs-ens/0p25/enfo/{d}{h:02d}0000-0h-enfo-cf.grib2"
        meta = curl_head_meta(url)
        out[name] = {"url": url, **(meta or {"status": None})}
        if meta and meta.get("last_modified"):
            try:
                # e.g. Sat, 14 Nov 2026 23:46:01 GMT
                lm = dt.datetime.strptime(meta["last_modified"], "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
                out[name]["latency_min"] = int((lm - c).total_seconds() // 60)
            except Exception:
                # some curl TZ may be GMT
                try:
                    lm = dt.datetime.strptime(meta["last_modified"].replace(" GMT", ""), "%a, %d %b %Y %H:%M:%S").replace(tzinfo=dt.timezone.utc)
                    out[name]["latency_min"] = int((lm - c).total_seconds() // 60)
                except Exception:
                    pass
    return out

def do_cycle(c, outdir, steps):
    cid = c.strftime("%Y%m%d%H")
    dest = os.path.join(outdir, f"{cid}.json")
    data = {"cycle": cid, "init": c.strftime("%Y-%m-%dT%H:%M:%SZ"), "steps": {}, "meta": None}
    if os.path.exists(dest):
        try:
            data = json.load(open(dest))
        except Exception:
            data = {"cycle": cid, "init": c.strftime("%Y-%m-%dT%H:%M:%SZ"), "steps": {}, "meta": None}
    need = [s for s in steps if str(s) not in (data.get("steps") or {})]
    if not need and data.get("meta"):
        return dest, 0, "cached"
    t0 = time.time()
    if not data.get("meta"):
        try:
            data["meta"] = cycle_meta(c)
        except Exception as e:
            data["meta"] = {"error": str(e)}
    for s in need:
        tmp = tempfile.mkdtemp(prefix=f"aifs_{cid}_f{s:03d}_")
        try:
            data["steps"][str(s)] = extract_ens_step(c, s, tmp)
            json.dump(data, open(dest + ".tmp", "w"), separators=(",", ":"))
            os.replace(dest + ".tmp", dest)
            src = data["steps"][str(s)]["source"]
            log(f"  {cid} f{s:03d} {src} n={data['steps'][str(s)]['n_members']} {time.time()-t0:.1f}s")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return dest, len(need), f"{time.time()-t0:.1f}s"

def cycles_between(t0, t1):
    t = t0.replace(minute=0, second=0, microsecond=0)
    t = t - dt.timedelta(hours=t.hour % 6)
    out = []
    while t <= t1:
        out.append(t)
        t += dt.timedelta(hours=6)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/sst_work/aifs_ens_msl")
    ap.add_argument("--start", default="2026-10-01T00:00:00Z")
    ap.add_argument("--end", default="2026-11-14T18:00:00Z")
    ap.add_argument("--cycle", help="single cycle YYYYMMDDHH")
    ap.add_argument("--steps", default="0-360")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    a, b = args.steps.split("-")
    steps = [s for s in STEPS if int(a) <= s <= int(b)]
    if args.cycle:
        cs = [dt.datetime.strptime(args.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)]
    else:
        t0 = dt.datetime.strptime(args.start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        t1 = dt.datetime.strptime(args.end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        cs = cycles_between(t0, t1)
    log(f"AIFS ENS msl extract: {len(cs)} cycles, steps {steps}, out {args.out}")
    n_new = 0
    for c in cs:
        dest, n, msg = do_cycle(c, args.out, steps)
        n_new += n
        log(f"{c:%Y%m%d%H} {msg} -> {dest}")
    log(f"done, new steps {n_new}")

if __name__ == "__main__":
    try:
        main()
        sys.stdout.flush(); os._exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)
