#!/usr/bin/env python3
"""Mock screenshots for t3052u flood-label + hover work. Not for production."""
import asyncio, json, sys, base64
from pathlib import Path
from playwright.async_api import async_playwright
B = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8766"
O = Path(sys.argv[2] if len(sys.argv) > 2 else "/workspace/wx-models-site/tide_flood_label_hover_mock_20261114/shots")
O.mkdir(parents=True, exist_ok=True)

STS = [
    ("9441102", "westport"),
    ("9447130", "seattle"),
    ("9449880", "fridayharbor"),
    ("9446484", "tacoma"),
    ("9442396", "lapush"),
]

async def load(pg, q):
    await pg.goto(f"{B}/tide/index.html?{q}", wait_until="load")
    await pg.wait_for_function("window.__tideDrawn > 0", timeout=90000)
    await pg.wait_for_timeout(800)

async def crop_labels(pg, path):
    L = await pg.evaluate("() => TIDE.qa().floodLabels")
    if not L: print("no labels for crop", path); return L
    b = await pg.evaluate("() => { const r = document.getElementById('tc').getBoundingClientRect(); return [r.left, r.top]; }")
    xs = [l["x0"] for l in L] + [l["x1"] for l in L]
    ys = [l["y0"] for l in L] + [l["y1"] for l in L] + [l["ly"] for l in L]
    # clip is in CSS pixels of the page; device_scale_factor applies to the screenshot
    pad = 36
    clip = {"x": max(0, b[0] + min(xs) - pad), "y": max(0, b[1] + min(ys) - pad),
            "width": max(xs) - min(xs) + pad * 2 + 40, "height": max(ys) - min(ys) + pad * 2}
    await pg.screenshot(path=str(path), clip=clip)
    return L

async def crop_legend(pg, path):
    box = await pg.evaluate("""() => {
      const cv = document.getElementById('tc'); const r = cv.getBoundingClientRect();
      return {x: r.left, y: r.top, width: Math.min(r.width, 1100), height: Math.min(220, r.height * 0.28)};
    }""")
    await pg.screenshot(path=str(path), clip=box)

async def main():
    notes = {}
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await br.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
        for st, nm in STS:
            await load(pg, f"st={st}&days=9")
            q = await pg.evaluate("() => TIDE.qa()")
            notes[nm] = {"legend": q.get("legend"), "labels": q.get("floodLabels"), "floods": q.get("floods"), "note": q.get("floodLabelNote")}
            print(nm, "labels", json.dumps(q.get("floodLabels")), "note", q.get("floodLabelNote"), "legend_has_flood", any("flood" in (x or "").lower() for x in (q.get("legend") or [])))
            await pg.screenshot(path=str(O / f"web_{nm}_floodlines_1920x1080@2x.png"))
            if nm in ("westport", "fridayharbor", "lapush"):
                await crop_labels(pg, O / f"crop_{nm}_flood_labels@2x.png")
        await crop_legend(pg, O / "crop_westport_legend_no_flood_rows@2x.png")  # last page is lapush; reload westport
        await load(pg, "st=9441102&days=9")
        await crop_legend(pg, O / "crop_westport_legend_no_flood_rows@2x.png")
        await crop_labels(pg, O / "crop_westport_flood_labels@2x.png")
        # desktop hover
        box = await pg.evaluate("() => { const r = document.getElementById('tc').getBoundingClientRect(); return {x: r.left + r.width * 0.55, y: r.top + r.height * 0.42}; }")
        await pg.mouse.move(box["x"], box["y"]); await pg.wait_for_timeout(300)
        hov = await pg.evaluate("() => ({ text: document.getElementById('tip').innerText, hidden: document.getElementById('tip').hidden, h: window.__tideHover })")
        print("desktop hover", json.dumps(hov)[:500])
        await pg.screenshot(path=str(O / "web_westport_hover_1920x1080@2x.png"))
        # close crop of tooltip
        tip = await pg.evaluate("""() => { const t = document.getElementById('tip'); const r = t.getBoundingClientRect();
          return {x: Math.max(0,r.left-16), y: Math.max(0,r.top-16), width: r.width+32, height: r.height+32, hidden: t.hidden}; }""")
        if not tip["hidden"]:
            await pg.screenshot(path=str(O / "crop_westport_hover_tooltip@2x.png"), clip={k: tip[k] for k in ("x","y","width","height")})

        # phone shots
        ph = await br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
        for st, nm in STS:
            await load(ph, f"st={st}&days=9")
            await ph.screenshot(path=str(O / f"phone_{nm}_floodlines_390x844@3x.png"))
        # phone tooltip via tap
        await load(ph, "st=9441102&days=9")
        box = await ph.evaluate("() => { const r = document.getElementById('tc').getBoundingClientRect(); return {x: r.left + r.width * 0.55, y: r.top + r.height * 0.42}; }")
        await ph.touchscreen.tap(box["x"], box["y"]); await ph.wait_for_timeout(400)
        hov = await ph.evaluate("() => ({ text: document.getElementById('tip').innerText, hidden: document.getElementById('tip').hidden, h: window.__tideHover })")
        print("phone hover", json.dumps(hov)[:500])
        await ph.screenshot(path=str(O / "phone_westport_tooltip_390x844@3x.png"))

        # Studio
        sp = await br.new_page(viewport={"width": 1920, "height": 1080})
        await sp.goto(B + "/studio.html", wait_until="load"); await sp.wait_for_timeout(4000)
        await sp.select_option("#smode", "tide")
        await sp.wait_for_function("() => window.__studioTide > 0", timeout=90000)
        await sp.frame_locator("#tdf").locator("#st").select_option("9441102")
        await sp.wait_for_function("() => document.getElementById('tdf').contentWindow.TIDE.qa().st === '9441102'", timeout=90000)
        await sp.wait_for_timeout(2500)
        await sp.screenshot(path=str(O / "studio_page_westport_1920x1080.png"))
        d = await sp.evaluate("() => document.getElementById('ch').toDataURL('image/png')")
        (O / "studio_frame16x9_westport_3840x2160.png").write_bytes(base64.b64decode(d.split(",")[1]))
        d2 = await sp.evaluate("() => document.getElementById('cv').toDataURL('image/png')")
        (O / "studio_frame9x16_westport_2160x3840.png").write_bytes(base64.b64decode(d2.split(",")[1]))
        box = await sp.evaluate("() => { const r = document.getElementById('ch').getBoundingClientRect(); return {x: r.left + r.width * 0.55, y: r.top + r.height * 0.45}; }")
        await sp.mouse.move(box["x"], box["y"]); await sp.wait_for_timeout(350)
        shov = await sp.evaluate("() => window.__studioTideHover")
        print("studio hover", json.dumps(shov)[:500] if shov else None)
        await sp.screenshot(path=str(O / "studio_westport_hover_1920x1080.png"))
        await br.close()
    (O / "qa_notes.json").write_text(json.dumps(notes, indent=2))
    print("wrote", O)

asyncio.run(main())
