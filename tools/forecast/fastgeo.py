"""Faster Cartopy drawing for every forecast map script (speed_build_v1). Import it once (house_style does) and it
patches GeoAxes.contour / contourf / barbs / quiver. Switch off with WX_FASTGEO=0.

Measured on the menu maps (same patterns as here): contourf with transform=PlateCarree() reprojects every color-band
polygon (20-45 s per map on 3 km / 0.1 deg grids); barbs/quiver with regrid_shape triangulate the whole grid with scipy
griddata (about 65 s per call). The patched versions give the same pictures (pixel diffs 0.00-0.05 %):
  - contour/contourf: the lon/lat grid is projected once per map view (cached), then contoured in map space
    (Cartopy's own transform_first idea). Line contours with one color skip levels outside the data range.
  - barbs/quiver with regrid_shape: same nx x ny target grid and the same linear (Delaunay) interpolation of the vectors
    rotated into the map projection, but each target point uses a 7x7 patch of the source grid around it.
"""
import os, numpy as np
import cartopy.crs as ccrs
from cartopy.mpl.geoaxes import GeoAxes

ON = os.environ.get("WX_FASTGEO", "1") != "0"
_XY = {}
_ORIG = {}


def _is_lonlat(t):
    return isinstance(t, ccrs.PlateCarree) and getattr(t, "proj4_params", {}).get("lon_0", 0) == 0


def proj_xy(proj, LO, LA):
    LO, LA = np.asarray(LO), np.asarray(LA)
    k = (id(proj), LO.shape, LA.shape, float(LO.flat[0]), float(LO.flat[-1]), float(LA.flat[0]), float(LA.flat[-1]))
    if k not in _XY:
        lo2, la2 = (LO, LA) if LO.ndim == 2 else np.meshgrid(LO, LA)
        P = proj.transform_points(ccrs.PlateCarree(), lo2.astype(float), la2.astype(float)); X, Y = P[..., 0], P[..., 1]
        bad = ~np.isfinite(X) | ~np.isfinite(Y)
        if bad.any(): X, Y = np.where(bad, np.nanmax(X), X), np.where(bad, np.nanmax(Y), Y)
        _XY[k] = (X, Y)
    return _XY[k]


def thin_vectors(ax, LO, LA, U, V, nx, ny):
    from scipy.spatial import Delaunay, cKDTree
    proj, pc = ax.projection, ccrs.PlateCarree(); x0, x1, y0, y1 = ax.get_extent(proj); xr, yr = x1 - x0, y1 - y0
    gx, gy = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny)); XT, YT = gx * xr + x0, gy * yr + y0
    LO, LA = np.asarray(LO, float), np.asarray(LA, float); U, V = np.asarray(U, float), np.asarray(V, float)
    ll = pc.transform_points(proj, XT, YT); tlo, tla = ll[..., 0].ravel(), ll[..., 1].ravel()
    if LO.ndim == 1:
        lon_ref = tlo % 360 if LO.max() > 180 else tlo
        jc = np.clip(np.searchsorted(LO, lon_ref), 0, LO.size - 1); ic = np.abs(LA[None, :] - tla[:, None]).argmin(1)
        shp = (LA.size, LO.size); lo_of = lambda ii, jj: LO[jj]; la_of = lambda ii, jj: LA[ii]
    else:
        kk = ("kd", LO.shape, float(LO.flat[0]), float(LA.flat[0]))
        if kk not in _XY: _XY[kk] = cKDTree(np.column_stack([LO.ravel(), LA.ravel()]))
        _, n = _XY[kk].query(np.column_stack([tlo, tla])); ic, jc = np.unravel_index(n, LO.shape)
        shp = LO.shape; lo_of = lambda ii, jj: LO[ii, jj]; la_of = lambda ii, jj: LA[ii, jj]
    uo = np.full(tlo.size, np.nan); vo = np.full(tlo.size, np.nan)
    for t in range(tlo.size):
        if not (np.isfinite(tlo[t]) and np.isfinite(tla[t])): continue
        ii, jj = np.meshgrid(np.arange(max(0, ic[t] - 3), min(shp[0], ic[t] + 4)), np.arange(max(0, jc[t] - 3), min(shp[1], jc[t] + 4)), indexing="ij")
        ii, jj = ii.ravel(), jj.ravel(); plo, pla = lo_of(ii, jj), la_of(ii, jj); pu, pv = U[ii, jj], V[ii, jj]
        P = proj.transform_points(pc, plo, pla); ok = np.isfinite(P[:, 0]) & np.isfinite(P[:, 1])
        if ok.sum() < 3: continue
        P, pu, pv, plo, pla = P[ok], pu[ok], pv[ok], plo[ok], pla[ok]; fin = np.isfinite(pu) & np.isfinite(pv)
        uu, vv = np.full(pu.shape, np.nan), np.full(pv.shape, np.nan)
        if fin.any(): uu[fin], vv[fin] = proj.transform_vectors(pc, plo[fin], pla[fin], pu[fin], pv[fin])
        pts = np.column_stack([(P[:, 0] - x0) / xr, (P[:, 1] - y0) / yr]); q = np.array([[gx.ravel()[t], gy.ravel()[t]]])
        try: tri = Delaunay(pts)
        except Exception: continue
        sx = int(tri.find_simplex(q)[0])
        if sx < 0: continue
        Tm = tri.transform[sx]; b = Tm[:2] @ (q[0] - Tm[2]); w = np.r_[b, 1 - b.sum()]; vx = tri.simplices[sx]
        uo[t], vo[t] = w @ uu[vx], w @ vv[vx]
    return XT, YT, uo.reshape(XT.shape), vo.reshape(XT.shape)


