#!/usr/bin/env python3
"""Studio-only map views for the global models (Benjamin 10-31-26 7:49 PM: "city labels on the new washington wide are way too
big"; 7:50 PM: build a proper wide Washington basemap and town layer, and make the view a little tighter).

"Washington (wide, for loops)" (wawide) was the model's Pacific NW tight map (pnwt) blown up ~3.8x by the Studio camera, so its
town names / numbers came out ~50 px tall in a 1080 px frame. This builds a real view for it, drawn at the scale the Studio frames
show it: Washington ~600 x 380 figure px (like the HRRR wide view), with room above / below for the 9:16 frame. Same encoder code
as fast_encode.static (LUT, coast / border layer, towns placed by temp_maps.region_towns with "88" numbers, number slots).

Nothing in manifest.json changes (no new view in the site's View menus): the view entries go to static/studio_views.json, which
only the Studio page reads. New files only: static/studio_views.json, static/lut_<model>_wawide.bin, static/{,x2/}base_wawide.png,
static/{,x2/}towns_wawide.png. Global (0.25 / 0.1 deg lat-lon) models only; the grid is analytic, so no GRIB download is needed.
The data rows / cols come from the model's published crop (manifest), so every run already in R2 works with it.

  studio_views.py --manifest data/manifest.json --out D [--models gfs,ifs,ifs9,aifs,eps,aens]
"""
import os, sys, json, argparse, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE

VID = os.environ.get("STUDIO_VIEW", "wawide")
# 11-04 (Benjamin t2289u "Make me a coastal view for studio that is a little bigger and wider, centered over the ocean, land in the right
# third. Call it 'coast view'"): STUDIO_VIEW=coast builds "Coast view" (vid coast) the same way. Its camera boxes (lon0, lon1, lat0, lat1):
# COAST_H = the 16:9 frame (Washington's coast ~2/3 across, Seattle inside the right third), COAST_V = the 9:16 frame (coast ~2/3 across)
# 11-04 (t2300u "a little tighter, a bit less Oregon, make sure Westport gets in there"): tighter boxes, south edge just below the
# Columbia mouth; built as STUDIO_VIEW=coast_t (new R2 file names, the site's view id stays "coast")
# 11-04 (t2311u "now just shift the whole view about 30 miles south and it's perfect"): both boxes 0.43 deg (~48 km) south, same zoom;
# built as STUDIO_VIEW=coast_s
COAST_H = (-131.2, -120.1, 45.07, 49.27)
COAST_V = (-127.35, -120.05, 43.97, 51.17)
COAST = VID.startswith("coast")
STATE = COAST_H if COAST else (-124.85, -116.9, 45.54, 49.0)   # Washington's lon / lat box: the part the Studio camera fits in the frame ("fit")
GLOBAL = ("gfs", "ifs", "ifs9", "aifs", "eps", "aens")

