#!/usr/bin/env python3
"""Compare MUR / Geo-Polar / OISST (and OSTIA if present) against in-situ water temperature,
pick a per-station source, blend in situ for Puget Sound / nearshore, build a consistent
2019-2024 day-of-year climatology, refit k, and write sst.json for the tide viewer.
"""
from __future__ import annotations
import datetime as D, json, math, os, glob, collections

HIRES = "/tmp/sst_work/hires"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "..", "site", "tide", "sst.json")
OUT_CMP = os.path.join(HERE, "sst_source_compare.json")

STATIONS = {
    "9439040": {"name": "Astoria, OR", "sound": False, "ndbc": ["ASTO3", "46029"]},
    "9440910": {"name": "Toke Point, WA", "sound": False, "ndbc": ["TOKW1", "46041"]},
    "9441102": {"name": "Westport, WA", "sound": False, "ndbc": ["WPTW1", "46041"]},
    "9442396": {"name": "La Push, WA", "sound": False, "ndbc": ["LAPW1"]},
    "9443090": {"name": "Neah Bay, WA", "sound": False, "ndbc": ["NEAW1", "46087"]},
    "9444090": {"name": "Port Angeles, WA", "sound": True, "ndbc": ["PTAW1", "46088"]},
    "9444900": {"name": "Port Townsend, WA", "sound": True, "ndbc": ["PTWW1", "SISW1"]},
    "9449880": {"name": "Friday Harbor, WA", "sound": True, "ndbc": ["FRDW1"]},
    "9449424": {"name": "Cherry Point, WA", "sound": True, "ndbc": ["CHYW1", "CPNW1"]},
    "9447130": {"name": "Seattle, WA", "sound": True, "ndbc": ["WPOW1"]},
    "9446484": {"name": "Tacoma, WA", "sound": True, "ndbc": ["TCNW1", "TCMW1"]},
}
PRODUCTS = ["mur", "geopolar_dn", "geopolar_n", "oisst", "ostia"]
PROD_LABEL = {
    "mur": "NASA JPL MUR v4.1 (0.01°)",
    "geopolar_dn": "NOAA Geo-Polar Blended Day+Night (5 km)",
    "geopolar_n": "NOAA Geo-Polar Blended Night (5 km)",
    "oisst": "NOAA OISST v2.1 (0.25°)",
    "ostia": "UK Met OSTIA (0.05°)",
    "coops": "CO-OPS water temperature (gauge)",
    "ndbc": "NDBC / CMAN water temperature",
    "blend": "In-situ blend (gauge + bias-corrected satellite)",
}
CLIM_A, CLIM_B = D.date(2019, 1, 1), D.date(2024, 12, 31)
FIT_A, FIT_B = "2023-06", "2025-10"
LATENT_D = 2   # days: don't use an analysis newer than issue-2d

def load_product(prod):
    out = {}
    d = os.path.join(HIRES, prod)
    if not os.path.isdir(d):
        return out
    for sid in STATIONS:
        fn = os.path.join(d, f"{sid}.json")
        if not os.path.exists(fn):
            continue
        rec = json.load(open(fn))
        out[sid] = {"series": {D.date.fromisoformat(k): float(v) for k, v in (rec.get("series") or {}).items()},
                    "pixel": rec.get("pixel")}
    return out

def load_insitu():
    coops, ndbc_by_st = {}, {sid: {} for sid in STATIONS}
    for sid in STATIONS:
        fn = os.path.join(HIRES, "insitu_coops", f"{sid}.json")
        if os.path.exists(fn):
            rec = json.load(open(fn))
            coops[sid] = {D.date.fromisoformat(k): float(v) for k, v in (rec.get("daily") or {}).items()}
        merged = {}
        for hid in STATIONS[sid]["ndbc"]:
            fn = os.path.join(HIRES, "insitu_ndbc", f"{hid}.json")
            if not os.path.exists(fn):
                continue
            rec = json.load(open(fn))
            for k, v in (rec.get("daily") or {}).items():
                merged.setdefault(k, []).append(float(v))
        ndbc_by_st[sid] = {D.date.fromisoformat(k): sum(vs)/len(vs) for k, vs in merged.items()}
    return coops, ndbc_by_st

