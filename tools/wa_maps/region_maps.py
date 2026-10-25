#!/usr/bin/env python3
"""Shared layout helpers for the regional (1600x2400) and full-state forecast maps.
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from render_core import asset as _asset
""\

import math, os
import numpy as np
import town_pop as TP

GAZ = _asset("2023_Gaz_place_national.txt")

def set_nudges(region=None):
    TP.PREF = dict(TP.REGION_PREF.get(region, {}))
    if os.environ.get("RPREF"):
        import json; TP.PREF.update({k: tuple(v) for k, v in json.loads(os.environ["RPREF"]).items()})
    rr = [int(v) for v in os.environ.get("RRINGS", "10,18,26,34,44,54").split(",")]
    TP.NUDGE = [(0, 0)] + [(round(r * math.cos(a * math.pi / 6)), round(r * 0.8 * math.sin(a * math.pi / 6))) for r in rr for a in range(12)]

def towns(g, region):
    PASSES = g["PASSES"]; TOWNS, OPTIONAL, ORDER = g["TOWNS"], g["OPTIONAL"], g["ORDER"]
    bx = TP.REGION_LABEL[region]; inc = []
    for l in open(GAZ, encoding="latin-1"):
        c = l.rstrip("\n").split("\t")
        if c[0] != "WA" or not (c[3].endswith(" city") or c[3].endswith(" town")): continue
        nm = c[3].rsplit(" ", 1)[0]; lo, la = float(c[11]), float(c[10])
        if bx[0] <= lo <= bx[2] and bx[1] <= la <= bx[3]: inc.append(nm)
    drop = TP.REGION_DROP[region]
    rq = [t for t in TP.REGION_REQUESTED.get(region, []) if t not in drop]
    if rq: TP.REQUESTED = list(TP.REQUESTED) + [t for t in rq if t not in TP.REQUESTED]
    new = list(dict.fromkeys(t for t in inc + TP.REGION_TOWNS[region] + rq if t not in TOWNS and t not in drop))
    T = [t for t in TOWNS if t not in drop] + new
    O = (set(OPTIONAL) | set(new)) - set(TP.REQUESTED)
    popt = region in TP.REGION_PASSES_OPTIONAL
    if popt: O |= set(PASSES)
    req = [t for t in ORDER if t not in O and t not in drop and t not in rq]

    last = max([i for i, t in enumerate(req) if t in TP.REQUESTED or TP.always(t, t in PASSES)] or [len(req) - 1])
    req = req[:last + 1] + sorted(rq, key=lambda t: -TP.pop(t)) + req[last + 1:]
    opt = sorted([t for t in T if t in O and t not in PASSES], key=lambda t: -TP.pop(t))
    g.update(TOWNS=T, OPTIONAL=O, ORDER=req + opt + ([p for p in PASSES] if popt else []), PASS_OPT=popt)

def bar_bottom(P, lo0, lo1):
    return float(P(-120.0, BAR_LAT)[1])

def fill_mask(R, Image, WS, HS, wam, valid):
    lm = np.asarray(R.LAND_MASK.resize((WS, HS), Image.NEAREST)) > 127
    return wam | (lm & valid)

_GRID = {}
def _grid(R, step):
    k = (R, step)
    if k not in _GRID:
        g = np.arange(-R, R + 1, step, dtype=float); GX, GY = np.meshgrid(g, g); GX, GY = GX.ravel(), GY.ravel()
        dd = np.hypot(GX, GY); o = np.argsort(dd, kind="stable")
        _GRID[k] = (GX, GY, dd, o)
    return _GRID[k]

def _memo(inside):
    if getattr(inside, "_memo", False): return inside
    if not hasattr(inside, "_rm_cache"): inside._rm_cache = {}
    cache = inside._rm_cache
    def f(bb):
        k = bb if type(bb) is tuple else tuple(bb)
        r = cache.get(k)
        if r is None: r = cache[k] = bool(inside(bb))
        return r
    f._memo = True; f.vec = getattr(inside, "vec", None)
    return f

def _vin(inside, B):
    v = getattr(inside, "vec", None)
    if v is not None: return np.asarray(v(np.asarray(B, float)), bool)
    return np.array([inside(tuple(b)) for b in B], bool)

def relax(lay, real_px, keep, inside, step=2):
    ""\
\
\

    import numpy as np, math
    inside = _memo(inside)
    names = list(lay)
    for _pass in range(4):
        moved = 0
        for n in names:
            c = lay[n]; rx, ry = real_px[n]; tw, th = c["tw"], c["th"]
            bx0, by0, bx1, by1 = c["bb"]; px0, py0 = c["tx"] - bx0, c["ty"] - by0
            bw, bh = bx1 - bx0, by1 - by0
            ox, oy = c["tx"] + tw / 2 - rx, c["ty"] + th / 2 - ry; r0 = math.hypot(ox, oy)
            if r0 < 1.5: continue
            oth = np.array([lay[m]["bb"] for m in names if m != n] + [tuple(k) for k in keep], float)
            op = np.array([real_px[m] for m in names if m != n], float).reshape(-1, 2)
            R = int(r0) + 2
            GX, GY, dd, o_ = _grid(R, step); o_ = o_[dd[o_] < r0 - 1]
            if not len(o_): continue
            GX, GY = GX[o_], GY[o_]
            X0 = rx + GX - tw / 2 - px0; Y0 = ry + GY - th / 2 - py0; X1, Y1 = X0 + bw, Y0 + bh
            hit = ~((X1[:, None] < oth[None, :, 0]) | (X0[:, None] > oth[None, :, 2]) | (Y1[:, None] < oth[None, :, 1]) | (Y0[:, None] > oth[None, :, 3]))
            ok = ~hit.any(1)
            cov = lambda a, b, c_, d_: ((op[:, 0] >= a) & (op[:, 0] <= c_) & (op[:, 1] >= b) & (op[:, 1] <= d_)).sum()
            cov0 = cov(bx0, by0, bx1, by1)
            nz_ = np.nonzero(ok)[0]
            if getattr(inside, "vec", None) is not None and len(nz_):
                nz_ = nz_[_vin(inside, np.stack([X0[nz_], Y0[nz_], X1[nz_], Y1[nz_]], 1))]
            for i in nz_:
                bb = (X0[i], Y0[i], X1[i], Y1[i])
                if not inside(bb) or cov(*bb) > cov0: continue
                dx, dy = bb[0] - bx0, bb[1] - by0
                c["tx"] += dx; c["ty"] += dy; c["bb"] = bb; moved += 1; break
        if not moved: break
    for n in names:
        c = lay[n]; c["x"], c["y"] = real_px[n]
        c["off"] = (c["tx"] + c["tw"] / 2 - c["x"], c["ty"] + c["th"] / 2 - c["y"])

def relax_push(lay, real_px, keep, inside, step=3, rounds=3, maxd=None):
    ""\
\

    import numpy as np, math
    inside = _memo(inside)
    names = list(lay); idx = {n: i for i, n in enumerate(names)}
    KP = np.array([tuple(k) for k in keep], float).reshape(-1, 4)
    OP = np.array([real_px[n] for n in names], float)
    def geo(n):
        c = lay[n]; bx0, by0, bx1, by1 = c["bb"]
        return c["tx"] - bx0, c["ty"] - by0, bx1 - bx0, by1 - by0
    def cov(bb, me):
        m = (OP[:, 0] >= bb[0]) & (OP[:, 0] <= bb[2]) & (OP[:, 1] >= bb[1]) & (OP[:, 1] <= bb[3]); m[idx[me]] = False
        return int(m.sum())
    cov0 = {n: cov(lay[n]["bb"], n) for n in names}
    def d2(n, bb):
        x, y = real_px[n]; return ((bb[0] + bb[2]) / 2 - x) ** 2 + ((bb[1] + bb[3]) / 2 - y) ** 2
    def d2v(n, B):
        x, y = real_px[n]; return ((B[:, 0] + B[:, 2]) / 2 - x) ** 2 + ((B[:, 1] + B[:, 3]) / 2 - y) ** 2
    def _near(B, O):
        return ~((B[:, 2].max() < O[:, 0]) | (B[:, 0].min() > O[:, 2]) | (B[:, 3].max() < O[:, 1]) | (B[:, 1].min() > O[:, 3]))
    def cands(n, R):
        px0, py0, bw, bh = geo(n); c = lay[n]; rx, ry = real_px[n]
        GX, GY, _dd, o = _grid(R, step); GX, GY = GX[o], GY[o]
        X0 = rx + GX - c["tw"] / 2 - px0; Y0 = ry + GY - c["th"] / 2 - py0
        return np.stack([X0, Y0, X0 + bw, Y0 + bh], 1)
    def hits(B, ex):
        L = np.array([lay[m]["bb"] for m in names], float)
        h = np.zeros((len(B), len(L)), bool); nr = np.nonzero(_near(B, L))[0]; Ln = L[nr]
        h[:, nr] = ~((B[:, None, 2] < Ln[None, :, 0]) | (B[:, None, 0] > Ln[None, :, 2]) | (B[:, None, 3] < Ln[None, :, 1]) | (B[:, None, 1] > Ln[None, :, 3]))
        for e in ex: h[:, idx[e]] = False
        if not len(KP): return h, np.zeros(len(B), bool)
        Kn = KP[_near(B, KP)]
        k = ~((B[:, None, 2] < Kn[None, :, 0]) | (B[:, None, 0] > Kn[None, :, 2]) | (B[:, None, 3] < Kn[None, :, 1]) | (B[:, None, 1] > Kn[None, :, 3]))
        return h, k.any(1)
    def setbb(n, bb):
        c = lay[n]; dx, dy = bb[0] - c["bb"][0], bb[1] - c["bb"][1]; c["tx"] += dx; c["ty"] += dy; c["bb"] = tuple(float(v) for v in bb)
    for _ in range(rounds):
        moved = 0
        for a in sorted(names, key=lambda n: -d2(n, lay[n]["bb"])):
            da = d2(a, lay[a]["bb"]); ra = math.sqrt(da)
            if ra < 4: continue
            CA = cands(a, int(ra) + 2); CA = CA[d2v(a, CA) < da - 4]
            if not len(CA): continue
            hA, kA = hits(CA, [a])
            done = False
            ia_ = np.nonzero((hA.sum(1) == 1) & ~kA)[0][:400]
            if getattr(inside, "vec", None) is not None and len(ia_): ia_ = ia_[_vin(inside, CA[ia_])]
            for i in ia_:
                bbA = tuple(CA[i]);
                if not inside(bbA) or cov(bbA, a) > cov0[a]: continue
                b = names[int(np.nonzero(hA[i])[0][0])]
                budget = da + d2(b, lay[b]["bb"]) - d2(a, bbA)
                if budget <= 0: continue
                CB = cands(b, int(math.sqrt(budget)) + 2)
                CB = CB[d2v(b, CB) < budget - 4]
                if not len(CB): continue
                old = lay[a]["bb"]; setbb(a, bbA)
                hB, kB = hits(CB, [b])
                jb_ = np.nonzero(~hB.any(1) & ~kB)[0]
                if getattr(inside, "vec", None) is not None and len(jb_): jb_ = jb_[_vin(inside, CB[jb_])]
                for j in jb_:
                    bbB = tuple(CB[j])
                    if maxd is not None and d2(b, bbB) > max(maxd ** 2, d2(b, lay[b]["bb"]) if b != a else 0): continue
                    if inside(bbB) and cov(bbB, b) <= cov0[b]:
                        setbb(b, bbB); done = True; break
                if done: break
                setbb(a, old)
            if done: moved += 1
        relax(lay, real_px, keep, inside)
        if not moved: break
    for n in names:
        c = lay[n]; c["off"] = (c["tx"] + c["tw"] / 2 - c["x"], c["ty"] + c["th"] / 2 - c["y"])

def wa_allowed(R, P, W, H, wa, water_km=5.6):
    ""\
\

    import pickle, os, numpy as np
    from PIL import Image, ImageDraw
    from scipy.ndimage import distance_transform_edt
    def rast(geoms):
        m = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(m)
        for g in geoms:
            for pg in R.polys(g):
                dr.polygon([tuple(p) for p in P.ring(pg.exterior.coords)], fill=255)
                for hole in pg.interiors: dr.polygon([tuple(p) for p in P.ring(hole.coords)], fill=0)
        return np.asarray(m) > 127
    st = pickle.load(open(R.BM + "/cb_2023_us_state_500k.pkl", "rb"))
    oth = [g for p_, g in st if p_.get("STUSPS") in ("OR", "ID", "MT", "CA", "NV")]
    oth += [g for p_, g in pickle.load(open(R.BM + "/ne_10m_admin_0_countries.pkl", "rb")) if p_.get("NAME") == "Canada"]
    wam = rast([wa]); om = rast(oth) & ~wam
    a, b = P(-120.0, 47.0), P(-120.0, 47.5); kmpx = 55.6 / max(1e-6, abs(b[1] - a[1]))
    dwa = distance_transform_edt(~wam); dot = distance_transform_edt(~om)
    water = ~wam & ~om
    from shapely.geometry import Polygon
    ocean = rast([Polygon([(-131, 43), (-123.85, 43), (-123.85, 48.25), (-124.75, 48.45), (-124.75, 50), (-131, 50)])])

    if os.environ.get("WA_WATER_STRICT"): return wam | (water & (dwa < dot) & (~ocean | (dwa * kmpx <= water_km)))
    return ~om

def tight(lay, real_px, keep, inside, allowed, L, protected, prio, step=2, cov_pen=10.0, hard_max=400):
    ""\
\
\
\

    import numpy as np, math
    H_, W_ = allowed.shape
    bad = np.pad((~allowed).astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    def badcount(X0, Y0, X1, Y1):
        x0 = np.clip(np.floor(X0).astype(int), 0, W_); x1 = np.clip(np.ceil(X1).astype(int), 0, W_)
        y0 = np.clip(np.floor(Y0).astype(int), 0, H_); y1 = np.clip(np.ceil(Y1).astype(int), 0, H_)
        return bad[y1, x1] - bad[y0, x1] - bad[y1, x0] + bad[y0, x0]
    order = [n for n in prio if n in lay and n in protected] + [n for n in prio if n in lay and n not in protected]
    order += [n for n in lay if n not in order]
    KP = [tuple(k) for k in keep]; placed = {}; dropped = []; exc = {}
    for i, n in enumerate(order):
        c = lay[n]; rx, ry = real_px[n]; tw, th = c["tw"], c["th"]
        bx0, by0, bx1, by1 = c["bb"]; px0, py0 = c["tx"] - bx0, c["ty"] - by0; bw, bh = bx1 - bx0, by1 - by0
        later = np.array([real_px[m] for m in order[i + 1:]], float).reshape(-1, 2)
        got = None
        for R_ in ((L,) if n not in protected else (L, hard_max)):
            g = np.arange(-R_, R_ + 1, step, dtype=float); GX, GY = np.meshgrid(g, g); GX, GY = GX.ravel(), GY.ravel()
            dd = np.hypot(GX, GY); m_ = dd <= R_; GX, GY, dd = GX[m_], GY[m_], dd[m_]
            X0 = rx + GX - tw / 2 - px0; Y0 = ry + GY - th / 2 - py0; X1, Y1 = X0 + bw, Y0 + bh
            ok = (X0 >= 16) & (X1 <= W_ - 16) & (Y0 >= 16) & (Y1 <= H_ - 12) & (badcount(X0, Y0, X1, Y1) == 0)
            O = np.array(list(placed.values()) + KP, float).reshape(-1, 4)
            if len(O):
                ok &= ~(~((X1[:, None] < O[None, :, 0]) | (X0[:, None] > O[None, :, 2]) | (Y1[:, None] < O[None, :, 1]) | (Y0[:, None] > O[None, :, 3]))).any(1)
            if not ok.any(): continue
            cost = dd.copy()
            if len(later):
                cv = ((later[None, :, 0] >= X0[:, None]) & (later[None, :, 0] <= X1[:, None]) & (later[None, :, 1] >= Y0[:, None]) & (later[None, :, 1] <= Y1[:, None])).sum(1)
                cost = cost + cov_pen * cv
            cost[~ok] = np.inf; j = int(np.argmin(cost))
            if not inside((X0[j], Y0[j], X1[j], Y1[j])): continue
            got = (X0[j], Y0[j], X1[j], Y1[j]); break
        if got is None: dropped.append(n); continue
        c["tx"] += got[0] - bx0; c["ty"] += got[1] - by0; c["bb"] = tuple(float(v) for v in got); placed[n] = c["bb"]
        c["x"], c["y"] = rx, ry
        off = math.hypot(c["tx"] + tw / 2 - rx, c["ty"] + th / 2 - ry)
        if off > L + 0.5: exc[n] = round(off)
    for n in dropped: del lay[n]
    return dropped, exc

def tighten(lay, real_px, keep, inside, L, protected, popf, step=2, hard_max=300, first=()):
    ""\
\
\
\
\

    import numpy as np, math, os, sys
    inside = _memo(inside)
    def geo(n):
        c = lay[n]; b = c["bb"]; return c["tx"] - b[0], c["ty"] - b[1], b[2] - b[0], b[3] - b[1]
    def off(n):
        c = lay[n]; x, y = real_px[n]; return math.hypot((c["bb"][0] + c["bb"][2]) / 2 - x, (c["bb"][1] + c["bb"][3]) / 2 - y)
    def cands(n, R):
        px0, py0, bw, bh = geo(n); rx, ry = real_px[n]; c = lay[n]
        GX, GY, dd, o = _grid(R, step); o = o[dd[o] <= R]
        GX, GY, dd = GX[o], GY[o], dd[o]

        X0 = rx + GX - bw / 2; Y0 = ry + GY - bh / 2
        return np.stack([X0, Y0, X0 + bw, Y0 + bh], 1), dd
    def setbb(n, bb):
        c = lay[n]; c["tx"] += bb[0] - c["bb"][0]; c["ty"] += bb[1] - c["bb"][1]; c["bb"] = tuple(float(v) for v in bb)
    KP = np.array([tuple(k) for k in keep], float).reshape(-1, 4)
    def overl(B, names):
        Lb = np.array([lay[m]["bb"] for m in names], float).reshape(-1, 4)
        f = lambda O: ~((B[:, None, 2] < O[None, :, 0]) | (B[:, None, 0] > O[None, :, 2]) | (B[:, None, 3] < O[None, :, 1]) | (B[:, None, 1] > O[None, :, 3]))

        near = lambda O: ~((B[:, 2].max() < O[:, 0]) | (B[:, 0].min() > O[:, 2]) | (B[:, 3].max() < O[:, 1]) | (B[:, 1].min() > O[:, 3]))
        hl = np.zeros((len(B), len(Lb)), bool)
        if len(B) and len(Lb):
            nr = np.nonzero(near(Lb))[0]; hl[:, nr] = f(Lb[nr])
        hk = f(KP[near(KP)]).any(1) if (len(KP) and len(B)) else np.zeros(len(B), bool)
        return hl, hk
    dropped = []; exc = {}; gone = {}
    def cut(b, by=None):
        gone[b] = lay.pop(b); dropped.append(b)
        if os.environ.get("TDBG_TIGHT"): print("tighten: cut %s (for %s)" % (b, by), file=sys.stderr)
    def ok_inside(B): return np.array([inside(tuple(b)) for b in B], bool)
    def fix(n, allow_cut, R, depth=0):
        others = [m for m in lay if m != n]
        B, dd = cands(n, R); hl, hk = overl(B, others); good = ~hk
        idx = np.nonzero(good)[0]
        free = idx[~hl[idx].any(1)]
        if getattr(inside, "vec", None) is not None:
            if len(free):
                okf = _vin(inside, B[free])
                if okf.any(): setbb(n, B[free[int(np.argmax(okf))]]); return True
        else:
            for i in free:
                if inside(tuple(B[i])): setbb(n, B[i]); return True
        if not allow_cut: return False
        me = popf(n); best = None
        for i in idx:
            bl = [others[j] for j in np.nonzero(hl[i])[0]]
            if not bl or any(b in protected or (popf(b) >= me and n not in protected) for b in bl): continue
            key = (max(popf(b) for b in bl), len(bl), dd[i]) if n not in protected else (round(dd[i] / 6), max(popf(b) for b in bl), len(bl), dd[i])
            if best is None or key < best[0]:
                if inside(tuple(B[i])): best = (key, i, bl)
        if best is None and n in protected and R <= hard_max and depth < 1:
            for i in idx[::2][:500]:
                if not inside(tuple(B[i])): continue
                bl = [others[j] for j in np.nonzero(hl[i])[0]]
                pb = [b for b in bl if b in protected]
                if not pb or len(pb) > 2 or any(b not in protected and popf(b) >= me and False for b in bl): continue
                old = {m: lay[m]["bb"] for m in [n] + pb}; setbb(n, B[i]); ub = [b for b in bl if b not in protected]
                saved = {b: lay.pop(b) for b in ub}
                ok_ = True
                for b in pb:
                    if not fix(b, False, max(L, off(b)), depth + 1): ok_ = False; break
                for b, c_ in saved.items(): lay[b] = c_
                if ok_:
                    for b in sorted(ub, key=popf): cut(b, n)
                    return True
                for m, bb_ in old.items(): setbb(m, bb_)
            return False
        if best is None: return False
        for b in sorted(best[2], key=popf): cut(b, n)
        setbb(n, B[best[1]]); return True
    order = sorted(lay, key=lambda n: (n not in protected, n not in first, -popf(n)))
    for n in order:
        if n not in lay: continue
        if inside(lay[n]["bb"]) and off(n) <= L: continue
        if fix(n, True, L): continue
        if n in protected:
            cur_ok = inside(lay[n]["bb"]); r0 = off(n) if cur_ok else hard_max; R_ = L + 6
            while R_ < r0 and not fix(n, True, R_): R_ += 6
            if not cur_ok and not inside(lay[n]["bb"]): print("tighten: protected %s found no WA-only spot" % n)
            exc[n] = round(off(n))
        else:
            cut(n, "limit")

    for n in sorted(set(dropped), key=lambda n: -popf(n)):
        lay[n] = gone[n]
        if fix(n, False, L): dropped.remove(n)
        else: del lay[n]
    return dropped, exc

def regreedy(lay, real_px, keep, inside, L, protected, popf, first=(), step=2, hard_max=300, w_pref=0.3, cov_pen=10.0):
    ""\
\
\
\

    import numpy as np, math
    pref = {n: ((c["bb"][0] + c["bb"][2]) / 2, (c["bb"][1] + c["bb"][3]) / 2) for n, c in lay.items()}
    order = sorted(lay, key=lambda n: (n not in first, n not in protected, -popf(n)))
    KP = [tuple(k) for k in keep]; placed = {}
    def try_place(n, R, later):
        c = lay[n]; rx, ry = real_px[n]; b = c["bb"]; bw, bh = b[2] - b[0], b[3] - b[1]
        g = np.arange(-R, R + 1, step, dtype=float); GX, GY = np.meshgrid(g, g); GX, GY = GX.ravel(), GY.ravel()
        dd = np.hypot(GX, GY); m = dd <= R; GX, GY, dd = GX[m], GY[m], dd[m]
        CX, CY = rx + GX, ry + GY; X0, Y0 = CX - bw / 2, CY - bh / 2; X1, Y1 = X0 + bw, Y0 + bh
        O = np.array(list(placed.values()) + KP, float).reshape(-1, 4)
        ok = (X0 >= 16) & (X1 <= 99999)
        if len(O): ok &= ~(~((X1[:, None] < O[None, :, 0]) | (X0[:, None] > O[None, :, 2]) | (Y1[:, None] < O[None, :, 1]) | (Y0[:, None] > O[None, :, 3]))).any(1)
        cost = dd + w_pref * np.hypot(CX - pref[n][0], CY - pref[n][1])
        if len(later):
            cost = cost + cov_pen * ((later[None, :, 0] >= X0[:, None]) & (later[None, :, 0] <= X1[:, None]) & (later[None, :, 1] >= Y0[:, None]) & (later[None, :, 1] <= Y1[:, None])).sum(1)
        cost[~ok] = np.inf
        for j in np.argsort(cost, kind="stable"):
            if not np.isfinite(cost[j]): return None
            bb = (X0[j], Y0[j], X1[j], Y1[j])
            if inside(bb): return bb
        return None
    dropped = []
    for i, n in enumerate(order):
        later = np.array([real_px[m] for m in order[i + 1:]], float).reshape(-1, 2)
        bb = try_place(n, L, later)
        if bb is None and n in protected: bb = try_place(n, hard_max, later)
        if bb is None: dropped.append(n); continue
        c = lay[n]; c["tx"] += bb[0] - c["bb"][0]; c["ty"] += bb[1] - c["bb"][1]; c["bb"] = tuple(float(v) for v in bb); placed[n] = c["bb"]
    for n in list(dropped):
        bb = try_place(n, L, np.zeros((0, 2)))
        if bb is not None:
            c = lay[n]; c["tx"] += bb[0] - c["bb"][0]; c["ty"] += bb[1] - c["bb"][1]; c["bb"] = tuple(float(v) for v in bb); placed[n] = c["bb"]; dropped.remove(n)
    for n in dropped: del lay[n]
    return dropped, {}

def fix_outliers(lay, real_px, keep, inside, L, protected, popf, factor=1.5, radius=260, max_cut=2):
    ""\
\

    import math, copy
    def off(n): c = lay[n]; return math.hypot((c["bb"][0] + c["bb"][2]) / 2 - real_px[n][0], (c["bb"][1] + c["bb"][3]) / 2 - real_px[n][1])
    cut_all = []
    for n in sorted([n for n in lay if n in protected and off(n) > factor * L], key=lambda n: -off(n)):
        if n not in lay or off(n) <= factor * L: continue
        rx, ry = real_px[n]
        cl = [m for m in lay if math.hypot(real_px[m][0] - rx, real_px[m][1] - ry) <= radius]
        sub = {m: copy.deepcopy(lay[m]) for m in cl}
        fixed = [tuple(lay[m]["bb"]) for m in lay if m not in cl]
        before = sum(off(m) ** 2 for m in cl if m in protected)
        dr, _ = regreedy(sub, real_px, list(keep) + fixed, inside, L, protected, popf, first=(n,), w_pref=0.15)
        if any(m in protected for m in dr) or len(dr) > max_cut: continue
        o2 = lambda m: math.hypot((sub[m]["bb"][0] + sub[m]["bb"][2]) / 2 - real_px[m][0], (sub[m]["bb"][1] + sub[m]["bb"][3]) / 2 - real_px[m][1])
        after = sum(o2(m) ** 2 for m in sub if m in protected)
        if after < before:
            for m in cl:
                if m in sub: lay[m].update(tx=sub[m]["tx"], ty=sub[m]["ty"], bb=sub[m]["bb"])
                else: del lay[m]; cut_all.append(m)
    return cut_all

def extreme_line(tv, popf, word, cold, unit, fits):
    ""\
\

    v = min(tv.values()) if cold else max(tv.values())
    t = sorted([k for k, x in tv.items() if x == v], key=lambda k: -popf(k))
    num = "%d%s" % (v, unit)
    if len(t) == 1: return "%s town: %s %s" % (word, t[0], num)
    opts = []
    if len(t) <= 3: opts.append("%s towns: %s %s" % (word, ", ".join(t), num))
    for k in range(min(3, len(t) - 1), 0, -1):
        opts.append("%s towns: %s +%d more %s" % (word, ", ".join(t[:k]), len(t) - k, num))
    for o in opts:
        if fits(o): return o
    return opts[-1]

BAR_LAT = 49.0
NB_NORTH = {"west": 49.35, "east": 49.22}
NB_EAST = {"east": -116.45}
NB_PAD = 10
NB_MAXOFF = 40
NB_MAXOFF_R = {"full": 56, "west": 64}

NEIGHBOR_TOWNS = {
    "west": [("Vancouver BC", -123.1207, 49.2827, 662248, "Lower Mainland"), ("Abbotsford", -122.3045, 49.0504, 153524, "Lower Mainland"),
             ("Surrey", -122.8490, 49.1913, 568322, "Lower Mainland"), ("Chilliwack", -121.9515, 49.1579, 93203, "Lower Mainland"),
             ("Victoria", -123.3656, 48.4284, 91867, "Vancouver Island"), ("Nanaimo", -123.9401, 49.1659, 99863, "Vancouver Island"),
             ("Duncan", -123.7079, 48.7787, 5047, "Vancouver Island"), ("Sooke", -123.7276, 48.3740, 15086, "Vancouver Island"),
             ("Portland", -122.6784, 45.5152, 652503, "north Oregon"), ("Astoria", -123.8313, 46.1879, 10181, "north Oregon"),
             ("Hood River", -121.5215, 45.7054, 8313, "north Oregon"), ("The Dalles", -121.1787, 45.5946, 16010, "north Oregon"),
             ("Seaside", -123.9226, 45.9932, 6440, "north Oregon"), ("St. Helens", -122.8065, 45.8640, 13817, "north Oregon"),

             ("Scappoose", -122.8770, 45.7543, 7600, "north Oregon"), ("Hillsboro", -122.9898, 45.5229, 106447, "north Oregon"),
             ("Gresham", -122.4302, 45.4984, 114247, "north Oregon"), ("Troutdale", -122.3873, 45.5393, 16000, "north Oregon"),
             ("Cannon Beach", -123.9615, 45.8918, 1489, "north Oregon"), ("Warrenton", -123.9243, 46.1651, 6277, "north Oregon"),
             ("Clatskanie", -123.2065, 46.1018, 1700, "north Oregon"), ("Rainier OR", -122.9354, 46.0890, 1900, "north Oregon"),
             ("Cascade Locks", -121.8957, 45.6698, 1300, "north Oregon")],
    "east": [("Hermiston", -119.2895, 45.8404, 19354, "north Oregon"), ("Pendleton", -118.7886, 45.6721, 16894, "north Oregon"),
             ("The Dalles", -121.1787, 45.5946, 16010, "north Oregon"),
             ("Coeur d'Alene", -116.7805, 47.6777, 54628, "west Idaho"), ("Lewiston", -117.0177, 46.4165, 34203, "west Idaho"),
             ("Moscow", -117.0002, 46.7324, 25435, "west Idaho"), ("Sandpoint", -116.5533, 48.2766, 8639, "west Idaho"),
             ("Osoyoos", -119.4682, 49.0323, 5556, "BC"), ("Trail", -117.7117, 49.0966, 7920, "BC"), ("Grand Forks", -118.4452, 49.0303, 4112, "BC"),
             ("Milton-Freewater", -118.3877, 45.9326, 7151, "north Oregon")],

    "full": [("Vancouver BC", -123.1207, 49.2827, 662248, "Lower Mainland"), ("Abbotsford", -122.3045, 49.0504, 153524, "Lower Mainland"),
             ("Victoria", -123.3656, 48.4284, 91867, "Vancouver Island"), ("Nanaimo", -123.9401, 49.1659, 99863, "Vancouver Island"),
             ("Portland", -122.6784, 45.5152, 652503, "north Oregon"), ("Astoria", -123.8313, 46.1879, 10181, "north Oregon"),
             ("Pendleton", -118.7886, 45.6721, 16894, "north Oregon"), ("Hermiston", -119.2895, 45.8404, 19354, "north Oregon"),
             ("Hood River", -121.5215, 45.7054, 8313, "north Oregon"), ("The Dalles", -121.1787, 45.5946, 16010, "north Oregon"),
             ("Coeur d'Alene", -116.7805, 47.6777, 54628, "west Idaho"), ("Lewiston", -117.0177, 46.4165, 34203, "west Idaho"),
             ("Moscow", -117.0002, 46.7324, 25435, "west Idaho"), ("Sandpoint", -116.5533, 48.2766, 8639, "west Idaho"),
             ("Osoyoos", -119.4682, 49.0323, 5556, "BC"), ("Grand Forks", -118.4452, 49.0303, 4112, "BC")],
}
NB_WA_PTS = False
NB_AREA_MAX = {"west": {"Vancouver Island": 3, "Lower Mainland": 3, "north Oregon": 6},
               "east": {"north Oregon": 3, "west Idaho": 4, "BC": 3},
               "full": {"north Oregon": 4, "west Idaho": 3}}

def neighbor_labels(region, lay, keep, P, W, H, d, R, tiers, sample, fmt, BXP, GAP, wa_pts):
    import math, numpy as np
    out = {}; cnt = {}
    occ = [tuple(c["bb"]) for c in lay.values()] + [tuple(k) for k in keep]
    WP = np.array(wa_pts, float).reshape(-1, 2)
    hit = lambda a, b: not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
    for name, lo, la, pop, area in NEIGHBOR_TOWNS.get(region, []):
        if cnt.get(area, 0) >= NB_AREA_MAX.get(region, {}).get(area, 2): continue
        x, y = P(lo, la)
        if not (30 < x < W - 30 and 30 < y < H - 30): continue
        val = float(sample(lo, la))
        if not np.isfinite(val): continue
        _, npx, vpx, swt, rrt = next(t for t in tiers if pop >= t[0])
        if name in TINY_NB: npx, vpx, swt, rrt = TP.TINY_PX[0], TP.TINY_PX[1], 3, 5
        f1 = R.font(R.MONT, npx, 700); f2 = R.font(R.MONT, vpx, 800); na = f1.getbbox("Ag")[3]; th = na + GAP + f2.getbbox("0")[3] + 2
        t2 = fmt(val); tw = max(d.textlength(name, font=f1), d.textlength(t2, font=f2))
        got = None
        mo = NB_MAXOFF_R.get(region, NB_MAXOFF); g = np.arange(-mo, mo + 1, 2)
        for dx, dy in sorted(((a, b) for a in g for b in g if math.hypot(a, b) <= mo), key=lambda q: math.hypot(*q)):
            tx, ty = x - tw / 2 + dx, y - th / 2 + dy
            bb = (tx - BXP, ty - 1, tx + tw + BXP, ty + th + 1)
            if not (bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12): continue
            pb = (bb[0] - NB_PAD, bb[1] - NB_PAD, bb[2] + NB_PAD, bb[3] + NB_PAD)
            if any(hit(pb, o) for o in occ): continue
            if NB_WA_PTS and len(WP) and ((WP[:, 0] >= bb[0]) & (WP[:, 0] <= bb[2]) & (WP[:, 1] >= bb[1]) & (WP[:, 1] <= bb[3])).any(): continue
            got = (tx, ty, bb); break
        if not got: continue
        tx, ty, bb = got; occ.append(bb); cnt[area] = cnt.get(area, 0) + 1
        out[name] = dict(x=x, y=y, tx=tx, ty=ty, tw=tw, th=th, bb=bb, mk=(x - 1, y - 1, x + 1, y + 1), t2=t2, val=val, f1=f1, f2=f2, na=na,
                         sw=swt, rr=rrt, tier=0, name=name, neighbor=area)
    return out

def add_neighbor_labels(region, lay, keep, P, W, H, d, R, tiers, sample, fmt, BXP, GAP, wa_pts):
    ""\

    nl = neighbor_labels(region or "full", lay, keep, P, W, H, d, R, tiers, sample, fmt, BXP, GAP, wa_pts)
    out = {}
    for n_, c_ in nl.items(): lay[n_] = c_; out[n_] = c_["t2"] + " (" + c_["neighbor"] + ")"
    return out

VL_BAR_W, VL_TXT_PX, VL_HEAD_PX = 28, 24, 26

def vlegend_size(d, R, nbins, bin_h, labs, head):
    ft = R.font(R.MONT, VL_TXT_PX, 700); fh = R.font(R.MONT, VL_HEAD_PX, 800)
    lw = max([d.textlength(l, font=ft) for l in labs if l] + [0])
    w = max(d.textlength(head, font=fh), VL_BAR_W + 10 + lw) + 8
    h = VL_HEAD_PX + 12 + nbins * bin_h + VL_TXT_PX // 2 + 4
    return int(w + 1), int(h + 1)

def vlegend_spot(d, R, nbins, labs, head, obst, W, H, ytop, ybot, xmax=420, bins=(22, 20, 18, 16, 15, 14, 13, 12, 11, 10, 9), pad=10, wide=(16, 14, 12, 11, 10)):
    ""\

    hit = lambda a, b: not (a[2] + pad < b[0] or a[0] - pad > b[2] or a[3] + pad < b[1] or a[1] - pad > b[3])
    for xm in (60, 200, xmax):
        for bh in bins:
            w, h = vlegend_size(d, R, nbins, bh, labs, head)
            for x0 in range(16, xm, 6):
                for y0 in range(int(ytop), int(ybot - h), 6):
                    bx = (x0 - 4, y0 - 4, x0 + w, y0 + h)
                    if not any(hit(bx, o) for o in obst): return x0, y0, bh, bx
    for bh in wide:
        w, h = vlegend_size(d, R, nbins, bh, labs, head)
        for x0 in range(16, W - w - 16, 6):
            for y0 in range(int(ytop), int(ybot - h), 6):
                bx = (x0 - 4, y0 - 4, x0 + w, y0 + h)
                if not any(hit(bx, o) for o in obst): return x0, y0, bh, bx
    return None

def draw_vlegend(d, R, x0, y0, bin_h, cols, labs, head, ink=(14, 16, 22), label_at="edge"):
    ft = R.font(R.MONT, VL_TXT_PX, 700); fh = R.font(R.MONT, VL_HEAD_PX, 800)
    d.text((x0, y0), head, font=fh, fill=(255, 255, 255), stroke_width=4, stroke_fill=ink)
    n = len(cols); yt = y0 + VL_HEAD_PX + 12; yb = yt + n * bin_h
    d.rectangle((x0 - 2, yt - 2, x0 + VL_BAR_W + 2, yb + 2), fill=ink)
    for i, c in enumerate(cols): d.rectangle((x0, yb - (i + 1) * bin_h, x0 + VL_BAR_W, yb - i * bin_h), fill=c)
    last = 1e9
    for i, l in enumerate(labs):
        if not l: continue
        y = yb - i * bin_h - (bin_h / 2 if label_at == "center" else 0)
        if y > last - VL_TXT_PX: continue
        d.line((x0 + VL_BAR_W, y, x0 + VL_BAR_W + 6, y), fill=(255, 255, 255), width=2)
        d.text((x0 + VL_BAR_W + 10, y), l, font=ft, fill=(255, 255, 255), stroke_width=3, stroke_fill=ink, anchor="lm"); last = y

TF_ALPHA, TF_HOLD, TF_TAIL = 205, 0.72, 80

def top_fade(im, W, title_bottom):
    import math, numpy as np
    from PIL import Image
    y0 = title_bottom * TF_HOLD; y1 = title_bottom + TF_TAIL; H_ = int(y1) + 2
    al = np.zeros(H_, np.uint8)
    for y in range(H_):
        t = 0 if y <= y0 else min(1.0, (y - y0) / (y1 - y0))
        al[y] = int(round(TF_ALPHA * 0.5 * (1 + math.cos(math.pi * t))))
    ov = Image.new("RGBA", (W, H_), (0, 0, 0, 0)); ov.putalpha(Image.fromarray(np.repeat(al[:, None], W, 1), "L"))
    im.alpha_composite(ov, (0, 0))
    return int(y1)

def top_scale_geom(W, title_bottom, left_edge):
    if WT_BY0: return int(left_edge + 20), int(W - 50), int(WT_BY0)
    return int(left_edge + 20), int(W - 50), int(title_bottom + 40)

WT_LON = (-124.935, -120.845)
WT_BOT = 45.336
WT_GAP = 14
TINY_LAT = 46.22
TINY_KEEP = {"Vancouver", "Longview", "Kelso"}
WT_TOWN_DROP = {"Cathlamet"}
WT_NB_DROP = {"Nanaimo", "Chilliwack", "Seaside", "Scappoose", "Cannon Beach", "Hillsboro", "Sooke", "Gresham", "Troutdale", "Warrenton", "Clatskanie", "Rainier OR", "Cascade Locks", "Portland"}
def west_tight(g):
    W = g["W"]; title_y = g.get("TITLE_Y", 14); tpx = g.get("TITLE_PX", 100); sbh = g.get("SCALE_BH", 18)
    by0 = int(title_y + tpx * 1.15) + 40
    border_y = by0 + sbh + 6 + 26 + WT_GAP
    m = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
    k = W / math.radians(WT_LON[1] - WT_LON[0])
    mt = m(49.0) + border_y / k; lat_top = math.degrees(2 * math.atan(math.exp(mt)) - math.pi / 2)
    H = int(round((mt - m(WT_BOT)) * k))
    g.update(H=H, FRAME_BOX=(WT_LON[0], WT_BOT, WT_LON[1], lat_top), FRAME_W=1.0, FRAME_BH=1.0, FRAME_CY=0.5, SCALE_Y=by0, WEST_TIGHT=True)
    global WT_BY0; WT_BY0 = by0
    tiny = set()
    pts = {}
    for l in open(GAZ, encoding="latin-1"):
        c = l.rstrip("\n").split("\t")
        if c[0] == "WA": pts.setdefault(c[3].rsplit(" ", 1)[0], (float(c[11]), float(c[10])))
    pts.update(TP.REGION_POINTS)
    for t in g["TOWNS"]:
        if t in TINY_KEEP or t in g.get("PASSES", {}) or t not in pts: continue
        lo, la = TP.real_point(t, pts[t])
        if la < TINY_LAT: tiny.add(t)
    TP.TINY = tiny
    g.update(TOWNS=[t for t in g["TOWNS"] if t not in WT_TOWN_DROP], ORDER=[t for t in g["ORDER"] if t not in WT_TOWN_DROP])
    NEIGHBOR_TOWNS["west"] = [q for q in NEIGHBOR_TOWNS["west"] if q[0] not in WT_NB_DROP]
    TINY_NB.update(q[0] for q in NEIGHBOR_TOWNS["west"] if q[2] < TINY_LAT)
    return H
WT_BY0 = None
TINY_NB = set()