def setup():
    import matplotlib; matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import house_style as HS, temp_maps as TM
    HS.use_for_plots(); FE.extra_views(TM, ccrs)
    # 13 x 17 in at 100 dpi: panel ~1238 x 1351 px, Washington ~599 x 379 px (HRRR wide view: 568 x 392). Tall, so a 9:16 frame
    # that fits the state's width still has map above and below it (41-53.6 N); 16:9 shows ~940 px of the 1238 px width.
    TM.VIEWS[VID] = dict(label="Washington (wide, for loops)", size=(13, 17),
                         proj=ccrs.LambertConformal(central_longitude=-120.6, central_latitude=47.3, standard_parallels=(45, 49)),
                         ll=(-128.5, -113.3, 41.0, 53.6), box=(-129.5, -112.0, 40.5, 54.2))
    # towns: the regional (population-tiered) placement like the HRRR wide view, a lower last tier (WA towns of 12k+) since
    # this frame is only ~1/3 of the Pacific NW tight one; names 9.5 / 8.5 / 8 pt as on every regional view
    TM.REGION_TOWNS[VID] = ((250000, 50000, 12000), 70)
    # + four eastern Washington towns from the site's Washington list (they fill the gaps east of the Cascades; this process
    # builds only this view, so the shared requested list is extended here only)
    TM.REGION_REQUESTED = tuple(TM.REGION_REQUESTED) + tuple(n for n in ("Ellensburg", "Moses Lake", "Pullman", "Colville") if n not in TM.REGION_REQUESTED)
    if COAST:
        # ~62 figure px per degree of longitude (wide view: ~81), Lambert centred on the ocean; the figure covers both camera boxes + room to pan
        TM.VIEWS[VID] = dict(label="Coast view", size=(14, 12.5),
                             proj=ccrs.LambertConformal(central_longitude=-126.0, central_latitude=46.3, standard_parallels=(44, 49)),
                             ll=(-134.0, -115.5, 43.3, 54.0), box=(-136.0, -113.5, 42.5, 55.0))
        TM.REGION_TOWNS[VID] = ((400000, 60000, 20000), 60)   # Victoria (~290k) after the coast towns, so Neah Bay keeps its spot
        # t2290u: the western Washington coast towns the site already has (Washington view list + the Western Washington view's coast towns)
        wwa = {t[0]: t for t in FE.EXTRA_TOWNS["wwa"]}; have = {t[0] for t in TM.WA_TOWNS}
        TM.WA_TOWNS = list(TM.WA_TOWNS) + [wwa[n] for n in ("Ocean Shores", "Westport", "Hoquiam", "Raymond") if n not in have]
        coast = ("Neah Bay", "Forks", "Port Angeles", "Ocean Shores", "Westport", "Aberdeen", "Hoquiam", "Raymond", "Long Beach", "Astoria", "Victoria")
        TM.REGION_REQUESTED = coast + tuple(n for n in TM.REGION_REQUESTED if n not in coast)
        # towns only where both frames can show their labels: west of 119.6 W (16:9 right edge 118.5 W) and between 42.9 N (9:16 key) and 49.3 N (F+ badge; Vancouver 49.28 N kept)
        rp = TM.region_places; TM.region_places = lambda vid: [t for t in rp(vid) if vid != VID or (t[2] <= -121.6 and 45.57 <= t[1] <= 49.3)]
    return TM, HS, ccrs

