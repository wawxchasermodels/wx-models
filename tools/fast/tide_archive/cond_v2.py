#!/usr/bin/env python3
"""Conditional Prediction v2 residuals (IB from AIFS ENS mean MSL, SST version D, optional STOFS wind).

Construction (fixed 2026-11-14): both modes sit on the same c1 backbone, applied once
  c1(t) = rs(t) + (rNow - rsNow) * exp(-lead/12 h)     during STOFS
        then 24 h relax to the 30-day mean residual     after STOFS ends
  W_D(t) = adj * (1 - exp(-lead/12 h))                 version D SST, 0 at issue
  dIB(t) = IB(AIFS or obs P) - IB(GFS / STOFS forcing)  reference-independent
  resid_on  = c1 + W_D + (dIB(t) - dIB(0)*fade)        wind-on; equals rNow at dt=0
  Wind      = (rs - anom) - IB_GFS                     anom = cwl minus cwl.noanomaly
  wind_comp = Wind(t) - Wind(0)*fade                   0 at dt=0 so default also matches obs
  resid_off = resid_on - wind_comp                     default (Wind surge off)

The 5-day station anomaly, the 12 h residual fade, and the 30-day offset stay in BOTH
modes (same as current Conditional). The toggle adds only wind, never IB or the anomaly.
If anom is missing, wind_comp is 0 (modes identical) so the default cannot drop the
anomaly. IB is 1 cm/hPa vs 1013.25 hPa, in feet; the AIFS-minus-GFS swap does not
depend on that reference.

resid_off / resid_on / wind_component below are the pre-fix constructors (kept so the
backtest can report the unfixed wind-on row). Use resid_pair / c1_resid for the live line.
"""
from __future__ import annotations
import math

P0 = 1013.25
CM_PER_HPA = 1.0
FT_PER_M = 3.28084
FT_PER_CM = FT_PER_M / 100.0  # 0.0328084
TAU_BIAS_H = 12.0
H_EFF_CAP_M = 400.0

def ib_ft(p_hpa):
    if p_hpa is None:
        return None
    try:
        p = float(p_hpa)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(p):
        return None
    return (P0 - p) * CM_PER_HPA * FT_PER_CM

def fade(dt_h, tau=TAU_BIAS_H):
    if dt_h is None or dt_h < 0:
        dt_h = 0.0
    return math.exp(-float(dt_h) / tau)

def wind_component(stofs_swl_ft, p_stofs_hpa):
    """STOFS surge minus IB on STOFS forcing pressure. 0 if either input is missing (do not
    substitute AIFS pressure — that would contaminate the wind term)."""
    ib = ib_ft(p_stofs_hpa)
    if stofs_swl_ft is None or ib is None:
        return 0.0
    try:
        s = float(stofs_swl_ft)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(s):
        return 0.0
    return s - ib

def d_ib(ib_aifs_ft, ib_stofs_ft):
    """AIFS (or obs) IB minus STOFS-forcing IB. Independent of the 1013.25 vs local-mean reference."""
    if ib_aifs_ft is None or ib_stofs_ft is None:
        return 0.0
    return float(ib_aifs_ft) - float(ib_stofs_ft)

def c1_resid(rs_t, r_now, rs_now, dt_h):
    """Current Conditional residual while STOFS is available: 3 h swl + fading (rNow-rsNow)."""
    return float(rs_t) + (float(r_now) - float(rs_now)) * fade(dt_h)

def wind_only(stofs_swl_ft, anom_ft, p_stofs_hpa):
    """Non-IB, non-anomaly part of STOFS. Missing anom or forcing P => None (do not guess)."""
    ib = ib_ft(p_stofs_hpa)
    if stofs_swl_ft is None or anom_ft is None or ib is None:
        return None
    try:
        s = float(stofs_swl_ft)
        a = float(anom_ft)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(s) and math.isfinite(a)):
        return None
    return s - a - ib

def wind_comp(wind_t, wind_0, dt_h):
    """Toggle increment. 0 at dt=0 (both modes match obs); equals wind_t at long lead."""
    if wind_t is None:
        return 0.0
    w0 = 0.0 if wind_0 is None else float(wind_0)
    return float(wind_t) - w0 * fade(dt_h)

def resid_on_fixed(c1, W_ft, d_ib_t, d_ib_0, dt_h):
    """Wind-on residual: c1 + version D SST + faded pressure-source swap. Equals c1 at dt=0 if W_D(0)=0."""
    d0 = 0.0 if d_ib_0 is None else float(d_ib_0)
    return float(c1) + float(W_ft) + (float(d_ib_t) - d0 * fade(dt_h))

def resid_off_fixed(resid_on, wind_comp_t):
    return float(resid_on) - float(wind_comp_t)

