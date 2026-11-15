#!/usr/bin/env python3
"""Guard / unit test: the Wind surge toggle adds ONLY wind, never the low-pressure term or the
STOFS 5-day anomaly again.

  wind_on - wind_off == wind_comp   (exactly, for every lead)
  wind_comp == 0  =>  wind_on == wind_off
  at dt=0 both modes equal rNow
  wind-on == c1 + W_D + faded dIB
  wind uses (swl - anom) - IB(STOFS forcing), never IB(AIFS) and never raw swl (which includes IB + anomaly)
"""
from __future__ import annotations
import math, os, sys, random

HERE = os.path.dirname(os.path.abspath(__file__))
CANDS = [
    os.path.join(HERE, "..", "tools", "fast", "tide_archive"),
    os.path.join(HERE, "..", "tide_sst_warmwater_mock_20261114", "tools", "fast", "tide_archive"),
    os.path.join("/workspace/wx-models-site/tide_sst_warmwater_mock_20261114/tools/fast/tide_archive"),
]
sys.path[:0] = [p for p in CANDS if os.path.isdir(p)]
import cond_v2 as C

EPS = 1e-12

def nearly(a, b, eps=EPS):
    return abs(a - b) <= eps * max(1.0, abs(a), abs(b))

def main():
    fails = []
    rng = random.Random(20261114)

    # 1) algebraic identity on a dense grid of leads and random physical inputs (fixed construction)
    for dt in [0, 0.5, 1, 3, 6, 12, 18, 24, 36, 48, 72, 96]:
        for _ in range(40):
            ib_aifs = C.ib_ft(rng.uniform(960, 1040))
            ib_gfs = C.ib_ft(rng.uniform(960, 1040))
            ib_aifs0 = C.ib_ft(rng.uniform(960, 1040))
            ib_gfs0 = C.ib_ft(rng.uniform(960, 1040))
            rs = rng.uniform(-2.5, 4.0)
            rs_now = rng.uniform(-2.5, 4.0)
            anom = rng.uniform(-0.5, 2.0)
            anom0 = rng.uniform(-0.5, 2.0)
            W = C.W_D(rng.uniform(-0.3, 0.6), dt)
            r_now = rng.uniform(-1.5, 2.5)
            d0 = C.d_ib(ib_aifs0, ib_gfs0)
            w0 = rs_now - anom0 - ib_gfs0
            off, on, wc = C.resid_pair(rs, r_now, rs_now, dt, W, ib_aifs, ib_gfs, anom, d0, w0)
            if not nearly(on - off, wc):
                fails.append(f"identity failed dt={dt}: on-off={on-off} wind={wc}")
            off0, on0, wc0 = C.resid_pair(rs, r_now, rs_now, dt, W, ib_aifs, ib_gfs, None, d0, w0)
            if not nearly(on0, off0) or not nearly(wc0, 0.0):
                fails.append(f"missing-anom modes must match dt={dt}: off={off0} on={on0} wc={wc0}")

    # 2) explicit zero-wind: missing anom, missing forcing P, and (swl-anom)==IB
    r_now, rs_now, rs, ib_a, ib_g, d0 = 0.5, 0.6, 0.7, 0.2, 0.1, 0.05
    W = C.W_D(0.08, 6)
    off, on, wc = C.resid_pair(rs, r_now, rs_now, 6, W, ib_a, ib_g, None, d0, 0.0)
    if not nearly(wc, 0.0) or not nearly(on, off):
        fails.append("missing anom should force zero wind_comp and matching modes")
    # constructed zero wind: swl - anom = IB_GFS
    anom = rs - ib_g
    w0 = 0.0
    off, on, wc = C.resid_pair(rs, r_now, rs_now, 6, W, ib_a, ib_g, anom, d0, w0)
    # wind_t = rs-anom-ib_g = 0; wind_comp = 0 - 0*fade = 0
    if not nearly(wc, 0.0) or not nearly(on, off):
        fails.append(f"constructed zero wind did not match: wc={wc} on={on} off={off}")

    # 3) never double IB and never put the 5-day anomaly into the wind term
    p_aifs, p_stofs = 980.0, 1010.0
    rs, anom, r_now, rs_now, dt = 0.80, 0.40, 0.42, 0.55, 24
    ib_aifs, ib_stofs = C.ib_ft(p_aifs), C.ib_ft(p_stofs)
    w = C.wind_only(rs, anom, p_stofs)
    if not nearly(w, rs - anom - ib_stofs):
        fails.append(f"wind_only must be (swl-anom)-IB(STOFS): {w}")
    if nearly(w, rs - anom - ib_aifs):
        fails.append("wind_only incorrectly used AIFS pressure")
    if nearly(w, rs - ib_stofs):
        fails.append("wind_only failed to remove the 5-day anomaly")
    W = C.W_D(0.05, dt)
    d0 = C.d_ib(ib_aifs, ib_stofs)
    w0 = C.wind_only(rs_now, anom, p_stofs)
    off, on, wc = C.resid_pair(rs, r_now, rs_now, dt, W, ib_aifs, ib_stofs, anom, d0, w0)
    c1 = C.c1_resid(rs, r_now, rs_now, dt)
    if nearly(on, off + rs):
        fails.append("wind-on equals wind-off + raw STOFS: IB and/or anomaly were doubled")
    if not nearly(on, C.resid_on_fixed(c1, W, C.d_ib(ib_aifs, ib_stofs), d0, dt)):
        fails.append("wind-on is not c1 + W_D + faded dIB")
    # changing AIFS pressure must not change the wind increment
    ib_aifs2 = C.ib_ft(1025.0)
    off2, on2, wc2 = C.resid_pair(rs, r_now, rs_now, dt, W, ib_aifs2, ib_stofs, anom, d0, w0)
    if not nearly(on2 - off2, wc) or not nearly(on2 - off2, on - off):
        fails.append("AIFS pressure change must not change the wind increment")

    # 4) at issue time, BOTH modes match the observed residual (rNow)
    rs, r_now, rs_now, anom, anom0 = 0.70, 0.42, 0.55, 0.35, 0.30
    ib_aifs, ib_gfs = C.ib_ft(1016.0), C.ib_ft(1015.0)
    # at dt=0, p and rs are the t0 values
    d0 = C.d_ib(ib_aifs, ib_gfs)
    w0 = C.wind_only(rs_now, anom0, 1015.0)
    off, on, wc = C.resid_pair(rs_now, r_now, rs_now, 0, C.W_D(0.08, 0), ib_aifs, ib_gfs, anom0, d0, w0)
    if not nearly(off, r_now):
        fails.append(f"wind-off at dt=0 must equal rNow: {off} vs {r_now}")
    if not nearly(on, r_now):
        fails.append(f"wind-on at dt=0 must equal rNow: {on} vs {r_now}")
    if not nearly(wc, 0.0):
        fails.append(f"wind_comp at dt=0 must be 0, got {wc}")

    # 5) version D fade-in + identity, and long-lead default keeps the anomaly
    adj = 0.08
    if not nearly(C.W_D(adj, 0), 0.0):
        fails.append(f"W_D(0) must be 0, got {C.W_D(adj, 0)}")
    if not nearly(C.W_D(adj, 1e9), adj):
        fails.append(f"W_D(inf) must equal adj, got {C.W_D(adj, 1e9)}")
    rs, r_now, rs_now, anom = 0.80, 0.42, 0.55, 0.40
    ib_a, ib_g = C.ib_ft(1012.0), C.ib_ft(1014.0)
    d0 = C.d_ib(ib_a, ib_g)
    w0 = rs_now - anom - ib_g
    for dt in (0, 3, 12, 24, 72, 1e9):
        W = C.W_D(adj, dt)
        rs_t = rs_now if dt == 0 else rs
        off, on, wc = C.resid_pair(rs_t, r_now, rs_now, dt, W, ib_a, ib_g, anom, d0, w0)
        if not nearly(on - off, wc):
            fails.append(f"identity failed with W_D at dt={dt}: {on-off} vs {wc}")
        if dt == 0 and not nearly(off, r_now):
            fails.append(f"version D wind-off at dt=0 must equal rNow, got {off}")
        if dt >= 1e8:
            # long lead: off = anom + W_D + IB_AIFS   (fade, dIB0 fade, wind all settled)
            expect_off = anom + W + ib_a
            if not nearly(off, expect_off):
                fails.append(f"long-lead default must keep anomaly + IB_AIFS + W_D: {off} vs {expect_off}")

    # 6) dIB is independent of the 1013.25 vs local-mean reference
    p_a, p_g, p_ref = 1008.0, 1016.0, 1018.0
    d_1013 = C.d_ib(C.ib_ft(p_a), C.ib_ft(p_g))
    # IB vs a different reference: (Pref-P)*c = ib_1013 + (Pref-1013.25)*c ; difference unchanged
    def ib_ref(p, p0):
        return (p0 - p) * C.FT_PER_CM
    d_clim = ib_ref(p_a, p_ref) - ib_ref(p_g, p_ref)
    if not nearly(d_1013, d_clim):
        fails.append(f"dIB must be reference-independent: {d_1013} vs {d_clim}")

    if fails:
        print("FAIL", len(fails))
        for f in fails[:20]:
            print(" ", f)
        return 1
    print("PASS  wind-on minus wind-off equals the wind component exactly; zero wind => modes match; both modes equal rNow at dt=0; wind is (swl-anom)-IB_GFS; anomaly and IB are not doubled; dIB is reference-independent.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