def build(models, man, out):
    import matplotlib.pyplot as plt
    import cartopy.feature as cf
    TM, HS, ccrs = setup(); pc = ccrs.PlateCarree(); V = TM.VIEWS[VID]
    os.makedirs(f"{out}/static/x2", exist_ok=True)
    def layer_fig():
        fig, ax, ky = TM.frame(VID); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    def save(fig, path):
        fig.savefig(path, dpi=FE.DPI, transparent=True); fig.savefig(path.replace("/static/", "/static/x2/"), dpi=FE.DPI * FE.X2, transparent=True)
        plt.close(fig); return os.path.getsize(path)
    # geometry (same as fast_encode.static)
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
    tr = pc._as_mpl_transform(ax)   # Washington's box in figure px (top-left origin): the Studio camera's "fit" rect
    sp = [tr.transform((lo, la)) for lo in np.linspace(STATE[0], STATE[1], 40) for la in STATE[2:]] + \
         [tr.transform((lo, la)) for lo in STATE[:2] for la in np.linspace(STATE[2], STATE[3], 40)]
    xs = [p[0] for p in sp]; ys = [H - p[1] for p in sp]
    fit = [float(min(xs)), float(min(ys)), float(max(xs) - min(xs)), float(max(ys) - min(ys))]
    fitV = None
    if COAST:
        B = COAST_V; sp = [tr.transform((lo, la)) for lo in np.linspace(B[0], B[1], 40) for la in B[2:]] + [tr.transform((lo, la)) for lo in B[:2] for la in np.linspace(B[2], B[3], 40)]
        xs = [p[0] for p in sp]; ys = [H - p[1] for p in sp]; fitV = [float(min(xs)), float(min(ys)), float(max(xs) - min(xs)), float(max(ys) - min(ys))]
    plt.close(fig)
    sizes = {}
    # fixed layers, shared by every model (same frame): coast / borders / frame, then towns (built with the first model's grid)
    fig, ax, ky = layer_fig(); HS.outlines(ax, cf, res="10m"); HS.frame(ax)
    nt = len(fig.texts); HS.header(fig, "X", "X", "X", "X", "X")
    for t in fig.texts[nt:]: t.set_visible(False)
    sizes["base"] = save(fig, f"{out}/static/base_{VID}.png")
    entries = {}; towns_png = False
    for m in models:
        MD = FE.MODELS[m]; assert MD["grid"] == "ll", m
        if m not in man.get("models", {}): print(f"{m}: not in manifest, skipped", flush=True); continue
        i0, i1, j0, j1 = man["models"][m]["crop"]; rs_ = MD.get("res", 0.25)
        fi, fj = (90.0 - LA_) / rs_, np.mod(LO_, 360.0) / rs_
        if not (fi.min() >= i0 and fi.max() <= i1 - 1 and fj.min() >= j0 and fj.max() <= j1 - 1):
            print(f"{m}: view not inside the published crop {[i0, i1, j0, j1]} (rows {fi.min():.1f}-{fi.max():.1f}, cols {fj.min():.1f}-{fj.max():.1f}); skipped", flush=True); continue
        np.stack([fi - i0, fj - j0, ang], -1).astype("<f4").tofile(f"{out}/static/lut_{m}_{VID}.bin")
        crop_la = 90.0 - np.arange(i0, i1) * rs_; crop_lo = np.mod(np.arange(j0, j1) * rs_, 360.0)
        bx = V["box"]; rr = np.where((crop_la >= bx[2]) & (crop_la <= bx[3]))[0]; cc = np.where((crop_lo >= bx[0] % 360) & (crop_lo <= bx[1] % 360))[0]
        cut = [int(rr.min()), int(rr.max() + 1), int(cc.min()), int(cc.max() + 1)]
        fig, slots = town_slots(TM, VID, layer_fig, i0, i1, j0, j1, rs_)
        if not towns_png:
            labs = getattr(fig, "_wx_labels", None)
            sizes["towns"] = save(fig, f"{out}/static/towns_{VID}.png"); towns_png = [s["name"] for s in slots]
            if labs: FE.write_town_labels(f"{out}/static/labels_{VID}.json", labs)
        else:
            plt.close(fig)
            if [s["name"] for s in slots] != towns_png: raise SystemExit(f"{m}: town placement differs from the shared towns layer")
        entries[m] = dict(label=V["label"], fig=[int(round(W)), int(round(H))], size_in=[float(x) for x in V["size"]], panel=[px, py, pw, ph],
                          stride=FE.STRIDE, nx=nx, ny=ny, barbs_across=20, lut=f"static/lut_{m}_{VID}.bin", cut=cut, towns=slots,
                          fit=fit, studioOnly=True, studioWide="wa", keysFrom="wa")
        if fitV: entries[m].update(fitV=fitV, studioCoast=True)
        print(f"{m} {VID}: {len(slots)} town numbers, cut {cut}", flush=True)
    sp = f"{out}/static/studio_views.json"; old = json.load(open(sp)).get("models", {}) if os.path.exists(sp) else {}   # other models kept
    for m, e in entries.items(): old.setdefault(m, {})[VID] = e
    for m, src in (("aensm", "aens"), ("epsm", "aens"), ("oisst", "gfs")):   # same 0.25 grid / crop as their source model (as the wide view)
        if src in entries and m in man.get("models", {}) and man["models"][m]["crop"] == man["models"][src]["crop"]: old.setdefault(m, {})[VID] = entries[src]
    doc = dict(built=time.strftime("%Y-%m-%dT%H:%M:%S%z"), v=time.strftime("%Y%m%d%H%M%S"),
               note="Studio-only views (studio_views.py); not in manifest.json", models=old)
    json.dump(doc, open(sp, "w"), indent=1)
    print("sizes", sizes, "towns", towns_png, flush=True); return doc

