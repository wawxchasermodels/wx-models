#!/usr/bin/env python3
"""NCEP/NCAR Reanalysis 1 monthly long-term mean (1991-2020) 850 mb air temperature -> small npz for the 850 mb anomaly maps.
Data: NOAA PSL (public domain), ncep.reanalysis.derived/pressure/air.mon.ltm.1991-2020.nc (2.5 deg, 12 months).
Same source, period and method as the 500 mb anomaly climatology (make_clim.py): monthly means, interpolated in time to the
valid date by the map code. Stored in deg C.
usage: make_clim_t850.py air.mon.ltm.1991-2020.nc out.npz   (needs h5py)"""
import sys, h5py, numpy as np
f = h5py.File(sys.argv[1]); i = list(f["level"][:]).index(850); v = f["air"]; a = v.attrs
g = lambda k, d: float(np.ravel(a[k])[0]) if k in a else d
t = v[:, i, :, :].astype("f4") * g("scale_factor", 1.0) + g("add_offset", 0.0)
if np.nanmean(t) > 150: t = t - 273.15   # file in K -> C
np.savez_compressed(sys.argv[2], t850=t.astype("f4"), lat=f["lat"][:], lon=f["lon"][:])
print("ok", sys.argv[2], t.shape, f"{np.nanmin(t):.1f}..{np.nanmax(t):.1f} C")
