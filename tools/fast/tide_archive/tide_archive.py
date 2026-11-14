#!/usr/bin/env python3
"""Tides viewer: Conditional Prediction archive (Benjamin t3012u, 2026-11-14).

Every 6 h (issue times 02/08/14/20 UTC, ~30-60 min after each STOFS-2D-Global cycle lands) this computes the Conditional
Prediction exactly the way site/tide/tide.js does and appends one snapshot per station to
  <out>/v1/<station>/<YYYY-MM>.json   {"station": id, "issues": [ {t, kind, alg, method, cycle, t0, rNow, rSlow, bias, r[]} ]}
where r[] is the forecast non-tidal residual (ft) at t, t+1h, ... t+72h. The viewer rebuilds the issued line as
official prediction (6-min) + residual, so peaks are exact.
kind = "archive" (computed live at issue time) or "hindcast" (reconstructed afterwards from the data that existed at the
issue time: observations <= t and the newest STOFS cycle that had been posted, cycle + 8 h <= t).
Storage: an orphan branch "tide-archive" of the public GitHub repo, read by the site via raw.githubusercontent.com (CORS *).
No keys: CO-OPS API + NOAA Open Data (noaa-gestofs-pds) are public.

  python tide_archive.py --out DIR --issue now            # live snapshot (kind=archive): current slot, or the current hour if >3 h late
  python tide_archive.py --out DIR --backfill 2026110602 2026111414   # hindcast slots in [a, b]
"""
import argparse, datetime as D, json, math, os, re, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?application=wx_models_tides&time_zone=gmt&units=english&format=json&datum=MLLW"
S3 = "https://noaa-gestofs-pds.s3.amazonaws.com/"
STATIONS = {"9441102": "WPTW1", "9440910": "TOKW1", "9442396": "LAPW1", "9443090": "NEAW1", "9444090": "PTAW1", "9444900": "PTWW1",
            "9449880": "FRDW1", "9449424": "CHYW1", "9447130": "EBSW1", "9446484": "TCNW1", "9439040": "ASTO3"}
ALG = "c1"   # = tide.js 20261114t2 (swl 3 h mean + bias fading 12 h, relax 24 h to the 30-day mean; persistence fallback)
H6, HR, DAY = 6 * 60000, 3600000, 86400000
TAU_BIAS, TAU_RELAX, SLOW_DAYS, LEAD_H = 12 * HR, 24 * HR, 30, 72
ISSUE_HOURS = (2, 8, 14, 20)
CACHE = os.environ.get("TIDE_CACHE", "/tmp/tide_archive_cache")


def get(u, tries=4):
    err = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "wx-models-tides"}), timeout=90).read()
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(2 + 3 * i)
    raise err


def gmt(ms):
    return D.datetime.fromtimestamp(ms / 1000, D.timezone.utc).strftime("%Y%m%d %H:%M")


def parse_t(s):
    return int(D.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=D.timezone.utc).timestamp() * 1000)


def coops(product, st, b, e, extra=""):
    out = {}
    t = b
    while t < e:
        u = f"{API}&product={product}&station={st}&begin_date={urllib.parse.quote(gmt(t))}&end_date={urllib.parse.quote(gmt(min(e, t + 30 * DAY)))}{extra}"
        j = json.loads(get(u))
        for p in (j.get("predictions") or j.get("data") or []):
            try:
                out[parse_t(p["t"])] = float(p["v"])
            except (ValueError, TypeError, KeyError):
                pass
        t += 30 * DAY
    return sorted(out.items())


def cycle_key(c):
    return f"stofs_2d_glo.{c:%Y%m%d}/stofs_2d_glo.t{c:%H}z.points.swl.shef"


def cycle_posted(c):
    x = get(f"{S3}?list-type=2&prefix={urllib.parse.quote(cycle_key(c))}").decode()
    return re.search(r"<KeyCount>[1-9]", x) is not None


def shef_text(c):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, f"{c:%Y%m%d%H}.swl.shef")
    if not os.path.exists(fn):
        data = get(S3 + cycle_key(c)); open(fn + ".tmp", "wb").write(data); os.replace(fn + ".tmp", fn)
    return open(fn).read()


