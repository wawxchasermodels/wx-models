"""1991-2020 monthly precipitation normals (mm/day) for the fast preview's precip anomaly maps.
Blend (finest wins, feathered edges): PRISM 4 km normals (US, terrain-aware) > CPC Global Unified gauge 0.5 deg (land)
> GPCP v2.3 2.5 deg (land + ocean). Output grid 0.125 deg, 10-80N, 160E-20W -> ../precip_mon_ltm_1991_2020.npz (key "pr")."""
import numpy as np, glob, h5py, tifffile, calendar
from scipy.io import netcdf_file
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import gaussian_filter, distance_transform_edt
d = 0.125; lat = np.arange(80, 10 - d / 2, -d); lon = np.arange(160, 340 + d / 2, d)
LA, LO = np.meshgrid(lat, lon, indexing="ij"); pts = np.stack([LA, LO], -1)
def interp(la, lo, f):   # la ascending, lo 0..360 ascending; f (la, lo)
    return RegularGridInterpolator((la, lo), f, bounds_error=False, fill_value=np.nan)(pts)
# GPCP (HDF5 / netCDF4), mm/day, monthly
g = h5py.File("gpcp_precip_mon_ltm_1991-2020.nc"); gl, go, gp = g["lat"][:], g["lon"][:], g["precip"][:].astype(float)
gp[gp < -1e3] = np.nan
o = np.argsort(gl); gl, gp = gl[o], gp[:, o]
gpw = np.concatenate([gp, gp[:, :, :1]], 2); gow = np.append(go, go[0] + 360)
# CPC daily ltm (mm/day) -> months (non-leap 365 days)
c = netcdf_file("cpc_precip_day_ltm_1991-2020.nc", "r", mmap=False); cl, co = c.variables["lat"][:].copy(), c.variables["lon"][:].copy()
cp = c.variables["precip"][:].astype(np.float32); cp[cp < -1e3] = np.nan
mdays = np.cumsum([0] + [calendar.monthrange(2001, k)[1] for k in range(1, 13)])
cpm = np.stack([np.nanmean(cp[mdays[k]:mdays[k + 1]], 0) if True else 0 for k in range(12)]); del cp
o = np.argsort(cl); cl, cpm = cl[o], cpm[:, o]
# PRISM monthly totals (mm/month) on 1/24 deg -> mm/day, block-mean to 1/8 deg
out = np.zeros((12,) + LA.shape, np.float32)
for k in range(12):
    base = interp(gl, gow, gpw[k])
    cpc = interp(cl, co, cpm[k])
    v = np.where(np.isfinite(cpc), cpc, base)
    # feather CPC into GPCP over ~1 deg at coasts
    m = np.isfinite(cpc).astype(float); w = np.clip(distance_transform_edt(m) / 8.0, 0, 1)
    v = w * np.nan_to_num(cpc) + (1 - w) * base
    a = tifffile.imread(glob.glob(f"prism/prism_ppt_us_25m_2020{k + 1:02d}_avg_30y.tif")[0]).astype(float); a[a < -9000] = np.nan
    a = a / calendar.monthrange(2001, k + 1)[1]
    ny, nx = a.shape; a = a[: ny // 3 * 3, : nx // 3 * 3].reshape(ny // 3, 3, nx // 3, 3)
    with np.errstate(all="ignore"): a = np.nanmean(np.nanmean(a, 3), 1)
    pla = 49.9375 + 1 / 48 - (np.arange(a.shape[0]) + 0.5) * d; plo = -125.0208333 - 1 / 48 + (np.arange(a.shape[1]) + 0.5) * d + 360
    pr = interp(pla[::-1], plo, a[::-1])
    pm = np.isfinite(pr).astype(float); w = np.clip(distance_transform_edt(pm) / 8.0, 0, 1)
    v = w * np.nan_to_num(pr) + (1 - w) * v
    out[k] = np.clip(np.nan_to_num(v, nan=np.nanmean(v)), 0, None)
    print(k + 1, "mean", round(float(out[k].mean()), 2), "max", round(float(out[k].max()), 1), flush=True)
np.savez_compressed("../precip_mon_ltm_1991_2020.npz", pr=out.astype(np.float32), lat=lat, lon=lon,
                    zs=np.zeros(1), source=np.array("PRISM 1991-2020 normals (US) + CPC Global Unified Gauge 1991-2020 (land) + GPCP v2.3 1991-2020 (all)"))
