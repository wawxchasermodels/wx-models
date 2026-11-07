#!/usr/bin/env python3
"""Wave-only map views for the ECMWF wave products (Benjamin 11-01-26 t1999u: "Make me a new view, just for waves right now, titled
west coast. Make sure shore acres is on there, and other major locations on the California coast or buoys"; t2000u: "Can expand that
map west to be more wide and show more of the ocean if that would be better, but as tall as the screenshot").

"West Coast" (wc): Mercator, Vancouver Island / Washington down to San Diego (31.8-49.8 N), widened west over the Pacific (to 152 W) so
the offshore buoys (46006, 46005, 46002, 46059, 46036) fit. Same encoder geometry as fast_encode.static / studio_views.build (LUT,
coast / border layer); no town layer (the viewer draws the coast labels and buoys itself on wave maps), color keys for waves /
wavemax / wavemax24 drawn from the manifest's current product tables (products_v over products).

manifest.json is NOT changed: the view entry goes to static/wave_views.json, which viewer.js (v=20261101p+) merges as a wave-only view.
New files: static/wave_views.json, static/lut_ifs_wc.bin, static/{,x2/}base_wc.png, static/{,x2/}towns_wc.png (empty),
static/{,x2/}key_ifs_<pid>_wc_<ver>.png.
  wave_views.py --manifest data/manifest.json --out D
"""
import os, sys, json, argparse, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE

VID, M_ = "wc", "ifs"
PIDS = ("waves", "wavemax", "wavemax24")

def setup():
    import matplotlib; matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import house_style as HS, temp_maps as TM
    HS.use_for_plots(); FE.extra_views(TM, ccrs)
    TM.VIEWS[VID] = dict(label="West Coast", size=(16, 10.5), proj=ccrs.Mercator(central_longitude=-134),
                         ll=(-152.0, -116.0, 31.8, 49.8), box=(-155.0, -113.0, 30.0, 51.5))
    return TM, HS, ccrs