def town_slots(TM, vid, layer_fig, i0, i1, j0, j1, rs_, passes=False):
    """Town names + number slots for a view on a lat/lon model crop (same code as fast_encode.static): the site's own placement
    (temp_maps.towns) with "88" numbers; each number reads the grid point found by sampling lat and lon grids at the pins.
    Returns (figure with the names / dots, numbers hidden: the town layer), slots."""
    import numpy as np, matplotlib.pyplot as plt
    crop_la = 90.0 - np.arange(i0, i1) * rs_; crop_lo = np.mod(np.arange(j0, j1) * rs_, 360.0)
    wcols = np.where(crop_lo >= 180)[0]; tw_lo1 = crop_lo[wcols] - 360; tw_la1 = crop_la
    tw_la, tw_lo = np.meshgrid(tw_la1, tw_lo1, indexing="ij")
    f88 = lambda v: None if not np.isfinite(v) else "88"
    fig, ax, ky = layer_fig(); arts = TM.towns(ax, vid, (tw_la1, tw_lo1, tw_la), f88) or []
    if passes: add_passes(TM, ax, arts, (tw_la1, tw_lo1, tw_la))
    tv_la = dict(getattr(ax, "town_values", {}) or {})
    fig2, ax2, _ = layer_fig(); TM.towns(ax2, vid, (tw_la1, tw_lo1, tw_lo), f88); tv_lo = dict(getattr(ax2, "town_values", {}) or {}); plt.close(fig2)
    fig.canvas.draw(); r = fig.canvas.get_renderer(); Wd, Hd = fig.get_size_inches() * fig.dpi; slots = []; last = None
    for t in arts:
        if t.get_text() != "88": last = t.get_text(); continue
        if not t.get_visible() or last not in tv_la: continue
        pla, plo = tv_la[last], tv_lo.get(last)
        if plo is None or not (np.isfinite(pla) and np.isfinite(plo)): continue
        bb = t.get_window_extent(r)
        slots.append(dict(name=last, kind="town", x=bb.x0 / Wd, y=1 - (bb.y0 + bb.y1) / 2 / Hd, fi=float((90.0 - pla) / rs_ - i0),
                          fj=float(np.mod(plo, 360.0) / rs_ - j0), size=t.get_fontsize(), color=t.get_color()))
        t.set_visible(False)
    fig._wx_labels = FE.label_items(fig, ax)
    return fig, slots

# 11-02 (Benjamin t2105u "Passes need to be added to maps on Washington wide for loops"): the Washington view's mountain passes
# (temp_maps.WA_PASSES: Snoqualmie, Stevens, White, Chinook, Blewett, Sherman, Satus, Wauconda, Disautel; the 10-25 list without
# Washington / Loup Loup / Cayuse) drawn on the wide view's town layer the same way as on the Washington view: small plum triangle +
# italic name (temp_maps.pass_labels), names only (no numbers: keeps the loop frames uncluttered). Placed after the towns, clear of
# every town name, number slot and dot; a name that does not fit is dropped (its triangle stays). Town placement is unchanged.
# New file names only (static/{,x2/}towns_wawide_p1.png); the site points the wawide view at it (production keeps towns_wawide.png).
PASS_PNG = "static/towns_wawide_p1.png"
def add_passes(TM, ax, arts, field):
    import matplotlib
    fig = ax.figure; fig.canvas.draw(); r = fig.canvas.get_renderer(); pt = 72.0 / fig.dpi; axbb = ax.get_window_extent(r)
    taken = [a.get_window_extent(r) for a in arts if a.get_visible()]
    for ln in ax.lines:   # town dots
        for x, y in ln.get_transform().transform(ln.get_xydata()): taken.append(matplotlib.transforms.Bbox([[x - 4, y - 4], [x + 4, y + 4]]))
    keep = TM.WA_TOWNS; TM.WA_TOWNS = []   # pass_labels also blocks the Washington view's town dots; here the real dots are in taken
    try: p_arts = TM.pass_labels(ax, field, lambda v: None, taken, r, pt, axbb)
    finally: TM.WA_TOWNS = keep
    print("passes:", [a.get_text() for a in p_arts], flush=True)

