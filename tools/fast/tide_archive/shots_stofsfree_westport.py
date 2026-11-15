#!/usr/bin/env python3
"""Westport screenshots of the STOFS-free Conditional: desktop 1920x1080@2x and phone 390x844@3x, wind OFF and ON.
Verifies the page rendered (lines painted, method stofs-free / stofs-free+wind, Now label does not cover flood words).
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

B = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/workspace/wx-models-site/tide_sst_warmwater_mock_20261114/shots_stofsfree")
OUT.mkdir(parents=True, exist_ok=True)

COLORS = """(id) => {
  const cv = document.getElementById(id); if (!cv) return null;
  const c = cv.getContext('2d'), w = cv.width, h = cv.height, d = c.getImageData(0,0,w,h).data;
  const n = {pred:0, obs:0, cond:0};
  for (let i=0;i<d.length;i+=4){
    const r=d[i],g=d[i+1],b=d[i+2],a=d[i+3];
    if (a<80) continue;
    if (r<80 && g<140 && b>180) n.pred++;
    else if (r>180 && g>180 && b>180) n.obs++;
    else if (r>180 && g>120 && b<80) n.cond++;
  }
  return n;
}"""

def overlap(a, b, eps=0.5):
    return (a["x"] + a["w"] > b["x"] + eps and b["x"] + b["w"] > a["x"] + eps and
            a["y"] + a["h"] > b["y"] + eps and b["y"] + b["h"] > a["y"] + eps)

async def load(pg, wind):
    url = f"{B}/tide/?st=9441102&days=9"
    await pg.goto(url, wait_until="load", timeout=120000)
    await pg.wait_for_function("() => window.__tideDrawn > 0", timeout=120000)
    # force wind state
    await pg.evaluate(f"""() => {{
      try {{ localStorage.setItem('tide:wind', '{1 if wind else 0}'); }} catch (e) {{}}
      if (window.TIDE) {{
        const T = window.TIDE;
        // TIDE may not expose T; click the chip if needed
      }}
    }}""")
    # click chip if needed
    state = await pg.evaluate("() => window.TIDE && window.TIDE.qa && window.TIDE.qa()")
    want = bool(wind)
    got = bool((state or {}).get("windOn"))
    if got != want:
        btn = pg.locator("#windtog")
        await btn.click()
        await pg.wait_for_timeout(400)
        # if click only swaps precomputed lines, method should update; if not, reload
        state = await pg.evaluate("() => window.TIDE && window.TIDE.qa()")
        if bool((state or {}).get("windOn")) != want:
            await pg.reload(wait_until="load")
            await pg.wait_for_function("() => window.__tideDrawn > 0", timeout=120000)
    await pg.wait_for_timeout(600)
    return await pg.evaluate("() => window.TIDE && window.TIDE.qa()")

async def one(br, W, H, dpr, phone, wind, tag, fname):
    ctx = await br.new_context(viewport={"width": W, "height": H}, device_scale_factor=dpr, is_mobile=phone, has_touch=phone)
    # start with stored wind so first paint matches
    await ctx.add_init_script(f"try{{localStorage.setItem('tide:wind','{1 if wind else 0}');}}catch(e){{}}")
    pg = await ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:240]))
    q = await load(pg, wind)
    want_m = "stofs-free+wind" if wind else "stofs-free"
    checks = {"tag": tag, "method": (q or {}).get("method"), "windOn": (q or {}).get("windOn"),
              "st": (q or {}).get("st"), "pred": (q or {}).get("pred"), "obs": (q or {}).get("obs"),
              "cond": (q or {}).get("cond"), "nowLabel": (q or {}).get("nowLabel"),
              "floodLabels": (q or {}).get("floodLabels"), "windTest": (q or {}).get("windTest"),
              "sst": (q or {}).get("sst"), "errs": errs}
    ok = True
    reasons = []
    if not q or q.get("err"):
        ok, reasons = False, [f"did not load: {(q or {}).get('err')}"]
    else:
        if q.get("st") != "9441102":
            ok = False; reasons.append(f"station {q.get('st')}")
        if q.get("method") != want_m:
            ok = False; reasons.append(f"method {q.get('method')} != {want_m}")
        if bool(q.get("windOn")) != bool(wind):
            ok = False; reasons.append(f"windOn {q.get('windOn')}")
        if not q.get("pred") or not q.get("obs") or not q.get("cond"):
            ok = False; reasons.append(f"missing lines pred/obs/cond={q.get('pred')}/{q.get('obs')}/{q.get('cond')}")
        n = await pg.evaluate(COLORS, "tc")
        checks["painted"] = n
        if not n or n.get("pred", 0) < 50 or n.get("obs", 0) < 30 or n.get("cond", 0) < 50:
            ok = False; reasons.append(f"not painted {n}")
        now = q.get("nowLabel")
        labs = q.get("floodLabels") or []
        if now and labs:
            nb = {"x": now["x"], "y": now["y"], "w": now["w"], "h": now["h"]}
            hits = []
            for lab in labs:
                lb = {"x": lab["x0"], "y": lab["y0"], "w": lab["x1"]-lab["x0"], "h": lab["y1"]-lab["y0"]}
                if overlap(nb, lb):
                    hits.append(lab.get("k"))
            checks["now_overlaps"] = hits
            if hits:
                ok = False; reasons.append(f"Now overlaps flood words {hits}")
        wt = q.get("windTest")
        if wt is not None and not wt.get("ok"):
            ok = False; reasons.append(f"identity {wt}")
        if errs:
            ok = False; reasons.append(f"page errors {errs[:2]}")
    path = OUT / fname
    await pg.screenshot(path=str(path), full_page=False)
    checks["ok"] = ok
    checks["reasons"] = reasons
    checks["path"] = str(path)
    print(("PASS" if ok else "FAIL"), tag, "->", path, reasons or "rendered")
    await ctx.close()
    return checks

async def main():
    if not B:
        print("usage: shots_stofsfree_westport.py <site url> [outdir]")
        return 2
    results = []
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        jobs = [
            (1920, 1080, 2, False, False, "desktop_windoff", "westport_stofsfree_desktop_1920x1080@2x_windoff.png"),
            (1920, 1080, 2, False, True,  "desktop_windon",  "westport_stofsfree_desktop_1920x1080@2x_windon.png"),
            (390, 844, 3, True,  False, "phone_windoff",   "westport_stofsfree_phone_390x844@3x_windoff.png"),
            (390, 844, 3, True,  True,  "phone_windon",    "westport_stofsfree_phone_390x844@3x_windon.png"),
        ]
        for W,H,dpr,phone,wind,tag,fn in jobs:
            results.append(await one(br, W,H,dpr,phone,wind,tag,fn))
        await br.close()
    report = {"ok": all(r["ok"] for r in results), "results": results}
    (OUT / "shots_stofsfree_report.json").write_text(json.dumps(report, indent=2, default=str))
    print("wrote", OUT / "shots_stofsfree_report.json", "ALL_OK" if report["ok"] else "SOME_FAILED")
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