def build(man, out, ver):
    import matplotlib.pyplot as plt
    import cartopy.feature as cf
    from matplotlib.colors import ListedColormap, BoundaryNorm
    import menu_maps as M
    TM, HS, ccrs = setup(); pc = ccrs.PlateCarree(); V = TM.VIEWS[VID]
    os.makedirs(f"{out}/static/x2", exist_ok=True)
    def layer_fig():
        fig, ax, ky = TM.frame(VID); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    def save(fig, path):
        fig.savefig(path, dpi=FE.DPI, transparent=True); fig.savefig(path.replace("/static/", "/static/x2/"), dpi=FE.DPI * FE.X2, transparent=True)
        plt.close(fig); return os.path.getsize(path)
    fig, ax, ky = TM.frame(VID); fig.set_dpi(FE.DPI); ax.apply_aspect(); fig.canvas.draw()
    W, H = fig.get_size_inches() * FE.DPI; b = ax.get_position()
    px, py, pw, ph = b.x0 * W, (1 - b.y1) * H, b.width * W, b.height * H
    x0, x1, y0, y1 = ax.get_extent(V["proj"])
    nx, ny = int(np.ceil(pw / FE.STRIDE)) + 1, int(np.ceil(ph / FE.STRIDE)) + 1
    gxp = np.arange(nx) * FE.STRIDE; gyp = np.arange(ny) * FE.STRIDE
    PX = x0 + (gxp[None, :] / pw) * (x1 - x0) + 0 * gyp[:, None]; PY = y1 - (gyp[:, None] / ph) * (y1 - y0) + 0 * gxp[None, :]
    ll = pc.transform_points(V["proj"], PX, PY); LO_, LA_ = ll[..., 0], ll[..., 1]
    n2 = V["proj"].transform_points(pc, LO_, np.minimum(LA_ + 0.05, 89.9))
    ang = np.arctan2(-(n2[..., 1] - PY) / (y1 - y0) * ph, (n2[..., 0] - PX) / (x1 - x0) * pw)
    plt.close(fig)
    MI = man["models"][M_]; i0, i1, j0, j1 = MI["crop"]; rs_ = FE.MODELS[M_].get("res", 0.25)
    fi, fj = (90.0 - LA_) / rs_, np.mod(LO_, 360.0) / rs_
    assert fi.min() >= i0 and fi.max() <= i1 - 1 and fj.min() >= j0 and fj.max() <= j1 - 1, "view not inside the published crop"
    np.stack([fi - i0, fj - j0, ang], -1).astype("<f4").tofile(f"{out}/static/lut_{M_}_{VID}.bin")
    crop_la = 90.0 - np.arange(i0, i1) * rs_; crop_lo = np.mod(np.arange(j0, j1) * rs_, 360.0)
    bx = V["box"]; rr = np.where((crop_la >= bx[2]) & (crop_la <= bx[3]))[0]; cc = np.where((crop_lo >= bx[0] % 360) & (crop_lo <= bx[1] % 360))[0]
    cut = [int(rr.min()), int(rr.max() + 1), int(cc.min()), int(cc.max() + 1)]
    sizes = {}
    fig, ax, ky = layer_fig(); HS.outlines(ax, cf, res="50m"); HS.frame(ax)
    nt = len(fig.texts); HS.header(fig, "X", "X", "X", "X", "X")
    for t in fig.texts[nt:]: t.set_visible(False)
    sizes["base"] = save(fig, f"{out}/static/base_{VID}.png")
    fig, ax, ky = layer_fig(); sizes["towns"] = save(fig, f"{out}/static/towns_{VID}.png")   # empty: wave maps draw their own labels
    allP = {}; [allP.update(MI.get(k) or {}) for k in ("products", "products_x", "products_p", "products_n", "products_t", "products_v")]
    keys = {}
    for pid in PIDS:
        P = allP[pid]; L = np.asarray(P["levels"], float); kw = P.get("kw"); tkd = list(P["ticks"])
        cm = ListedColormap(P["colors"]);
        if P.get("under"): cm.set_under(P["under"])
        if P.get("over"): cm.set_over(P["over"])
        if kw: Ld = np.concatenate([[0.0], np.cumsum(kw)]); tkd = [float(np.interp(t, L, Ld)) for t in P["ticks"]]; L = Ld
        fig, ax, ky = layer_fig(); xa, xb, ya, yb = ax.get_extent(V["proj"]); X, Y = np.meshgrid([xa, xb], [ya, yb])
        ext = "both" if P.get("under") and P.get("over") else "max" if P.get("over") else "min" if P.get("under") else "neither"
        cs = ax.contourf(X, Y, np.full((2, 2), np.nan), levels=L, cmap=cm, norm=BoundaryNorm(L, cm.N), extend=ext, transform=ax.projection); cs.set_visible(False)
        cb = HS.hbar(fig, cs, [], P["key"], ky, **({"spacing": "proportional"} if kw else {})); cb.set_ticks(tkd)
        cb.ax.set_xticklabels([f"{t:g}" for t in P["ticks"]], fontproperties=HS.font(700, 13))
        HS.credit(fig, M.credit(M_))
        fn = f"static/key_{M_}_{pid}_{VID}_{ver}.png"; sizes[fn] = save(fig, f"{out}/{fn}"); keys[pid] = fn
    entry = dict(label=V["label"], fig=[int(round(W)), int(round(H))], size_in=[float(x) for x in V["size"]], panel=[px, py, pw, ph],
                 stride=FE.STRIDE, nx=nx, ny=ny, barbs_across=20, lut=f"static/lut_{M_}_{VID}.bin", cut=cut, towns=[],
                 towns_png=f"static/towns_{VID}.png", waveOnly=True, after="pnw", keys=keys)
    doc = dict(built=time.strftime("%Y-%m-%dT%H:%M:%S%z"), note="wave-only views (wave_views.py); not in manifest.json", models={M_: {VID: entry}})
    json.dump(doc, open(f"{out}/static/wave_views.json", "w"), indent=1)
    print("sizes", sizes, "cut", cut, "panel", [round(x) for x in (px, py, pw, ph)], flush=True); return doc

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--manifest", required=True); ap.add_argument("--out", required=True); ap.add_argument("--ver", default="v1")
    a = ap.parse_args(); build(json.load(open(a.manifest)), a.out, a.ver)