def passes_layer(models, man, out):
    import matplotlib.pyplot as plt
    TM, HS, ccrs = setup(); os.makedirs(f"{out}/static/x2", exist_ok=True)
    def layer_fig():
        fig, ax, ky = TM.frame(VID); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    m = models[0]; i0, i1, j0, j1 = man["models"][m]["crop"]
    fig0, slots0 = town_slots(TM, VID, layer_fig, i0, i1, j0, j1, FE.MODELS[m].get("res", 0.25)); plt.close(fig0)
    fig, slots = town_slots(TM, VID, layer_fig, i0, i1, j0, j1, FE.MODELS[m].get("res", 0.25), passes=True)
    assert slots == slots0, "town slots changed"
    fig.savefig(f"{out}/{PASS_PNG}", dpi=FE.DPI, transparent=True); fig.savefig(f"{out}/{PASS_PNG}".replace("/static/", "/static/x2/"), dpi=FE.DPI * FE.X2, transparent=True)
    plt.close(fig); json.dump(slots, open(f"{out}/slots_{m}.json", "w")); print("wrote", PASS_PNG, len(slots), "town slots", flush=True)

# 10-31 8:17 PM (Benjamin: "Fix the pacific nw tight view"): static/towns_pnwt.png (built 10-30 by an older town list, kept since the
# encoder only writes a missing layer) no longer matched the number slots in the manifest, so numbers sat on other towns' names.
# Rebuilt here with the current code into NEW versioned files (production's towns_pnwt.png is left as is): static/{,x2/}towns_pnwt_v2.png
# and static/view_fixes.json {models: {m: {pnwt: {towns, towns_png}}}}; the site overlays these on the manifest's pnwt entries.
FIX_VID, FIX_PNG = "pnwt", "static/towns_pnwt_v2.png"
def pnwt_fix(models, man, out):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt, cartopy.crs as ccrs
    import house_style as HS, temp_maps as TM
    HS.use_for_plots(); FE.extra_views(TM, ccrs)
    os.makedirs(f"{out}/static/x2", exist_ok=True)
    def layer_fig():
        fig, ax, ky = TM.frame(FIX_VID); fig.set_dpi(FE.DPI); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    fp = f"{out}/static/view_fixes.json"; doc = json.load(open(fp)) if os.path.exists(fp) else {"models": {}}
    names0 = None
    for m in models:
        MD = FE.MODELS[m]
        if m not in man.get("models", {}) or FIX_VID not in man["models"][m]["views"]: print(f"{m}: no {FIX_VID} view, skipped", flush=True); continue
        i0, i1, j0, j1 = man["models"][m]["crop"]
        fig, slots = town_slots(TM, FIX_VID, layer_fig, i0, i1, j0, j1, MD.get("res", 0.25))
        names = [s_["name"] for s_ in slots]
        if names0 is None:
            labs = getattr(fig, "_wx_labels", None)
            fig.savefig(f"{out}/{FIX_PNG}", dpi=FE.DPI, transparent=True); fig.savefig(f"{out}/{FIX_PNG}".replace("/static/", "/static/x2/"), dpi=FE.DPI * FE.X2, transparent=True)
            if labs: FE.write_town_labels(f"{out}/" + FIX_PNG.replace("towns_", "labels_").replace(".png", ".json"), labs)
            names0 = names
        elif names != names0: raise SystemExit(f"{m}: town placement differs from the shared towns layer")
        plt.close(fig)
        doc["models"].setdefault(m, {})[FIX_VID] = dict(towns=slots, towns_png=FIX_PNG)
        print(f"{m} {FIX_VID}: {len(slots)} town numbers", flush=True)
    doc.update(built=time.strftime("%Y-%m-%dT%H:%M:%S%z"), note="per-view overrides the site lays over manifest.json (studio_views.py pnwt_fix)")
    json.dump(doc, open(fp, "w"), indent=1); print("towns", names0, flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--manifest", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=",".join(GLOBAL)); ap.add_argument("--pnwt-fix", action="store_true"); ap.add_argument("--passes", action="store_true"); a = ap.parse_args()
    (pnwt_fix if a.pnwt_fix else passes_layer if a.passes else build)(a.models.split(","), json.load(open(a.manifest)), a.out)
