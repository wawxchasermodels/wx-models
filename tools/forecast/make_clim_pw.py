"""Build the precipitable-water normal used by the PW Anomaly maps.

usage: make_clim_pw.py pr_wtr.eatm.day.ltm.1991-2020.nc hgt.sfc.gauss.nc out.npz   (needs h5py)
Source: NCEP/NCAR Reanalysis 1991-2020 daily long-term mean PW (NOAA PSL, public domain), 2.5 deg grid,
smoothed with a 15-day running mean, cropped to North America. Reanalysis terrain height is stored too so the
maps can move the normal to each model's terrain (water-vapor scale height 2.3 km)."""
import sys, numpy as np, h5py

f = h5py.File(sys.argv[1]); lat, lon = f["lat"][:], f["lon"][:]
la = (lat >= 10) & (lat <= 82); lo = (lon >= 170) & (lon <= 330)
pw = f["pr_wtr"][:][:, la, :][:, :, lo].astype("f4")
k = 7; pad = np.concatenate([pw[-k:], pw, pw[:k]]); cs = np.cumsum(pad, 0, dtype="f8")
cs = np.concatenate([np.zeros((1,) + pw.shape[1:]), cs]); pw = ((cs[2 * k + 1:] - cs[:-2 * k - 1]) / (2 * k + 1)).astype("f4")
g = h5py.File(sys.argv[2]); gl, go = g["lat"][:], g["lon"][:]
gla = (gl >= 5) & (gl <= 87); glo = (go >= 165) & (go <= 335)
zs = g["hgt"][0][gla, :][:, glo].astype("f4")
np.savez_compressed(sys.argv[3], pw=pw.astype("f2"), lat=lat[la], lon=lon[lo], zs=zs, zlat=gl[gla], zlon=go[glo])
print(pw.shape, zs.shape, float(pw.min()), float(pw.max()))
