#!/usr/bin/env python3
"""Write the viewer's town-label JSON from the same placement the static generator uses.

fast_encode.static records these beside each towns PNG (static/labels_<view>.json). This
script rebuilds that JSON without a model grid: a synthetic field keeps every in-frame
town's "88" number, so collision matches a grid that covers the view. The live value is
not stored. Raster towns PNGs stay the fallback when a file is missing.

  export_town_labels.py [--site tools/fast/site]
"""
import os, sys, argparse, types
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
# temp_maps imports eccodes at load; label placement never reads a GRIB. A stub is enough when the library is absent.
try: import eccodes  # noqa: F401
except ModuleNotFoundError: sys.modules["eccodes"] = types.ModuleType("eccodes")
import fast_encode as FE

VIEWS = ("wa", "wwa", "ewa", "puget", "passes", "newa", "bc", "lm", "pnwhr", "pnwt", "pnw", "wc", "na")


def synth(TM, vid):
    if "ll" not in TM.VIEWS[vid]: raise KeyError("ll")
    b = TM.VIEWS[vid]["ll"]
    lo = np.arange(b[0] - 2.0, b[1] + 2.01, 0.25)
    la = np.arange(b[3] + 2.0, b[2] - 2.01, -0.25)
    return (la, lo, np.ones((len(la), len(lo)), dtype=float))


def render(TM, vid, scale=1.0, passes=False):
    import matplotlib.pyplot as plt
    import house_style as HS
    saved = HS.font
    if scale != 1:
        def small(weight=500, size=12, _f=saved, _s=scale): return _f(weight, size * _s)
        TM.HS.font = small; HS.font = small
    fig, ax, _ky = TM.frame(vid); fig.patch.set_alpha(0); ax.patch.set_alpha(0)
    field = synth(TM, vid)
    FE.place_view_towns(TM, ax, vid, field)
    if passes:
        import studio_views as SV
        fig.canvas.draw(); r = fig.canvas.get_renderer(); pt = 72.0 / fig.dpi
        axbb = ax.get_window_extent(r)
        arts = [t for t in ax.texts if t.get_visible()]
        SV.add_passes(TM, ax, arts, field)
    items = FE.label_items(fig, ax)
    plt.close(fig)
    TM.HS.font = saved; HS.font = saved
    return items


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--site", default=os.path.join(HERE, "site")); a = ap.parse_args()
    import matplotlib; matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import house_style as HS, temp_maps as TM
    HS.use_for_plots(); FE.extra_views(TM, ccrs)
    static = os.path.join(a.site, "slayers", "static"); slayers = os.path.join(a.site, "slayers", "static")
    os.makedirs(static, exist_ok=True); os.makedirs(slayers, exist_ok=True)
    pnwt_items = None
    for vid in VIEWS:
        if vid not in TM.VIEWS or "ll" not in TM.VIEWS[vid]: print("skip", vid); continue
        items = render(TM, vid)
        if vid == "pnwt": pnwt_items = items
        path = os.path.join(static, f"labels_{vid}.json")
        wrote = FE.write_town_labels(path, items)
        print(f"{vid}: {sum(1 for i in items if i['k']=='t')} names, {sum(1 for i in items if i['k']=='m')} markers" + ("" if wrote else " (none)"))
    # HRRR / RRFS / NBM wide view: pnwhr towns at the smaller loop size (wawide_small_towns_lcc.py, scale 0.83)
    items = render(TM, "pnwhr", scale=0.83)
    FE.write_town_labels(os.path.join(slayers, "labels_pnwhr_s2.json"), items)
    print(f"pnwhr_s2: {sum(1 for i in items if i['k']=='t')} names")
    # Global wide view: studio_views wawide placement, then the 0.83 scale + passes (wawide_small_towns.py)
    import studio_views as SV
    TM, HS, _ccrs = SV.setup()
    items = render(TM, SV.VID, scale=0.83, passes=True)
    FE.write_town_labels(os.path.join(slayers, "labels_wawide_s2.json"), items)
    print(f"wawide_s2: {sum(1 for i in items if i['k']=='t')} names")
    # Pacific NW tight override (towns_pnwt_v2.png) uses the same placement as the unscaled pnwt pass above,
    # before setup() extends the regional request list for the wide view.
    if pnwt_items:
        FE.write_town_labels(os.path.join(static, "labels_pnwt_v2.json"), pnwt_items)
        print(f"pnwt_v2: {sum(1 for i in pnwt_items if i['k']=='t')} names")


if __name__ == "__main__":
    main()
