#!/usr/bin/env python3
"""NCEP/NCAR Reanalysis 1 6-hourly long-term mean (1991-2020) 2 m air temperature -> small npz for the 2 m anomaly maps.
Data: NOAA PSL (public domain). Each 6-hourly slot (00/06/12/18Z) is smoothed with a 15-day circular running mean so the
day-to-day noise of a 30-year sample does not show up as anomaly. Cropped to the Northern Hemisphere 150E-0E (all views).
Also stores the reanalysis surface height so the anomaly maps can move the climatology to model terrain.
usage: make_clim_t2m.py air.2m.gauss.4Xday.ltm.1991-2020.nc hgt.sfc.gauss.nc out.npz   (needs h5py)"""
import sys, h5py, numpy as np
from scipy.ndimage import uniform_filter1d
f, g = h5py.File(sys.argv[1]), h5py.File(sys.argv[2])
lat, lon = f["lat"][:], f["lon"][:]
la = (lat >= -2) & (lat <= 90); lo = lon >= 148
t = f["air"][:, la, :][:, :, lo].astype("f4")                    # (1460, ny, nx) K, slot = (day-1)*4 + hour/6
t = t.reshape(365, 4, *t.shape[1:])
t = uniform_filter1d(t, 15, axis=0, mode="wrap")                 # 15-day running mean per hour slot
z = g["hgt"][0][la, :][:, lo].astype("f4")
np.savez_compressed(sys.argv[3], t2m=(t - 273.15).astype("f2").reshape(1460, *t.shape[2:]), zs=z, lat=lat[la], lon=lon[lo])
print("ok", sys.argv[3], t.shape)
