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

  python tide_archive.py --out DIR --issue now            # live snapshot (kind=archive) for the current issue slot
  python tide_archive.py --out DIR --backfill 2026110602 2026111414   # hindcast slots in [a, b]
"""
import argparse, datetime as D, json, math, os, re, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?application=wx_models_tides&time_zone=gmt&units=english&format=json&datum=MLLW"
S3 = "https://noaa-gestofs-pds.s3.amazonaws.com/"
STATIONS = {"9441102": "WPTW1", "9440910": "TOKW1", "9442396": "LAPW1", "9443090": "NEAW1", "9444090": "PTAW1", "9444900": "PTWW1",
            "9449880": "FRDW1", "9449424": "CHYW1", "9447130": "EBSW1", "9446484": "TCNW1", "9439040": "ASTO3", "9440581": "CPTW1"}
ALG = "c1"   # = tide.js 20261114t2 (swl 3 h mean + bias fading 12 h, relax 24 h to the 30-day mean; persistence fallback)
# c2 = c1 + version D SST term (k * (newest 2d OISST anomaly - prior 5d), faded in 1-exp(-lead/12h)).
# The scheduled job MUST run sst_steric.py --out DIR before this script so v1/sst.json exists; otherwise snapshots stay c1.
# The live Conditional also uses AIFS ENS IB + optional wind; those are not yet in this archive snapshot (separate from c2).
ALG_C2 = "c2"
H6, HR, DAY = 6 * 60000, 3600000, 86400000
TAU_BIAS, TAU_RELAX, SLOW_DAYS, LEAD_H = 12 * HR, 24 * HR, 30, 72
ISSUE_HOURS = (2, 8, 14, 20)
CACHE = os.environ.get("TIDE_CACHE", "/tmp/tide_archive_cache")
FT_PER_HPA = 3.28084 / 100  # 1 cm per hPa in feet, same as tide.js ibFt


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


def load_sst(out):
    fn = os.path.join(out, "v1", "sst.json")
    try:
        return json.load(open(fn)) if os.path.exists(fn) else None
    except Exception:
        return None

def ib_ft(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(p):
        return None
    return (1013.25 - p) * FT_PER_HPA

def load_v1(out, name):
    fn = os.path.join(out, "v1", name)
    try:
        return json.load(open(fn)) if os.path.exists(fn) else None
    except Exception:
        return None

def parse_init_ms(raw):
    if not raw:
        return None
    raw = str(raw)
    try:
        if "T" in raw:
            s = (raw if len(raw) > 16 else raw + ":00").replace("Z", "")
            d = D.datetime.fromisoformat(s)
            if d.tzinfo is None:
                d = d.replace(tzinfo=D.timezone.utc)
            return int(d.timestamp() * 1000)
        if len(raw) >= 10:
            d = D.datetime.strptime(raw[:10], "%Y%m%d%H").replace(tzinfo=D.timezone.utc)
            return int(d.timestamp() * 1000)
    except ValueError:
        return None
    return None

def aifs_hourly(rec, sid):
    if not rec:
        return []
    init = parse_init_ms(rec.get("init") or rec.get("cycle"))
    steps = rec.get("steps") or {}
    if init is None or not steps:
        return []
    def val(h):
        row = steps.get(str(h)) or steps.get(h) or {}
        v = (row.get("msl_hpa") or {}).get(sid)
        return float(v) if v is not None else None
    hs = [h for h in sorted({int(k) for k in steps}) if val(h) is not None]
    if not hs:
        return []
    out, last = [], hs[-1]
    for h in range(hs[0], last + 1):
        t = init + h * HR
        if val(h) is not None:
            out.append((t, val(h))); continue
        a = max(x for x in hs if x <= h)
        nxt = [x for x in hs if x >= h]
        b = nxt[0] if nxt else a
        va, vb = val(a), val(b)
        out.append((t, va if b == a else va + (vb - va) * (h - a) / (b - a)))
    return out

def coops_metric_pressure(st, b, e):
    url = (API.replace("units=english", "units=metric")
           + f"&product=air_pressure&station={st}&begin_date={gmt(b)}&end_date={gmt(e)}&interval=h")
    try:
        j = json.loads(get(url))
    except Exception:
        return []
    out = []
    for p in j.get("data") or []:
        try:
            out.append((parse_t(p["t"]), float(p["v"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out

def p_at(obs_pts, fc_pts, t, now_t):
    if t <= now_t:
        v = interp(obs_pts, t)
        if v is not None:
            return v
    return interp(fc_pts, t)

def conditional_free(T, pred, obs, air, aifs_rec, sst_st, sid, now_t=None):
    """STOFS-free default residual, matching site/tide/tide.js (wind off).

    resid = IB(t) + W + offset5 + leftover * exp(-lead/12h).
    Forecast hours use AIFS ENS pressure when present; otherwise the issue-time
    observed pressure is held (same fallback as the page).
    """
    now_t = now_t if now_t is not None else T
    pmap = dict(pred)
    obs = [(t, v) for t, v in obs if t <= T]
    res = [(t, v - pmap[t]) for t, v in obs if t in pmap]
    t_obs = obs[-1][0] if obs else None
    r_now = None
    if t_obs is not None and T - t_obs < 6 * HR:
        recent = [r[1] for r in res if r[0] >= t_obs - HR]
        if recent:
            r_now = sum(recent) / len(recent)
    if r_now is None and res:
        r_now = res[-1][1]
    if r_now is None:
        return None
    t0c = t_obs if t_obs is not None else T
    W = 0.0
    if sst_st:
        if sst_st.get("W") is not None:
            try:
                W = float(sst_st["W"])
            except (TypeError, ValueError):
                W = 0.0
        elif sst_st.get("k_ft_per_c") is not None:
            ssta = sst_st.get("ssta30_c")
            if ssta is None:
                ssta = sst_st.get("ssta")
            if ssta is not None:
                W = float(sst_st["k_ft_per_c"]) * float(ssta)
    fc_pts = aifs_hourly(aifs_rec, sid)
    ib0 = ib_ft(p_at(air, fc_pts, t0c, now_t)) or 0.0
    # 5-day unexplained offset: mean(r_obs - IB - W) on hours with residual + pressure
    t5 = t0c - 5 * DAY
    acc, n = 0.0, 0
    t = t5
    rmap = dict(res)
    while t <= t0c:
        rr = interp(res, t)
        if rr is not None:
            ibh = ib_ft(p_at(air, fc_pts, t, now_t))
            if ibh is not None:
                acc += rr - ibh - W
                n += 1
        t += HR
    offset5 = (acc / n) if n else 0.0
    leftover = r_now - ib0 - W - offset5
    def resid(t):
        dt = t - t0c
        p = p_at(air, fc_pts, t, now_t)
        ib = ib_ft(p)
        if ib is None:
            ib = ib0
        return ib + W + offset5 + leftover * math.exp(-max(0.0, dt) / TAU_BIAS)
    rr = lambda x: None if x is None else round(x, 3)
    snap = {"t": T, "alg": ALG, "method": "stofs-free", "t0": t0c,
            "rNow": rr(r_now), "rSlow": rr(offset5), "bias": rr(leftover),
            "r": [round(resid(T + k * HR), 3) for k in range(LEAD_H + 1)],
            "offset5": rr(offset5), "W": rr(W)}
    if sst_st:
        snap["sst"] = {k: sst_st.get(k) for k in ("last_day", "ssta30_c", "ssta", "k_ft_per_c", "W", "source", "chosen_sat")}
    return snap


def conditional(T, pred, obs, sto, sst_st=None):
    """Port of tide.js load(): returns the snapshot dict for issue time T (ms) or None.
    If sst_st (one station from v1/sst.json) is provided, the version D adj is faded in (alg=c2)."""
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

    adj = float((sst_st or {}).get("adj_ft") or 0)
    def sst_in(dt):
        return adj * (1 - math.exp(-max(0.0, dt) / TAU_BIAS))

    def resid(t):
        dt = t - t0c
        if rs and rs_now is not None and t <= rs_end[0]:
            return interp(rs, t) + bias * math.exp(-dt / TAU_BIAS) + sst_in(dt)
        if rs and rs_now is not None:
            r_end = rs_end[1] + bias * math.exp(-(rs_end[0] - t0c) / TAU_BIAS) + sst_in(rs_end[0] - t0c)
            return base + (r_end - base) * math.exp(-(t - rs_end[0]) / TAU_RELAX)
        r0 = r_now if r_now is not None else base
        return base + (r0 - base) * math.exp(-dt / TAU_BIAS) + sst_in(dt)

    rr = lambda x: None if x is None else round(x, 3)
    snap = {"t": T, "alg": ALG_C2 if sst_st else ALG, "method": "stofs" if (rs and rs_now is not None) else "persist", "t0": t0c,
            "rNow": rr(r_now), "rSlow": rr(r_slow), "bias": rr(bias), "r": [round(resid(T + k * HR), 3) for k in range(LEAD_H + 1)]}
    if sst_st:
        snap["sst"] = {k: sst_st.get(k) for k in ("last_day", "ssta30_c", "d_c", "k_ft_per_c", "steric_ft", "adj_ft")}
    return snap


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
        slot = slot_floor(now); slots = [slot]
        # live only if we are within 3 h of the slot (Actions cron can lag ~1 h); otherwise it is a reconstruction
        kind = "archive" if now - slot.timestamp() * 1000 <= 3 * HR else "hindcast"
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
    sst = load_sst(a.out)
    aifs = load_v1(a.out, "aifs_ens_msl.json")
    if not sst:
        print("note: v1/sst.json missing — SST term W=0 (same fallback as the page)")
    if not aifs:
        print("note: v1/aifs_ens_msl.json missing — forecast pressure holds the issue-time observation (same fallback as the page)")

    def one(item):
        st, sid = item
        pred = coops("predictions", st, T0 - SLOW_DAYS * DAY - DAY, T1 + (LEAD_H + 3) * HR, "&interval=6")
        obs = coops("water_level", st, T0 - SLOW_DAYS * DAY - DAY, obs_end)
        air = coops_metric_pressure(st, T0 - 6 * DAY, obs_end)
        snaps = []
        for s in slots:
            T = int(s.timestamp() * 1000)
            c = cyc_of.get(s)
            snap = conditional_free(T, pred, obs, air, aifs, (sst and (sst.get("stations") or {}).get(st)), st, now)
            if snap:
                snap["kind"] = kind
                snap["cycle"] = f"{c:%Y%m%d%H}" if c else (aifs or {}).get("cycle")
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
    v1 = os.path.join(a.out, "v1")
    idx["sidecars"] = {fn: True for fn in ("sst.json", "aifs_ens_msl.json", "stofs_anom.json")
                       if os.path.exists(os.path.join(v1, fn))}
    os.makedirs(os.path.dirname(idx_fn), exist_ok=True)
    json.dump(idx, open(idx_fn + ".tmp", "w"), separators=(",", ":")); os.replace(idx_fn + ".tmp", idx_fn)
    print(json.dumps({"kind": kind, "slots": len(slots), "cycles": [f"{c:%Y%m%d%H}" for c in cycles], "stations": dict(done)}))


if __name__ == "__main__":
    main()