def shef_series(txt, sid):   # same parser as tide.js stofsSeries
    L = txt.split("\n")
    for i, l in enumerate(L):
        if l.startswith(f".E {sid} "):
            m = re.search(r"(\d{8}) Z DH(\d{2})(\d{2}).*?DIN(\d+)/(.*)$", l)
            if not m:
                return None
            t0 = int(D.datetime.strptime(m.group(1) + m.group(2) + m.group(3), "%Y%m%d%H%M").replace(tzinfo=D.timezone.utc).timestamp() * 1000)
            step = int(m.group(4)) * 60000
            vals = [x.strip() for x in m.group(5).split("/") if x.strip()]
            j = i + 1
            while j < len(L) and re.match(r"^\.E\d+\s", L[j]):
                vals += [x.strip() for x in re.sub(r"^\.E\d+\s+", "", L[j]).split("/") if x.strip()]; j += 1
            pts = []
            for k, v in enumerate(vals):
                try:
                    x = float(v)
                except ValueError:
                    continue
                if math.isfinite(x) and x > -90:
                    pts.append((t0 + k * step, x))
            return (step, pts) if pts else None
    return None


def interp(pts, t):
    if not pts or t < pts[0][0] or t > pts[-1][0]:
        return None
    lo, hi = 0, len(pts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pts[mid][0] <= t: lo = mid
        else: hi = mid
    (ta, va), (tb, vb) = pts[lo], pts[hi]
    return va if tb == ta else va + (vb - va) * (t - ta) / (tb - ta)


def conditional(T, pred, obs, sto):
    """Port of tide.js load(): returns the snapshot dict for issue time T (ms) or None."""
    pmap = dict(pred)
    obs = [(t, v) for t, v in obs if t <= T]
    res = [(t, v - pmap[t]) for t, v in obs if t in pmap]
    t_obs = obs[-1][0] if obs else None
    mean = lambda a: (sum(x[1] for x in a) / len(a)) if a else None
    r_slow = mean([r for r in res if r[0] >= T - SLOW_DAYS * DAY])
    r_now = mean([r for r in res if r[0] >= t_obs - HR]) if (t_obs is not None and T - t_obs < 6 * HR) else None
    rs = None
    if sto:
        step, raw = sto
        n = max(1, round(1.5 * HR / step))
        rs = []
        for i in range(len(raw)):
            w = raw[max(0, i - n): min(len(raw) - 1, i + n) + 1]
            rs.append((raw[i][0], sum(x[1] for x in w) / len(w)))
    t0c = t_obs if (t_obs is not None and r_now is not None) else T
    rs_now = interp(rs, t0c) if rs else None
    bias = (r_now - rs_now) if (r_now is not None and rs_now is not None) else 0.0
    base = r_slow if r_slow is not None else 0.0
    rs_end = rs[-1] if rs else None
    if r_now is None and not rs:
        return None

    def resid(t):
        dt = t - t0c
        if rs and rs_now is not None and t <= rs_end[0]:
            return interp(rs, t) + bias * math.exp(-dt / TAU_BIAS)
        if rs and rs_now is not None:
            r_end = rs_end[1] + bias * math.exp(-(rs_end[0] - t0c) / TAU_BIAS)
            return base + (r_end - base) * math.exp(-(t - rs_end[0]) / TAU_RELAX)
        r0 = r_now if r_now is not None else base
        return base + (r0 - base) * math.exp(-dt / TAU_BIAS)

    rr = lambda x: None if x is None else round(x, 3)
    return {"t": T, "alg": ALG, "method": "stofs" if (rs and rs_now is not None) else "persist", "t0": t0c,
            "rNow": rr(r_now), "rSlow": rr(r_slow), "bias": rr(bias), "r": [round(resid(T + k * HR), 3) for k in range(LEAD_H + 1)]}


def write(out, st, snaps):
    by_month = {}
    for s in snaps:
        by_month.setdefault(D.datetime.fromtimestamp(s["t"] / 1000, D.timezone.utc).strftime("%Y-%m"), []).append(s)
    for mon, add in by_month.items():
        fn = os.path.join(out, "v1", st, f"{mon}.json")
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        cur = json.load(open(fn)) if os.path.exists(fn) else {"station": st, "issues": []}
        keep = {i["t"]: i for i in cur["issues"]}
        for s in add:
            old = keep.get(s["t"])
            if old and old.get("kind") == "archive" and s["kind"] == "hindcast":
                continue   # never overwrite a live snapshot with a reconstruction
            keep[s["t"]] = s
        cur["issues"] = [keep[k] for k in sorted(keep)]
        tmp = fn + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cur, f, separators=(",", ":"))
        os.replace(tmp, fn)


