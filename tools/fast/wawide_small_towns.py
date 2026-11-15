#!/usr/bin/env python3
"""11-15 (t3093u): Studio "Washington (wide, for loops)" town layer at Washington typography (SCALE 1: names 9.5 /
pass names 8, weight 600, halo 2.6, dots 3.6 / 4.6). Was 0.83 (t2308u). Same placement code (studio_views.town_slots +
passes). Shipped with the site: slayers/static/{,x2/}towns_wawide_s2.png + slayers/static/wawide_s2.json. Studio paints
these at the same on-screen size as the Washington view (paintStudioTowns typ). Coast view untouched.

  STUDIO_VIEW=wawide wawide_small_towns.py --manifest M --sv studio_views.json --out site/slayers
"""
import os, sys, json, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ["STUDIO_VIEW"] = "wawide"
import studio_views as SV, fast_encode as FE
SCALE = 1.0; PNG = "static/towns_wawide_s2.png"  # 11-15 (t3093u): match Washington typography (was 0.83)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--manifest", required=True); ap.add_argument("--sv", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    import matplotlib.pyplot as plt
    man = json.load(open(a.manifest)); sv = json.load(open(a.sv))["models"]
    TM, HS, ccrs = SV.setup(); f0 = HS.font
    def small(weight=500, size=12): return f0(weight, size * SCALE)
    TM.HS.font = small; HS.font = small
    def layer_fig():
        fig, ax, ky = TM.frame(SV.VID); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    os.makedirs(f"{a.out}/static/x2", exist_ok=True); out = {}; names0 = None
    for m, e in sv.items():
        if "wawide" not in e: continue
        MD = FE.MODELS.get(m); crop = man["models"].get(m, {}).get("crop")
        if not MD or MD.get("grid") != "ll" or not crop: print(m, "skipped (no ll model / crop)"); continue
        i0, i1, j0, j1 = crop
        fig, slots = SV.town_slots(TM, SV.VID, layer_fig, i0, i1, j0, j1, MD.get("res", 0.25), passes=True)
        names = [s["name"] for s in slots]
        if names0 is None:
            labs = getattr(fig, "_wx_labels", None) or FE.label_items(fig, fig.axes[0])
            fig.savefig(f"{a.out}/{PNG}", dpi=FE.DPI, transparent=True); fig.savefig(f"{a.out}/{PNG}".replace("/static/", "/static/x2/"), dpi=FE.DPI * FE.X2, transparent=True); names0 = names
            if labs: FE.write_town_labels(f"{a.out}/" + PNG.replace("towns_", "labels_").replace(".png", ".json"), labs)
        elif names != names0: raise SystemExit(f"{m}: placement differs")
        plt.close(fig); out[m] = slots; print(m, len(slots), "slots", flush=True)
    for m, e in sv.items():   # models without their own entry here (same crop as a built one) copy it
        if "wawide" in e and m not in out:
            src = next((k for k in out if man["models"].get(k, {}).get("crop") == man["models"].get(m, {}).get("crop")), None)
            if src: out[m] = out[src]; print(m, "copied from", src)
    json.dump(dict(note="Studio wawide town labels match Washington typography (t3093u), scale %.2f" % SCALE, png=PNG, models=out), open(f"{a.out}/static/wawide_s2.json", "w"))
    print("towns", names0)
main()
