#!/usr/bin/env python3
"""NCEP/NCAR Reanalysis 1 monthly long-term mean (1991-2020) 500 mb height -> small npz. Data: NOAA PSL (public domain).
usage: make_clim.py hgt.mon.ltm.1991-2020.nc out.npz   (needs h5py)"""
import sys, h5py, numpy as np
f = h5py.File(sys.argv[1]); i = list(f["level"][:]).index(500); v = f["hgt"]; a = v.attrs
g = lambda k, d: float(np.ravel(a[k])[0]) if k in a else d
h = v[:, i, :, :].astype("f4") * g("scale_factor", 1.0) + g("add_offset", 0.0)
np.savez_compressed(sys.argv[2], hgt=h, lat=f["lat"][:], lon=f["lon"][:])
