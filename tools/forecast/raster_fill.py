"""Prototype (speed_build_v1, part 2): color fills drawn as a raster instead of contourf polygons. OFF unless MENU_RASTERFILL=1.

How it works: for each map view and model grid, work out ONCE which model grid points (and with what weights) sit under
every output pixel of the map panel (bilinear for regular lon/lat grids, triangle weights for the 3 km Lambert grids).
After that, a frame's fill is just: pixel value = weighted sum of 3-4 grid values, then a color lookup table with the exact
same bins and colors as the color key. The result is pasted into the matplotlib map with imshow, so coastlines, contours,
barbs, labels, header and key are drawn exactly as before.
"""
import os, hashlib, numpy as np
import cartopy.crs as ccrs
from matplotlib.colors import BoundaryNorm, to_rgba_array

_W = {}
SS = int(os.environ.get("MENU_RASTER_SS", "1"))   # supersampling (2 = 2x2 samples per pixel, smoother band edges, 4x the work)


def _panel_px(ax):
    ax.apply_aspect(); fig = ax.figure; b = ax.get_position(); W, H = fig.get_size_inches() * fig.dpi
    return max(2, int(round(b.width * W))) * SS, max(2, int(round(b.height * H))) * SS


def weights(ax, LO, LA, xy):
    """(index array k x N, weight array k x N, shape) for the panel pixels; cached in memory and on disk per view + grid."""
    nx, ny = _panel_px(ax); proj = ax.projection; x0, x1, y0, y1 = ax.get_extent(proj)
    LO, LA = np.asarray(LO, float), np.asarray(LA, float)
    key = (id(proj), LO.shape, float(LO.flat[0]), float(LO.flat[-1]), float(LA.flat[0]), float(LA.flat[-1]), nx, ny)
    if key in _W: return _W[key]
    d = os.path.join(os.environ.get("WX_CACHE", os.path.expanduser("~/.cache/wx-models")), "raster_w"); os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, hashlib.sha1(repr((proj.proj4_init, key[1:], (x0, x1, y0, y1))).encode()).hexdigest() + ".npz")
    if os.path.exists(fn):
        z = np.load(fn); _W[key] = (z["i"], z["w"], (ny, nx)); return _W[key]
    px = x0 + (np.arange(nx) + 0.5) / nx * (x1 - x0); py = y1 - (np.arange(ny) + 0.5) / ny * (y1 - y0)   # top row first
    PX, PY = np.meshgrid(px, py)
    if LO.ndim == 1:   # regular lon/lat: bilinear from fractional row/column
        ll = ccrs.PlateCarree().transform_points(proj, PX, PY); lo, la = ll[..., 0].ravel(), ll[..., 1].ravel()
        if LO.max() > 180: lo = lo % 360
        fj = np.interp(lo, LO, np.arange(LO.size), left=np.nan, right=np.nan)
        asc = LA[-1] > LA[0]; LAa = LA if asc else LA[::-1]
        fi = np.interp(la, LAa, np.arange(LA.size), left=np.nan, right=np.nan)
        if not asc: fi = (LA.size - 1) - fi
        bad = ~np.isfinite(fi) | ~np.isfinite(fj); fi, fj = np.nan_to_num(fi), np.nan_to_num(fj)
        i0 = np.clip(np.floor(fi).astype(int), 0, LA.size - 2); j0 = np.clip(np.floor(fj).astype(int), 0, LO.size - 2)
        di, dj = fi - i0, fj - j0; n = LO.size
        I = np.stack([i0 * n + j0, i0 * n + j0 + 1, (i0 + 1) * n + j0, (i0 + 1) * n + j0 + 1])
        Wt = np.stack([(1 - di) * (1 - dj), (1 - di) * dj, di * (1 - dj), di * dj])
    else:              # 2-D grid: Delaunay of the grid points in map space, then barycentric weights (once per view)
        from scipy.spatial import Delaunay
        X, Y = xy; pts = np.column_stack([X.ravel(), Y.ravel()]); tri = Delaunay(pts)
        q = np.column_stack([PX.ravel(), PY.ravel()]); s = tri.find_simplex(q); bad = s < 0; s = np.where(bad, 0, s)
        T = tri.transform[s]; b = np.einsum("nij,nj->ni", T[:, :2], q - T[:, 2])
        I = tri.simplices[s].T; Wt = np.vstack([b.T, 1 - b.sum(1)])
    Wt = np.where(bad[None, :], np.nan, Wt).astype(np.float32); I = I.astype(np.int32)
    np.savez(fn, i=I, w=Wt); _W[key] = (I, Wt, (ny, nx)); return _W[key]


def lut(L, cm, ext):
    """Colors per bin exactly as contourf + BoundaryNorm pick them (under/over colors only where extend asks for them)."""
    norm = BoundaryNorm(L, cm.N); nb = len(L) - 1
    mids = (np.asarray(L[:-1], float) + np.asarray(L[1:], float)) / 2
    cols = cm(norm(mids)); under = cm(norm(L[0] - 1e9)) if ext in ("min", "both") else (0, 0, 0, 0)
    over = cm(norm(L[-1] + 1e9)) if ext in ("max", "both") else (0, 0, 0, 0)
    return np.vstack([to_rgba_array(under), cols, to_rgba_array(over)]), nb


def raster(ax, LO, LA, F, L, cm, ext, xy):
    I, Wt, shp = weights(ax, LO, LA, xy)
    v = np.asarray(F, float).ravel()[I]; val = np.einsum("kn,kn->n", Wt, v)   # NaN corner or outside -> NaN
    tab, nb = lut(L, cm, ext)
    k = np.searchsorted(np.asarray(L, float), val, side="right")   # 0 = under, 1..nb = bins, nb+1 = over
    k = np.where(val == L[-1], nb, k)   # top edge belongs to the last bin (like contourf)
    rgba = tab[np.clip(k, 0, nb + 1)]; rgba[~np.isfinite(val)] = 0
    return (rgba.reshape(shp + (4,)) * 255).astype(np.uint8)


def fill(ax, LO, LA, F, L, cm, ext, z, xy):
    img = raster(ax, LO, LA, F, L, cm, ext, xy); x0, x1, y0, y1 = ax.get_extent(ax.projection)
    ax.imshow(img, extent=(x0, x1, y0, y1), origin="upper", transform=ax.projection, zorder=z, interpolation="antialiased" if SS > 1 else "nearest",
              resample=False)
    # an invisible 2x2 contourf carries the levels / colors / extend arrows for the color key, exactly like before
    X, Y = np.meshgrid([x0, x1], [y0, y1]); cs = ax.contourf(X, Y, np.full((2, 2), np.nan), levels=L, cmap=cm, norm=BoundaryNorm(L, cm.N),
                                                             extend=ext, transform=ax.projection, zorder=z)
    cs.set_visible(False); return cs