def stats(pairs):
    """pairs: list of (sat, insitu). bias = sat - insitu. RMSE, n."""
    if len(pairs) < 10:
        return {"n": len(pairs), "bias": None, "rmse": None, "mae": None, "r": None}
    n = len(pairs)
    bias = sum(s - i for s, i in pairs) / n
    mse = sum((s - i)**2 for s, i in pairs) / n
    mae = sum(abs(s - i) for s, i in pairs) / n
    ms = sum(s for s, _ in pairs)/n
    mi = sum(i for _, i in pairs)/n
    num = sum((s-ms)*(i-mi) for s, i in pairs)
    den = (sum((s-ms)**2 for s,_ in pairs)*sum((i-mi)**2 for _,i in pairs))**0.5
    r = (num/den) if den else None
    return {"n": n, "bias": bias, "rmse": mse**0.5, "mae": mae, "r": r,
            "rmse_bc": (sum((s - i - bias)**2 for s, i in pairs)/n)**0.5}

def doy(d):
    return d.timetuple().tm_yday

def clim_of(series, a=CLIM_A, b=CLIM_B, half=3):
    """Mean of (doy ± half days) over the clim window, returning {doy: C}."""
    buckets = collections.defaultdict(list)
    for d, v in series.items():
        if a <= d <= b:
            buckets[doy(d)].append(v)
    out = {}
    for n in range(1, 367):
        vals = []
        for k in range(-half, half+1):
            vals.extend(buckets.get(((n-1+k) % 365)+1, []))
        if len(vals) >= 8:
            out[n] = sum(vals)/len(vals)
    return out

def anom_series(series, clim):
    out = {}
    for d, v in series.items():
        c = clim.get(doy(d))
        if c is not None:
            out[d] = v - c
    return out

def fit_k(resid_monthly, ssta_monthly):
    """Slope of monthly residual (ft) vs monthly SSTA (C), floored at 0. Returns k, r, n."""
    xs, ys = [], []
    for m, r in resid_monthly.items():
        if m < FIT_A or m > FIT_B:
            continue
        if m in ssta_monthly and ssta_monthly[m] is not None:
            xs.append(ssta_monthly[m]); ys.append(r)
    n = len(xs)
    if n < 8:
        return 0.0, None, n
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    den = sum((x-mx)**2 for x in xs)
    k = (num/den) if den else 0.0
    if k < 0:
        k = 0.0
    # r
    ny = sum((y-my)**2 for y in ys)
    r = (num/(den*ny)**0.5) if den and ny else None
    return k, r, n

def monthly_mean(series):
    mon = collections.defaultdict(list)
    for d, v in series.items():
        mon[d.strftime("%Y-%m")].append(v)
    return {m: sum(vs)/len(vs) for m, vs in mon.items() if len(vs) >= 8}

