#!/usr/bin/env python3
"""11-04 (Benjamin t2314u "yes rebuild those too", after t2308u): HRRR / RRFS / NBM "Washington (wide, for loops)" in Studio is their
Pacific NW (high-res) view (pnwhr) under the Studio camera, whose town names come from the static towns_pnwhr.png layer. This builds the
same layer with every label font x SCALE (0.83, like wawide_small_towns.py: names 9.5/8.5/8 -> 7.9/7.1/6.6 pt, numbers 9.5 -> 7.9, pass
names 8 -> 6.6), dots unchanged, same placement code (fast_encode.static's town section for pnwhr), into NEW site-shipped files
slayers/static/{,x2/}towns_pnwhr_s2.png + number slots merged into slayers/static/wawide_s2.json {models: {hrrr, rrfs, nbm}}.
viewer.js uses them for the Studio wide view only; the Pacific NW (high-res) view itself keeps R2's towns_pnwhr.png. Static layer +
the published crop, so every model cycle uses it (no per-cycle step).

  wawide_small_towns_lcc.py --manifest M --out site/slayers [--check]   (--check: SCALE 1, compare slots with the manifest's pnwhr)
"""
import os, sys, json, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fast_encode as FE
SCALE = 0.83; VID = "pnwhr"; PNG = "static/towns_pnwhr_s2.png"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--manifest", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="hrrr,rrfs,nbm"); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt, cartopy.crs as ccrs
    import house_style as HS, temp_maps as TM
    HS.use_for_plots(); FE.extra_views(TM, ccrs); pc = ccrs.PlateCarree()
    sc = 1.0 if a.check else SCALE; f0 = HS.font
    def small(weight=500, size=12): return f0(weight, size * sc)
    TM.HS.font = small; HS.font = small
    man = json.load(open(a.manifest)); os.makedirs(f"{a.out}/static/x2", exist_ok=True)
    jp = f"{a.out}/static/wawide_s2.json"; doc = json.load(open(jp)) if os.path.exists(jp) else {"models": {}}
    def layer_fig():
        fig, ax, ky = TM.frame(VID); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    names0 = None; bad = 0
    for m in a.models.split(","):
        MD = FE.MODELS[m]; Mm = man["models"][m]; i0, i1, j0, j1 = Mm["crop"]
        la, lo, oro = FE.model_grid(m)
        rad = MD.get("radius", 6371229.0)
        hp = ccrs.LambertConformal(globe=ccrs.Globe(ellipse="sphere", semimajor_axis=rad, semiminor_axis=rad), **MD.get("lcc", FE.HRRR_LCC))
        g = hp.transform_points(pc, lo, la); gx0, gy0 = g[0, 0, 0], g[0, 0, 1]
        d = 3000.0 if "lcc" not in MD else float(np.hypot(g[0, 1, 0] - gx0, g[0, 1, 1] - gy0))
        def to_ij(LO_, LA_):
            hh = hp.transform_points(pc, LO_, LA_); return (hh[..., 1] - gy0) / d, (hh[..., 0] - gx0) / d
        tw_la, tw_lo = la[i0:i1, j0:j1], lo[i0:i1, j0:j1]
        fig, ax, ky = layer_fig()
        arts = TM.towns(ax, VID, (tw_la, tw_lo, tw_la), lambda v: None if not np.isfinite(v) else "88") or []
        tv_la = dict(getattr(ax, "town_values", {}) or {}); pr_la = dict(getattr(ax, "pass_raw", {}) or {})
        fig2, ax2, _ = layer_fig(); TM.towns(ax2, VID, (tw_la, tw_lo, tw_lo), lambda v: None if not np.isfinite(v) else "88")
        tv_lo = dict(getattr(ax2, "town_values", {}) or {}); pr_lo = dict(getattr(ax2, "pass_raw", {}) or {}); plt.close(fig2)
        lab2key = {v[0]: k for k, v in TM.WA_PASSES.items()}
        fig.canvas.draw(); r = fig.canvas.get_renderer(); Wd, Hd = fig.get_size_inches() * fig.dpi; slots = []; last = None
        for t in arts:
            if t.get_text() != "88": last = t.get_text(); continue
            if not t.get_visible(): continue
            if last in tv_la: pla, plo, kind, el = tv_la[last], tv_lo.get(last), "town", None
            elif last in lab2key and lab2key[last] in pr_la: k_ = lab2key[last]; pla, plo, kind, el = pr_la[k_], pr_lo.get(k_), "pass", TM.WA_PASSES[k_][3]
            else: continue
            if plo is None or not (np.isfinite(pla) and np.isfinite(plo)): continue
            fi_, fj_ = to_ij(np.array([[plo]]), np.array([[pla]])); fi_, fj_ = float(round(float(fi_[0, 0]) - i0)), float(round(float(fj_[0, 0]) - j0))
            bb = t.get_window_extent(r)
            slot = dict(name=last, kind=kind, x=bb.x0 / Wd, y=1 - (bb.y0 + bb.y1) / 2 / Hd, fi=fi_, fj=fj_, size=t.get_fontsize(), color=t.get_color())
            if kind == "pass" and oro is not None:
                rr, cc = int(round(fi_)) + i0, int(round(fj_)) + j0; slot["t2m_corr"] = float(TM.LAPSE_T_F_PER_FT * (oro[rr, cc] - el))
            slots.append(slot); t.set_visible(False)
        fig._wx_labels = FE.label_items(fig, ax)
        names = [s["name"] for s in slots]
        if a.check:
            ref = Mm["views"][VID]["towns"]; rn = [s["name"] for s in ref]
            dx = max([abs(s["x"] - q["x"]) + abs(s["y"] - q["y"]) for s, q in zip(slots, ref)] or [0])
            dij = max([abs(s["fi"] - q["fi"]) + abs(s["fj"] - q["fj"]) for s, q in zip(slots, ref)] or [0])
            ok = names == rn and dx < 1e-4 and dij < 0.01; bad += not ok
            print(m, "check", "OK" if ok else "DIFF", len(slots), len(ref), "dxy %.2g dij %.2g" % (dx, dij), set(names) ^ set(rn), flush=True)
            if m == "hrrr": fig.savefig(f"{a.out}/check_towns_pnwhr.png", dpi=FE.DPI, transparent=True)
            plt.close(fig); continue
        if names0 is None:
            labs = getattr(fig, "_wx_labels", None)
            fig.savefig(f"{a.out}/{PNG}", dpi=FE.DPI, transparent=True); fig.savefig(f"{a.out}/{PNG}".replace("/static/", "/static/x2/"), dpi=FE.DPI * FE.X2, transparent=True); names0 = names
            if labs: FE.write_town_labels(f"{a.out}/" + PNG.replace("towns_", "labels_").replace(".png", ".json"), labs)
        elif names != names0: raise SystemExit(f"{m}: placement differs from the shared layer")
        plt.close(fig); doc["models"][m] = dict(towns=slots, towns_png=PNG); print(m, len(slots), "slots", flush=True)
    if a.check: sys.exit(1 if bad else 0)
    doc["lcc_note"] = "HRRR/RRFS/NBM wide view (pnwhr layer) smaller labels (t2314u), scale %.2f (wawide_small_towns_lcc.py)" % SCALE
    json.dump(doc, open(jp, "w")); print("towns", names0)
main()