def slot_floor(ms):
    d = D.datetime.fromtimestamp(ms / 1000, D.timezone.utc).replace(minute=0, second=0, microsecond=0)
    while d.hour not in ISSUE_HOURS:
        d -= D.timedelta(hours=1)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--issue", help="'now' = live snapshot for the current issue slot")
    ap.add_argument("--backfill", nargs=2, metavar=("FROM", "TO"), help="YYYYMMDDHH YYYYMMDDHH (UTC), hindcast")
    a = ap.parse_args()
    now = int(time.time() * 1000)
    if a.issue == "now":
        # real-time snapshot: the current 6-hourly slot if we are within 3 h of it (Actions cron can lag ~1 h); a late run or a
        # manual workflow_dispatch issues at the current hour instead, so every snapshot from this mode is computed live
        slot = slot_floor(now)
        if now - slot.timestamp() * 1000 > 3 * HR:
            slot = D.datetime.fromtimestamp(now / 1000, D.timezone.utc).replace(minute=0, second=0, microsecond=0)
        slots = [slot]; kind = "archive"
    elif a.backfill:
        f, t = (D.datetime.strptime(x, "%Y%m%d%H").replace(tzinfo=D.timezone.utc) for x in a.backfill)
        slots = []; d = f
        while d <= t:
            if d.hour in ISSUE_HOURS: slots.append(d)
            d += D.timedelta(hours=1)
        kind = "hindcast"
    else:
        ap.error("--issue now or --backfill")
    # STOFS cycle per slot: the newest cycle posted by issue time (live: S3 listing; hindcast: cycle + 8 h <= slot)
    cyc_of = {}
    for s in slots:
        c = s.replace(hour=s.hour // 6 * 6)
        for k in range(8):
            cc = c - D.timedelta(hours=6 * k)
            if kind == "archive":
                if cycle_posted(cc): cyc_of[s] = cc; break
            elif cc + D.timedelta(hours=8) <= s and cycle_posted(cc):
                cyc_of[s] = cc; break
    cycles = sorted(set(cyc_of.values()))
    with ThreadPoolExecutor(4) as ex:
        texts = dict(zip(cycles, ex.map(shef_text, cycles)))
    T0 = int(slots[0].timestamp() * 1000); T1 = int(slots[-1].timestamp() * 1000)
    obs_end = min(now, T1) + H6

    def one(item):
        st, sid = item
        pred = coops("predictions", st, T0 - SLOW_DAYS * DAY - DAY, T1 + (LEAD_H + 3) * HR, "&interval=6")
        obs = coops("water_level", st, T0 - SLOW_DAYS * DAY - DAY, obs_end)
        snaps = []
        for s in slots:
            T = int(s.timestamp() * 1000)
            c = cyc_of.get(s)
            sto = shef_series(texts[c], sid) if c else None
            snap = conditional(T, pred, obs, sto)
            if snap:
                snap["kind"] = kind; snap["cycle"] = f"{c:%Y%m%d%H}" if (c and snap["method"] == "stofs") else None
                if kind == "archive": snap["made"] = now
                snaps.append(snap)
        write(a.out, st, snaps)
        return st, len(snaps)

    with ThreadPoolExecutor(4) as ex:
        done = list(ex.map(one, STATIONS.items()))
    idx_fn = os.path.join(a.out, "v1", "index.json")
    idx = json.load(open(idx_fn)) if os.path.exists(idx_fn) else {"alg": ALG, "issue_hours_utc": list(ISSUE_HOURS), "lead_h": LEAD_H}
    idx["updated"] = now
    # months present per station, so the viewer never requests a missing file (no 404s in the console)
    idx["months"] = {st: sorted(f[:-5] for f in os.listdir(os.path.join(a.out, "v1", st)) if re.match(r"^\d{4}-\d{2}\.json$", f))
                     for st in STATIONS if os.path.isdir(os.path.join(a.out, "v1", st))}
    if kind == "archive" and "first_archive" not in idx: idx["first_archive"] = int(slots[0].timestamp() * 1000)
    if kind == "hindcast": idx["hindcast_through"] = max(idx.get("hindcast_through", 0), T1)
    os.makedirs(os.path.dirname(idx_fn), exist_ok=True)
    json.dump(idx, open(idx_fn + ".tmp", "w"), separators=(",", ":")); os.replace(idx_fn + ".tmp", idx_fn)
    print(json.dumps({"kind": kind, "slots": len(slots), "cycles": [f"{c:%Y%m%d%H}" for c in cycles], "stations": dict(done)}))


if __name__ == "__main__":
    main()