def _single_color(kw):
    c = kw.get("colors")
    if c is None: return False
    if isinstance(c, str): return True
    try: return len(c) in (3, 4) and all(isinstance(x, (int, float)) for x in c) or len(c) == 1
    except TypeError: return False


def _wrap(name):
    orig = _ORIG[name] = getattr(GeoAxes, name)

    def f(self, *args, **kw):
        t = kw.get("transform")
        if not ON or t is None or not _is_lonlat(t) or kw.get("transform_first") or len(args) < 3:
            return orig(self, *args, **kw)
        X, Y, Z = args[0], args[1], np.asarray(args[2]); rest = list(args[3:])
        if np.ndim(Z) != 2: return orig(self, *args, **kw)
        PX, PY = proj_xy(self.projection, X, Y)
        if PX.shape != Z.shape: return orig(self, *args, **kw)
        if name == "contour" and _single_color(kw) and np.isfinite(Z).any() and not isinstance(kw.get("linestyles"), (list, tuple)) \
                and not isinstance(kw.get("linewidths"), (list, tuple)):
            L = kw.get("levels", rest[0] if rest else None)
            if L is not None and np.ndim(L) == 1 and len(L) > 2:
                lo, hi = np.nanmin(Z), np.nanmax(Z); Lk = [l for l in L if lo <= l <= hi]
                if Lk:
                    if "levels" in kw: kw["levels"] = Lk
                    else: rest[0] = Lk
        kw["transform"] = self.projection
        return orig(self, PX, PY, Z, *rest, **kw)
    setattr(GeoAxes, name, f)


def _wrap_vec(name):
    orig = _ORIG[name] = getattr(GeoAxes, name)

    def f(self, *args, **kw):
        t = kw.get("transform"); rs = kw.get("regrid_shape")
        if not ON or rs is None or t is None or not _is_lonlat(t) or len(args) != 4 or kw.get("target_extent") is not None:
            return orig(self, *args, **kw)
        nx, ny = (rs, rs) if np.isscalar(rs) else rs
        kw.pop("regrid_shape"); kw["transform"] = self.projection
        X, Y, u, v = thin_vectors(self, args[0], args[1], args[2], args[3], int(nx), int(ny))
        return orig(self, X, Y, u, v, **kw)
    setattr(GeoAxes, name, f)


def install():
    if _ORIG or not ON: return
    for n in ("contour", "contourf"): _wrap(n)
    for n in ("barbs", "quiver"): _wrap_vec(n)


install()