def resid_pair(rs_t, r_now, rs_now, dt_h, W_ft, ib_aifs_ft, ib_gfs_ft, anom_ft, d_ib_0, wind_0):
    """Return (off, on, wind_comp) for the fixed construction. If anom or GFS IB is missing,
    wind_comp is 0 and the two modes match (both stay on the c1 + SST + dIB line)."""
    c1 = c1_resid(rs_t, r_now, rs_now, dt_h)
    dibt = d_ib(ib_aifs_ft, ib_gfs_ft)
    on = resid_on_fixed(c1, W_ft, dibt, d_ib_0, dt_h)
    # wind_only needs a pressure; reconstruct from ib_gfs via the same reference
    w_t = None
    if anom_ft is not None and ib_gfs_ft is not None and rs_t is not None:
        w_t = float(rs_t) - float(anom_ft) - float(ib_gfs_ft)
    wc = wind_comp(w_t, wind_0, dt_h)
    off = resid_off_fixed(on, wc)
    return off, on, wc

def resid_off(ib_aifs_ft, W_ft, r_now, ib_now_ft, W_now_ft, dt_h):
    """PRE-FIX wind-off (kept for the 'wind-on before fix' backtest row)."""
    return (ib_aifs_ft + W_ft) + (r_now - ib_now_ft - W_now_ft) * fade(dt_h)

def resid_on(ib_aifs_ft, W_ft, r_now, ib_now_ft, W_now_ft, dt_h, wind_ft):
    """PRE-FIX wind-on (kept for the 'wind-on before fix' backtest row)."""
    return resid_off(ib_aifs_ft, W_ft, r_now, ib_now_ft, W_now_ft, dt_h) + wind_ft

def rho_unesco(T, S, p=0.0):
    """UNESCO EOS-80 seawater density (kg/m3). T in deg C, S in psu, p in dbar (default surface)."""
    T, S, p = float(T), float(S), float(p)
    # one-atmosphere density (UNESCO 1983 / Fofonoff & Millard)
    a0, a1, a2, a3, a4, a5 = 999.842594, 6.793952e-2, -9.095290e-3, 1.001685e-4, -1.120083e-6, 6.536332e-9
    b0, b1, b2, b3, b4 = 8.24493e-1, -4.0899e-3, 7.6438e-5, -8.2467e-7, 5.3875e-9
    c0, c1, c2 = -5.72466e-3, 1.0227e-4, -1.6546e-6
    d0 = 4.8314e-4
    smow = a0 + T*(a1 + T*(a2 + T*(a3 + T*(a4 + T*a5))))
    rho = smow + S*(b0 + T*(b1 + T*(b2 + T*(b3 + T*b4)))) + S**1.5*(c0 + T*(c1 + T*c2)) + d0*S*S
    if p == 0:
        return rho
    # secant bulk modulus (surface is enough for alpha at the surface; include p for completeness)
    e0, e1, e2 = 19652.21, 148.4206, -2.327105
    e3, e4 = 1.360477e-2, -5.155288e-5
    f0, f1, f2, f3 = 54.6746, -0.603459, 1.09987e-2, -6.1670e-5
    g0, g1, g2 = 7.944e-2, 1.6483e-2, -5.3009e-5
    Kw = e0 + T*(e1 + T*(e2 + T*(e3 + T*e4)))
    K = Kw + S*(f0 + T*(f1 + T*(f2 + T*f3))) + S**1.5*(g0 + T*(g1 + T*g2))
    # pressure terms (standard UNESCO)
    h0, h1, h2, h3 = 3.239908, 1.43713e-3, 1.16092e-4, -5.77905e-7
    i0, i1, i2 = 2.2838e-3, -1.0981e-5, -1.6078e-6
    j0 = 1.91075e-4
    k0, k1, k2 = 8.50935e-5, -6.12293e-6, 5.2787e-8
    m0, m1, m2 = -9.9348e-7, 2.0816e-8, 9.1697e-10
    Aw = h0 + T*(h1 + T*(h2 + T*h3))
    A = Aw + S*(i0 + T*(i1 + T*i2)) + j0*S**1.5
    Bw = k0 + T*(k1 + T*k2)
    B = Bw + S*(m0 + T*(m1 + T*m2))
    Kp = K + p*(A + p*B)
    return rho / (1.0 - p/Kp)

def alpha_thermal(T, S):
    """Surface thermal expansion coefficient (1/K) from a centered UNESCO density derivative."""
    dT = 0.05
    r1, r2 = rho_unesco(T - dT, S), rho_unesco(T + dT, S)
    mid = 0.5 * (r1 + r2)
    return -(r2 - r1) / (2.0 * dT) / mid

def W_ft(dT_C, T_C, S, H_eff_m):
    """Steric height in feet: alpha(T,S) * anomaly(K) * H_eff(m)."""
    if dT_C is None or T_C is None or H_eff_m is None:
        return 0.0
    a = alpha_thermal(T_C, S)
    return a * float(dT_C) * float(H_eff_m) * FT_PER_M

def clamp_H_eff(h):
    if h is None or not math.isfinite(h) or h < 0:
        return 0.0
    return min(float(h), H_EFF_CAP_M)

def W_D(adj_ft, dt_h):
    """Version D warm-water increment (ft): adj faded in, 0 at the issue/now time.

    adj_ft = k * (mean newest 2 days SSTA - mean prior 5 days). The 30-day steric
    is already in STOFS's 5-day bias and must not be added on top.
    """
    if adj_ft is None or not math.isfinite(adj_ft):
        return 0.0
    return float(adj_ft) * (1.0 - fade(dt_h))