def main():
    products = {}
    for p in PRODUCTS:
        products[p] = load_product(p)
        print(f"loaded {p}: {len(products[p])} stations, days={max((len(v['series']) for v in products[p].values()), default=0)}")
    coops, ndbc = load_insitu()
    print(f"insitu coops stations={len(coops)} ndbc={sum(1 for s in ndbc if ndbc[s])}")

    compare = {}
    chosen = {}
    series_op = {}  # operational temperature series used for anomaly
    clim_op = {}
    ssta_op = {}
    k_fit = {}
    pixels = (json.load(open(os.path.join(HIRES, "pixels.json"))) if os.path.exists(os.path.join(HIRES, "pixels.json")) else {})

    for sid, meta in STATIONS.items():
        # prefer CO-OPS at the gauge; fall back to NDBC daily
        ins = coops.get(sid) or {}
        ins_src = "coops" if ins else None
        if len(ins) < 60 and ndbc.get(sid):
            # fill gaps or replace
            if not ins:
                ins, ins_src = ndbc[sid], "ndbc"
            else:
                merged = dict(ndbc[sid])
                merged.update(ins)
                ins, ins_src = merged, "coops+ndbc"
        # A couple of leftover days (Seattle) is not a usable in-situ record
        if len(ins) < 60:
            ins, ins_src = {}, None
        row = {"name": meta["name"], "sound": meta["sound"], "insitu_src": ins_src, "insitu_days": len(ins), "products": {}}
        best = None
        for p, data in products.items():
            rec = data.get(sid)
            if not rec or not rec["series"]:
                continue
            sat = rec["series"]
            pairs = [(sat[d], ins[d]) for d in sat.keys() & ins.keys()]
            st = stats(pairs)
            st["pixel"] = rec.get("pixel")
            st["days"] = len(sat)
            row["products"][p] = st
            # pick by raw RMSE (how well the analysis matches the gauge)
            if st["rmse"] is not None and (best is None or st["rmse"] < best[1]):
                best = (p, st["rmse"], st)
        row["best_sat"] = best[0] if best else None
        compare[sid] = row

        # Operational series
        if best:
            sat = products[best[0]][sid]["series"]
            bias = best[2]["bias"] or 0.0
            sat_bc = {d: v - bias for d, v in sat.items()}  # in-situ frame
            if meta["sound"] or (best[2]["rmse"] is not None and best[2]["rmse"] > 1.0 and ins):
                # blend in situ when present; otherwise bias-corrected satellite
                blend = dict(sat_bc)
                for d, v in ins.items():
                    blend[d] = 0.7 * v + 0.3 * sat_bc.get(d, v)
                series_op[sid] = blend
                src_used = f"blend:{best[0]}+{ins_src or 'insitu'}"
            else:
                series_op[sid] = sat_bc
                src_used = best[0] + "_bc"
            row["chosen"] = src_used
            row["chosen_sat"] = best[0]
            row["sat_bias_removed_C"] = bias
        elif ins:
            series_op[sid] = dict(ins)
            row["chosen"] = ins_src or "insitu"
            row["chosen_sat"] = None
            row["sat_bias_removed_C"] = 0.0
        else:
            # No in-situ at this gauge (Seattle and Cherry Point have no water-temp sensor).
            # Use the finest analysis that has a water pixel; do not skip k-fit.
            fallback = None
            for p in ("mur", "geopolar_dn", "geopolar_n", "oisst", "ostia"):
                if products.get(p) and products[p].get(sid) and products[p][sid]["series"]:
                    fallback = p
                    break
            if not fallback:
                row["chosen"] = None
                print("no sat and no in-situ", sid)
                continue
            series_op[sid] = dict(products[fallback][sid]["series"])
            row["chosen"] = fallback + " (no in-situ at this gauge)"
            row["chosen_sat"] = fallback
            row["sat_bias_removed_C"] = 0.0
            row["best_sat"] = fallback
            print(f"{sid} no in-situ; operational series = {fallback}")
        chosen[sid] = row["chosen"]
        clim_op[sid] = clim_of(series_op[sid])
        ssta_op[sid] = anom_series(series_op[sid], clim_op[sid])
        row["clim_n_doy"] = len(clim_op[sid])
        # latest anomaly (for the live sidecar): last day minus 2-day latency vs today
        today = D.date(2026, 11, 14)
        usable = {d: v for d, v in ssta_op[sid].items() if d <= today - D.timedelta(days=LATENT_D)}
        row["ssta_latest"] = None
        row["ssta30"] = None
        row["last_day"] = None
        if usable:
            last = max(usable)
            row["last_day"] = last.isoformat()
            row["ssta_latest"] = usable[last]
            window = [usable[last - D.timedelta(days=k)] for k in range(30) if (last - D.timedelta(days=k)) in usable]
            if window:
                row["ssta30"] = sum(window)/len(window)

    # k fit against monthly residual
    resid_dir = os.path.join(HIRES, "residuals")
    for sid in STATIONS:
        if sid not in ssta_op:
            continue
        fn = os.path.join(resid_dir, f"{sid}.json")
        if not os.path.exists(fn):
            print("no residuals yet", sid)
            continue
        rec = json.load(open(fn))
        rm = rec.get("resid_monthly") or {}
        sm = monthly_mean(ssta_op[sid])
        k, r, n = fit_k(rm, sm)
        k_fit[sid] = {"k_ft_per_c": round(k, 4), "r": None if r is None else round(r, 3), "n_months": n}
        compare[sid]["k"] = k_fit[sid]
        print(f"k {sid} {STATIONS[sid]['name']:18s} k={k:.4f} r={r} n={n} chosen={compare[sid].get('chosen')} best_sat={compare[sid].get('best_sat')}")

    # live sst.json
    stations_out = {}
    for sid, meta in STATIONS.items():
        k = (k_fit.get(sid) or {}).get("k_ft_per_c", 0.0)
        ssta30 = compare.get(sid, {}).get("ssta30")
        ssta = compare.get(sid, {}).get("ssta_latest")
        # prefer 30-day mean anomaly for the steric term (less noisy); also store latest
        use = ssta30 if ssta30 is not None else (ssta if ssta is not None else 0.0)
        W = k * use
        stations_out[sid] = {
            "name": meta["name"],
            "source": compare.get(sid, {}).get("chosen"),
            "chosen_sat": compare.get(sid, {}).get("chosen_sat"),
            "k_ft_per_c": k,
            "ssta": None if ssta is None else round(ssta, 3),
            "ssta30_c": None if ssta30 is None else round(ssta30, 3),
            "W": round(W, 4),
            "steric_ft": round(W, 4),
            "last_day": compare.get(sid, {}).get("last_day"),
            "clim": "2019-2024 DOY ±3d mean of the operational (blended) series",
            "blend": compare.get(sid, {}).get("chosen"),
            "sat_bias_removed_C": None if compare.get(sid, {}).get("sat_bias_removed_C") is None else round(compare[sid]["sat_bias_removed_C"], 3),
        }

    out_cmp = {
        "compared_at": "2026-11-14",
        "climatology": "2019-01-01 through 2024-12-31, day-of-year ±3 days, consistent across sources after bias-correcting satellite to in-situ",
        "validation": "daily satellite SST vs daily mean in-situ water temperature (CO-OPS gauge preferred, NDBC/CMAN to fill)",
        "ostia": "UK Met OSTIA was requested; CoastWatch ERDDAP dataset jplUKMO_OSTIAv20 returns 404 and PODAAC OpenDAP requires Earthdata login, so OSTIA is not in this comparison.",
        "stations": compare,
        "k_fit": k_fit,
        "k_fit_window": [FIT_A, FIT_B],
        "products_present": [p for p in PRODUCTS if products[p]],
    }
    os.makedirs(os.path.dirname(OUT_CMP), exist_ok=True)
    json.dump(out_cmp, open(OUT_CMP, "w"), indent=2, default=str)
    live = {"source_note": out_cmp["climatology"], "sst_method": "full-anomaly", "stations": stations_out, "k_fit_window": [FIT_A, FIT_B]}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(live, open(OUT_JSON, "w"), indent=2)
    # also a copy under hires
    json.dump(out_cmp, open(os.path.join(HIRES, "sst_source_compare.json"), "w"), indent=2, default=str)
    json.dump(live, open(os.path.join(HIRES, "sst.json"), "w"), indent=2)
    # dump ssta series for the backtest
    ssta_dump = {sid: {d.isoformat(): v for d, v in ser.items()} for sid, ser in ssta_op.items()}
    json.dump({"latent_d": LATENT_D, "ssta": ssta_dump, "k": {s: (k_fit.get(s) or {}).get("k_ft_per_c", 0) for s in STATIONS}},
              open(os.path.join(HIRES, "ssta_series.json"), "w"))
    print("wrote", OUT_CMP, "and", OUT_JSON)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
