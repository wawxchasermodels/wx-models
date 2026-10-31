"""Collect build_kit.py outputs (<src>/<kind>_<view>/) into the site kit tree (site/wamaps/kit/<view>/): base.png, mask.png, lut.bin
and titles/ are per view (identical for both kinds, checked); <kind>.json + <kind>_overlay.png per product."""
import sys, os, json, shutil, filecmp
src, dst = sys.argv[1], sys.argv[2]
for view in ("full", "west", "east"):
    o = os.path.join(dst, view); os.makedirs(o + "/titles", exist_ok=True)
    for f in ("base.png", "mask.png", "lut.bin"):
        a, b = f"{src}/low_{view}/{f}", f"{src}/high_{view}/{f}"
        if f != "base.png": assert filecmp.cmp(a, b, shallow=False), (view, f)
        shutil.copy(a, o + "/" + f)
    for kind in ("low", "high"):
        k = json.load(open(f"{src}/{kind}_{view}/kit.json")); k.pop("static_ops", None)
        for L in k["labels"]:
            for q in ("x", "y", "fi", "fj"): L[q] = round(L[q], 2)
        json.dump(k, open(f"{o}/{kind}.json", "w"), separators=(",", ":"))
        shutil.copy(f"{src}/{kind}_{view}/overlay.png", f"{o}/{kind}_overlay.png")
        for t in os.listdir(f"{src}/{kind}_{view}/titles"):
            if t.startswith(kind + "_"): shutil.copy(f"{src}/{kind}_{view}/titles/{t}", f"{o}/titles/{t}")
print("ok")
