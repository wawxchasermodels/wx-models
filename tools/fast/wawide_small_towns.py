#!/usr/bin/env python3
"""11-04 (Benjamin t2308u "Make the town names little smaller on Washington wide for loops"): the global models' Studio
"Washington (wide, for loops)" town layer rebuilt with every label font at SCALE (0.83, ~17 % smaller: names 9.5/8.5/8 ->
7.9/7.1/6.6 pt, numbers 9.5 -> 7.9 pt, pass names 8 -> 6.6 pt), same placement code (studio_views.town_slots + passes), dots
unchanged. Shipped with the site (no R2 change): slayers/static/{,x2/}towns_wawide_s2.png + slayers/static/wawide_s2.json
{models: {m: towns}}; viewer.js uses them for the wawide view only (Coast view and every other view untouched).

  STUDIO_VIEW=wawide wawide_small_towns.py --manifest M --sv studio_views.json --out site/slayers
"""
import os, sys, json, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ["STUDIO_VIEW"] = "wawide"
import studio_views as SV, fast_encode as FE
SCALE = 0.83; PNG = "static/towns_wawide_s2.png"

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
    json.dump(dict(note="Studio wawide smaller town labels (t2308u), scale %.2f" % SCALE, png=PNG, models=out), open(f"{a.out}/static/wawide_s2.json", "w"))
    print("towns", names0)
main()
